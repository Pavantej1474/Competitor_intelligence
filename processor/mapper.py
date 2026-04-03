# processor/mapper.py
import asyncio
import json
import sys
import os
import re
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from groq import AsyncGroq
from prompts.advisor_prompt import build_advisor_summary_prompt
from config import GROQ_API_KEY

groq_client = AsyncGroq(api_key=GROQ_API_KEY, max_retries=0)
MODEL = "llama-3.1-8b-instant"

def _get_server_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server", "server.py")

def _parse_json(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except:
        pass
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        try:
            return json.loads(re.sub(r',\s*([}\]])', r'\1', match.group(0)))
        except:
            pass
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(re.sub(r',\s*([}\]])', r'\1', match.group(0)))
        except:
            pass
    return None

async def map_news_to_clients(news_item: dict, clients: list) -> list:
    """
    MCP agentic client mapping:
    1. LLM reads the news item
    2. LLM calls local client-lookup tools via MCP to find candidates
    3. LLM scores only the relevant subset of clients
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_get_server_path()],
        env=os.environ.copy(),
    )

    clients_json = json.dumps(clients)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            
            # Only expose client-lookup tools (not search tools) for mapping
            client_tools = []
            for tool in tools_result.tools:
                if tool.name.startswith("find_clients_"):
                    client_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        }
                    })

            system = """You are a competitive intelligence analyst at LPL Financial.
Given a competitor news item, use the tools to find which LPL clients are at risk.

TOOL STRATEGY:
- Use find_clients_by_pain_point FIRST — this is the strongest at-risk signal
  (e.g. if news is about a new platform, search pain_point "platform")
- Use find_clients_by_interest for clients whose interests match the news
- Use find_clients_by_holding only if the news is specifically about benefits 
  for shareholders of that company
- Use find_clients_by_sector if news impacts a whole sector

CRITICAL RULES:
- Do NOT match clients just because they hold the competitor's stock
- Call 2-3 tools maximum, then stop
- After tool calls, produce the final JSON assessment"""

            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"""Find at-risk LPL clients for this competitor news.
The clients_json parameter for ALL tool calls is: {clients_json}

COMPETITOR NEWS:
{json.dumps(news_item, indent=2)}"""
                }
            ]

            candidate_clients = {}

            # Agentic tool-calling loop
            total_tool_calls = 0
            MAX_TOTAL_TOOL_CALLS = 3
            for _ in range(2):
                if total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
                    break
                try:
                    response = await groq_client.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        tools=client_tools,
                        tool_choice="auto",
                        temperature=0.2,
                        max_tokens=800,
                    )
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "rate_limit" in error_str:
                        await asyncio.sleep(10)
                        try:
                            response = await groq_client.chat.completions.create(
                                model=MODEL,
                                messages=messages,
                                tools=client_tools,
                                tool_choice="auto",
                                temperature=0.2,
                                max_tokens=800,
                            )
                        except Exception:
                            break
                    else:
                        break

                msg = response.choices[0].message

                if not msg.tool_calls:
                    break

                tool_calls_to_process = msg.tool_calls[:max(1, MAX_TOTAL_TOOL_CALLS - total_tool_calls)]

                tool_calls_formatted = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls_to_process
                ]
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tool_calls_formatted
                })

                for tc in tool_calls_to_process:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    # Always inject the clients_json
                    fn_args["clients_json"] = clients_json

                    tool_result = await session.call_tool(fn_name, fn_args)
                    result_text = tool_result.content[0].text if tool_result.content else "[]"

                    # Accumulate candidate clients
                    try:
                        found = json.loads(result_text)
                        if isinstance(found, list):
                            for c in found:
                                candidate_clients[c["id"]] = c
                    except:
                        pass

                    # Truncate tool result for LLM context
                    MAX_TOOL_RESULT_CHARS = 2000
                    if len(result_text) > MAX_TOOL_RESULT_CHARS:
                        result_text = result_text[:MAX_TOOL_RESULT_CHARS] + '... (truncated)'

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })
                    total_tool_calls += 1

            if not candidate_clients:
                return []

            # Final scoring pass — only on the small candidate subset
            scoring_prompt = f"""You found these LPL client candidates for a competitor news item.
Produce the final risk assessment — be SPECIFIC and cite exact client attributes.

COMPETITOR NEWS:
{json.dumps({k: news_item.get(k) for k in ["company","title","change_type","summary","client_impact"]}, indent=2)}

CANDIDATE CLIENTS:
{json.dumps(list(candidate_clients.values()), indent=2)}

For each client with a GENUINE connection, output:
- risk_type: "at_risk" if competitor's offering addresses their pain_point or interest
- risk_type: "retention_opportunity" if competitor news reveals a weakness LPL can exploit
- SKIP clients with only a vague connection

RETURN ONLY valid JSON array, no markdown. Return [] if no strong matches.

[
  {{
    "client_id": "",
    "client_name": "",
    "risk_type": "at_risk | retention_opportunity",
    "urgency": "high | medium | low",
    "competitor": "{news_item.get('company', '')}",
    "match_reason": "cite the EXACT pain_point or interest from the client profile",
    "suggested_action": "concrete action for LPL advisor",
    "talking_points": ["specific point 1", "specific point 2"]
  }}
]"""

            for attempt in range(3):
                try:
                    final = await groq_client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "user", "content": scoring_prompt}],
                        temperature=0.2,
                        max_tokens=1000,
                    )
                    result = _parse_json(final.choices[0].message.content)
                    return result if isinstance(result, list) else []
                except Exception as e:
                    if ("429" in str(e) or "rate_limit" in str(e)) and attempt < 2:
                        await asyncio.sleep(15)
                    else:
                        return []


async def build_advisor_feed(advisor: dict, news_with_clients: list) -> dict:
    trimmed = []
    for m in news_with_clients:
        news = m.get("competitor_news", {})
        trimmed.append({
            "competitor_news": {
                "company":       news.get("company", ""),
                "title":         news.get("title", ""),
                "change_type":   news.get("change_type", ""),
                "client_impact": (news.get("client_impact") or "")[:200],
            },
            "affected_lpl_clients": [
                {
                    "client_id":    c.get("client_id", ""),
                    "client_name":  c.get("client_name", ""),
                    "match_reason": (c.get("match_reason") or "")[:150],
                }
                for c in m.get("affected_lpl_clients", [])
            ]
        })

    prompt = build_advisor_summary_prompt(advisor, trimmed)
    response = await groq_client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1500,
    )
    raw = response.choices[0].message.content
    result = _parse_json(raw)
    return result if isinstance(result, dict) else {"error": "parse failed", "raw": raw}