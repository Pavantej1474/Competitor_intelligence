import json

def build_advisor_summary_prompt(advisor: dict, at_risk_mappings: list) -> str:
    return f"""You are preparing a **Competitive Intelligence Briefing** for LPL Financial advisor **{advisor['name']}** (ID: {advisor['id']}).

This advisor manages clients at LPL Financial. Below are recent competitor moves that have been mapped to their specific clients who are either AT RISK of being poached or where a RETENTION OPPORTUNITY exists.

--- CLIENT RISK MAPPINGS ---
{json.dumps(at_risk_mappings, indent=2)}
--- END MAPPINGS ---

Create an actionable daily briefing that helps this LPL advisor protect and retain their clients.

RETURN ONLY valid JSON. No markdown, no explanation.

SCHEMA:
{{
  "advisor_id": "{advisor['id']}",
  "advisor_name": "{advisor['name']}",
  "firm": "LPL Financial",
  "briefing_date": "2026-04-02",
  "priority_alerts": [
    {{
      "client_name": "",
      "client_id": "",
      "risk_level": "high | medium | low",
      "alert_type": "at_risk | retention_opportunity",
      "competitor": "Which competitor is involved",
      "headline": "One-line summary: what happened and why it matters for this client",
      "recommended_action": "Specific next step for the LPL advisor",
      "talking_points": ["What to say to the client", "How LPL compares or can do better"],
      "deadline": "When to act by"
    }}
  ],
  "competitive_landscape": "2-3 sentence summary of what competitors are doing and how it impacts LPL's position",
  "retention_strategies": ["Specific strategy 1 to keep clients at LPL", "Strategy 2"]
}}"""