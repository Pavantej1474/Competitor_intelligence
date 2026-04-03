# main.py
import asyncio
import json
from mcp_server.client import get_news_via_mcp
from groq import AsyncGroq
from processor.parser import parse_output
from processor.mapper import map_news_to_clients, build_advisor_feed
from storage.json_store import save, load
from data.companies import COMPETITORS
from prompts.news_prompt import build_prompt_from_articles
from config import GROQ_API_KEY

# Disable Groq SDK internal retry to prevent CancelledError conflicts with our manual retry
groq_client = AsyncGroq(api_key=GROQ_API_KEY, max_retries=0)
MODEL = "llama-3.1-8b-instant"
API_DELAY = 15  # seconds between API calls to respect Groq free tier 6000 TPM limit
BATCH_SIZE = 2  # articles per LLM call — small batches stay under 6000 TPM

async def _extract_batch(company: str, batch: list, batch_num: int) -> list:
    """Extract structured news from a small batch of articles via LLM."""
    prompt = build_prompt_from_articles(company, batch)
    for attempt in range(3):
        try:
            response = await groq_client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000,
            )
            result = parse_output(response.choices[0].message.content)
            print(f"    📦 Batch {batch_num}: {len(result)} articles extracted")
            return result
        except Exception as e:
            if ("429" in str(e) or "rate_limit" in str(e)) and attempt < 2:
                wait = 15 + attempt * 10  # 15s, 25s
                print(f"    ⏳ Rate limited on batch {batch_num}, waiting {wait}s (attempt {attempt+1}/3)...")
                await asyncio.sleep(wait)
            else:
                print(f"    ⚠️ Batch {batch_num} failed: {e}")
                return []
    return []

async def extract_structured_news(company: str, articles: list) -> list:
    """Send raw Tavily articles to LLM in small batches for structured extraction."""
    if not articles:
        return []
    # Sort by Tavily score and take top articles
    articles.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_articles = articles[:6]

    # Split into small batches of BATCH_SIZE
    batches = [top_articles[i:i+BATCH_SIZE] for i in range(0, len(top_articles), BATCH_SIZE)]
    all_extracted = []
    seen_titles = set()

    for idx, batch in enumerate(batches, 1):
        result = await _extract_batch(company, batch, idx)
        for article in result:
            title_key = article.get("title", "").strip().lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                all_extracted.append(article)
        # Wait between batches to respect rate limits
        if idx < len(batches):
            await asyncio.sleep(API_DELAY)

    return all_extracted

async def run():
    print("\n🚀 LPL Financial Competitive Intelligence Pipeline (MCP + Tavily)\n")

    # ─── Step 1: Fetch news via MCP/Tavily ───────────────────────
    print("📡 Step 1: Fetching competitor news via MCP + Tavily...\n")
    all_news = []

    company_articles = {}
    for competitor in COMPETITORS:
        try:
            print(f"  🔎 Searching: {competitor}")
            raw_articles = await get_news_via_mcp(competitor)
            structured    = await extract_structured_news(competitor, raw_articles)
            structured.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            company_articles[competitor] = structured
            print(f"  ✅ {competitor}: {len(structured)} structured articles\n")
        except Exception as e:
            print(f"  ❌ Failed: {competitor} → {e}\n")
        await asyncio.sleep(API_DELAY)

    # Guarantee up to 3 articles per company, sorted by relevance score
    MIN_PER_COMPANY = 3
    for company, articles in company_articles.items():
        # Take up to MIN_PER_COMPANY articles per company (already sorted by relevance)
        all_news.extend(articles[:MIN_PER_COMPANY])

    all_news.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    from collections import Counter
    counts = Counter(a.get("company", "?") for a in all_news)
    print(f"  📊 Final selection: {len(all_news)} articles — {dict(counts)}\n")

    save(all_news, "storage/output/news.json")
    print(f"✅ Step 1 complete: {len(all_news)} articles saved to news.json\n")

    if not all_news:
        print("No news found. Exiting.")
        return

    # ─── Step 2: MCP-based client mapping ────────────────────────
    MAPPING_MIN_RELEVANCE = 0.5
    actionable = [n for n in all_news if n.get("relevance_score", 0) >= MAPPING_MIN_RELEVANCE]
    print(f"🔍 Step 2: Mapping {len(actionable)} actionable articles to LPL clients (MCP tools)...\n")

    clients    = load("data/clients.json")
    client_map = []

    for i, news_item in enumerate(actionable):
        try:
            await asyncio.sleep(API_DELAY)
            matches = await map_news_to_clients(news_item, clients)
            if matches:
                client_map.append({
                    "competitor_news":     news_item,
                    "affected_lpl_clients": matches
                })
                print(f"  🎯 '{news_item.get('title','')[:55]}...' → {len(matches)} clients")
            else:
                print(f"  ⚪ '{news_item.get('title','')[:55]}...' → no match")
        except Exception as e:
            print(f"  ⚠️ Mapping failed for item {i}: {e}")

    save(client_map, "storage/output/client_map.json")
    print(f"\n✅ Step 2 complete: {len(client_map)} mappings saved\n")

    # ─── Step 3: Advisor briefings ───────────────────────────────
    print("📋 Step 3: Generating advisor briefings...\n")
    advisors = {}
    for c in clients:
        aid = c["advisor_id"]
        if aid not in advisors:
            advisors[aid] = {"id": aid, "name": c.get("advisor_name", f"Advisor {aid}")}

    advisor_feeds = []
    for advisor_id, advisor_info in advisors.items():
        try:
            await asyncio.sleep(API_DELAY)
            advisor_client_ids = [c["id"] for c in clients if c["advisor_id"] == advisor_id]
            relevant = [
                m for m in client_map
                if any(mc.get("client_id") in advisor_client_ids
                       for mc in m["affected_lpl_clients"])
            ]
            if not relevant:
                print(f"  ⚪ No alerts for {advisor_info['name']}")
                continue
            feed = await build_advisor_feed(advisor_info, relevant)
            advisor_feeds.append(feed)
            print(f"  📋 Briefing ready for {advisor_info['name']} ({len(relevant)} alerts)")
        except Exception as e:
            print(f"  ⚠️ Briefing failed for {advisor_info['name']}: {e}")

    save(advisor_feeds, "storage/output/advisor_feed.json")
    print(f"\n✅ Step 3 complete: {len(advisor_feeds)} briefings saved")
    print("\n🏁 Done. Check storage/output/ for results.")

if __name__ == "__main__":
    asyncio.run(run())