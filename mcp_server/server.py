# mcp/server.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient
from config import TAVILY_API_KEY
import json

mcp = FastMCP("financial-intel")
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# ─── Tool 1: Search competitor news ───────────────────────────────
@mcp.tool()
def search_competitor_news(company: str, topic: str = "") -> str:
    """
    Search for recent news about a financial competitor using Tavily.
    Returns full article content, not truncated snippets.
    Use this to find fee changes, product launches, platform updates,
    promotions, partnerships, and any client-facing changes.
    
    Args:
        company: Company name e.g. 'Goldman Sachs', 'Fidelity'
        topic: Optional focus topic e.g. 'fee changes', 'new platform', 'wealth management'
    """
    query = f"{company} {topic} financial services wealth management clients 2025 2026"
    
    try:
        results = tavily.search(
            query=query,
            search_depth="advanced",      # deep search
            max_results=5,
            include_raw_content=False,    # use snippets to stay within LLM token limits
            topic="news",
        )
        
        articles = []
        MAX_CONTENT_CHARS = 500  # keep responses small for LLM token limits
        for r in results.get("results", []):
            content = r.get("content", "") or ""
            articles.append({
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "source":  r.get("url", "").split("/")[2] if r.get("url") else "",
                "date":    r.get("published_date", ""),
                "content": content[:MAX_CONTENT_CHARS],
                "score":   r.get("score", 0),
            })
        
        # Sort by Tavily relevance score
        articles.sort(key=lambda x: x["score"], reverse=True)
        return json.dumps(articles)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool 2: Search specific topic for a company ──────────────────
@mcp.tool()
def search_company_topic(company: str, change_type: str) -> str:
    """
    Search for a specific type of change from a company.
    Use this for targeted searches like fee changes, app launches, etc.
    
    Args:
        company: Company name
        change_type: One of: fee_change, product_launch, platform_update,
                     partnership, promotion, rate_change, advisor_tool
    """
    topic_queries = {
        "fee_change":       f"{company} fee reduction increase waiver advisory fees 2025 2026",
        "product_launch":   f"{company} new product launch fund account service 2025 2026",
        "platform_update":  f"{company} platform app digital tool launch feature update 2025 2026",
        "partnership":      f"{company} partnership acquisition merger deal announcement 2025 2026",
        "promotion":        f"{company} promotion offer bonus incentive clients 2025 2026",
        "rate_change":      f"{company} interest rate APY savings CD mortgage change 2025 2026",
        "advisor_tool":     f"{company} advisor tool CRM platform technology launch 2025 2026",
    }
    
    query = topic_queries.get(change_type, f"{company} {change_type} 2025 2026")
    
    try:
        results = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_raw_content=False,    # use snippets to stay within LLM token limits
            topic="news",
        )
        
        articles = []
        MAX_CONTENT_CHARS = 500  # keep responses small for LLM token limits
        for r in results.get("results", []):
            content = r.get("content", "") or ""
            articles.append({
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "source":  r.get("url", "").split("/")[2] if r.get("url") else "",
                "date":    r.get("published_date", ""),
                "content": content[:MAX_CONTENT_CHARS],
                "score":   r.get("score", 0),
            })
        
        return json.dumps(articles)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool 3: Client lookup tools (local — no API call) ────────────
@mcp.tool()
def find_clients_by_holding(ticker: str, clients_json: str) -> str:
    """
    Find clients who hold a specific stock ticker.
    Use when news is about a company clients may hold directly.
    
    Args:
        ticker: Stock ticker e.g. 'GS', 'JPM', 'BLK'
        clients_json: JSON string of client list
    """
    clients = json.loads(clients_json)
    matches = [
        {"id": c["id"], "name": c["name"], "advisor_id": c["advisor_id"],
         "pain_points": c.get("pain_points", []), "interests": c.get("interests", [])}
        for c in clients
        if ticker.upper() in [h.upper() for h in c.get("holdings", [])]
    ]
    return json.dumps(matches)


@mcp.tool()
def find_clients_by_pain_point(keyword: str, clients_json: str) -> str:
    """
    Find clients whose pain points match a keyword from the news.
    This is the STRONGEST signal for at-risk clients.
    
    Args:
        keyword: Pain point keyword e.g. 'fees', 'platform', 'digital tools', 'analytics'
        clients_json: JSON string of client list
    """
    clients = json.loads(clients_json)
    keyword_lower = keyword.lower()
    matches = [
        {"id": c["id"], "name": c["name"], "advisor_id": c["advisor_id"],
         "matched_pain_point": [pp for pp in c.get("pain_points", []) if keyword_lower in pp.lower()],
         "interests": c.get("interests", []), "account_type": c.get("account_type", "")}
        for c in clients
        if any(keyword_lower in pp.lower() for pp in c.get("pain_points", []))
    ]
    return json.dumps(matches)


@mcp.tool()
def find_clients_by_interest(keyword: str, clients_json: str) -> str:
    """
    Find clients whose stated interests match a keyword.
    
    Args:
        keyword: Interest keyword e.g. 'crypto', 'AI', 'ESG', 'retirement', 'fee transparency'
        clients_json: JSON string of client list
    """
    clients = json.loads(clients_json)
    keyword_lower = keyword.lower()
    matches = [
        {"id": c["id"], "name": c["name"], "advisor_id": c["advisor_id"],
         "matched_interest": [i for i in c.get("interests", []) if keyword_lower in i.lower()],
         "pain_points": c.get("pain_points", []), "account_type": c.get("account_type", "")}
        for c in clients
        if any(keyword_lower in i.lower() for i in c.get("interests", []))
    ]
    return json.dumps(matches)


@mcp.tool()
def find_clients_by_sector(sector: str, clients_json: str) -> str:
    """
    Find clients exposed to a specific sector.
    
    Args:
        sector: Sector name e.g. 'banking', 'tech', 'crypto', 'fixed_income'
        clients_json: JSON string of client list
    """
    clients = json.loads(clients_json)
    sector_lower = sector.lower()
    matches = [
        {"id": c["id"], "name": c["name"], "advisor_id": c["advisor_id"],
         "sectors": c.get("sectors", []), "pain_points": c.get("pain_points", []),
         "account_type": c.get("account_type", "")}
        for c in clients
        if any(sector_lower in s.lower() for s in c.get("sectors", []))
    ]
    return json.dumps(matches)


if __name__ == "__main__":
    mcp.run(transport="stdio")