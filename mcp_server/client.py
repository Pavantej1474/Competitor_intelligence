# mcp/client.py
import asyncio
import json
import subprocess
import sys
import os
from mcp.server.fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from groq import AsyncGroq
from config import GROQ_API_KEY
from prompts.news_prompt import build_prompt_from_articles, CHANGE_TYPES

groq_client = AsyncGroq(api_key=GROQ_API_KEY, max_retries=0)
MODEL = "llama-3.1-8b-instant"

def _get_server_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

async def get_news_via_mcp(company: str) -> list[dict]:
    """
    Use MCP server tools to search for news, then LLM to extract structure.
    The LLM drives the search by calling tools agentically.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_get_server_path()],
        env=os.environ.copy(),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools from MCP server
            tools_result = await session.list_tools()
            mcp_tools = tools_result.tools

            # Convert MCP tools to Groq tool format
            groq_tools = []
            for tool in mcp_tools:
                # Only expose search tools to the news-fetching LLM
                if tool.name in ("search_competitor_news", "search_company_topic"):
                    groq_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        }
                    })

            # System prompt for the news-fetching agent
            system = f"""You are a financial intelligence analyst searching for competitor news.
Your job: find the most recent and relevant news about **{company}** that affects 
wealth management clients — fee changes, product launches, platform updates, 
promotions, partnerships, rate changes, advisor tools.

STRATEGY:
1. Use search_competitor_news FIRST with a broad 'wealth management' topic.
2. Then use search_company_topic for 2-3 DIFFERENT specific change_types 
   (e.g. 'fee_change', 'platform_update', 'product_launch', 'partnership').
3. Use DIFFERENT topics each call to maximize article diversity.
4. Make 3-5 targeted searches for comprehensive coverage.
5. Stop when you have at least 8-10 diverse articles."""

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Search for recent news about {company} that LPL Financial advisors should know about."}
            ]

            all_articles = []

            # Agentic loop — LLM decides what to search
            total_tool_calls = 0
            MAX_TOTAL_TOOL_CALLS = 5  # allow more searches for broader coverage
            for _ in range(3):  # max 3 LLM iterations
                if total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
                    break
                try:
                    response = await groq_client.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        tools=groq_tools,
                        tool_choice="auto",
                        temperature=0.1,
                        max_tokens=1000,
                    )
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "rate_limit" in error_str:
                        print(f"    ⏳ Rate limited, waiting 10s...")
                        await asyncio.sleep(10)
                        try:
                            response = await groq_client.chat.completions.create(
                                model=MODEL,
                                messages=messages,
                                tools=groq_tools,
                                tool_choice="auto",
                                temperature=0.1,
                                max_tokens=1000,
                            )
                        except Exception as e2:
                            print(f"    ⚠️ Groq API error after retry: {e2}")
                            break
                    else:
                        print(f"    ⚠️ Groq API error: {e}")
                        break

                msg = response.choices[0].message

                if not msg.tool_calls:
                    break  # LLM decided it has enough

                # Limit tool calls per batch to stay within token budget
                tool_calls_to_process = msg.tool_calls[:max(1, MAX_TOTAL_TOOL_CALLS - total_tool_calls)]

                # Process tool calls
                tool_calls_formatted = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
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
                    print(f"    🔧 MCP tool: {fn_name}({fn_args})")

                    # Call tool on MCP server
                    tool_result = await session.call_tool(fn_name, fn_args)
                    result_text = tool_result.content[0].text if tool_result.content else "[]"

                    # Collect articles from search results
                    try:
                        articles = json.loads(result_text)
                        if isinstance(articles, list):
                            all_articles.extend(articles)
                    except:
                        pass

                    # Truncate tool result to avoid exceeding Groq token limits
                    MAX_TOOL_RESULT_CHARS = 2000
                    if len(result_text) > MAX_TOOL_RESULT_CHARS:
                        result_text = result_text[:MAX_TOOL_RESULT_CHARS] + '... (truncated)'

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })
                    total_tool_calls += 1

            # Deduplicate articles by URL
            seen_urls = set()
            unique_articles = []
            for a in all_articles:
                url = a.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_articles.append(a)

            print(f"    📄 {company}: {len(unique_articles)} unique articles from MCP/Tavily")
            return unique_articles