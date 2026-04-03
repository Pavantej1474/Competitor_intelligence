import json

def build_mapping_prompt(news_item: dict, clients: list) -> str:
    return f"""You are a competitive intelligence analyst at **LPL Financial**.

A COMPETITOR has made a move. Your job is to analyze which LPL Financial clients might be AT RISK of being attracted by this competitor's offering, or where a RETENTION OPPORTUNITY exists for the LPL advisor to proactively engage.

All clients below are current LPL Financial clients. You must INFER the risk by reasoning about:
- Does the competitor's offering address this client's **pain_points**?
- Does this news relate to the client's **interests**, **sectors**, or **holdings**?
- Would this client's **account_type** or **risk_profile** make them a natural target for this competitor's move?
- Does the client hold stock in the competitor (e.g. holdings include "GS" and news is about Goldman Sachs)?

--- COMPETITOR NEWS ---
{json.dumps(news_item, indent=2)}
--- END NEWS ---

--- LPL FINANCIAL CLIENT PROFILES ---
{json.dumps(clients, indent=2)}
--- END CLIENTS ---

ANALYSIS RULES:
1. A client is "at_risk" if:
   - The competitor's new product, feature, or service DIRECTLY addresses one or more of the client's **pain_points** (this is the strongest signal)
   - The client's **interests** closely match what the competitor is specifically launching or changing
   - The client's **sectors** + **account_type** together make them a natural target
2. A client is a "retention_opportunity" if:
   - The competitor news reveals a WEAKNESS (staff cuts, lawsuits, platform outage, data breach) AND the client has a pain_point or interest that LPL can address proactively
   - LPL can concretely match or beat what the competitor is offering
3. STRICT ANTI-MATCHING RULES (very important):
   - Do NOT match a client JUST because they hold the competitor's stock. Holding GS stock does NOT mean a client is "at risk" from a Goldman Sachs news article — the news must address a specific client NEED.
   - Do NOT match if the connection is vague or generic (e.g., "news is about Goldman Sachs and client holds GS" is NOT a valid match)
   - Do NOT match more than 3-4 clients per news item. If you find yourself matching 5+, you are being too loose — tighten your criteria.
   - Do NOT match on articles about personal stories, career transitions, stock ratings, or opinion pieces — these have ZERO client impact.
4. QUALITY OVER QUANTITY: It is better to return 1-2 strong matches than 5 weak ones.
5. Be SPECIFIC — cite the exact pain_point or interest that creates the connection. The match_reason MUST reference a specific field value from the client profile.

RETURN ONLY a valid JSON array. No markdown, no explanation.
If no clients are affected, return []

SCHEMA:
[
  {{
    "client_id": "C001",
    "client_name": "Name",
    "risk_type": "at_risk | retention_opportunity",
    "urgency": "high | medium | low",
    "competitor": "Which competitor this relates to",
    "match_reason": "Cite the specific client attribute (pain_point, interest, holding, sector) that connects to this competitor news",
    "suggested_action": "What the LPL advisor should do — be concrete (e.g. schedule call, demo LPL alternative, review portfolio)",
    "talking_points": ["What to say to the client", "How LPL compares or can do better"]
  }}
]"""