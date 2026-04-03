# prompts/news_prompt.py
import json

CHANGE_TYPES = [
    "fee_reduction", "fee_increase", "fee_waiver", "commission_change", "penalty_change", "expense_ratio_change",
    "new_fund_launch", "new_account_type", "new_card_launch", "new_loan_product", "new_insurance_product",
    "product_discontinuation", "product_merger",
    "app_feature_update", "platform_launch", "api_integration", "ai_tool_launch",
    "security_update", "platform_migration", "platform_outage",
    "interest_rate_change", "dividend_change", "yield_change", "apy_change", "loan_rate_change",
    "signup_bonus", "referral_program", "loyalty_reward_change", "promotional_rate",
    "benefit_addition", "benefit_removal", "eligibility_change",
    "new_partnership", "partnership_ended", "acquisition", "merger", "distribution_expansion",
    "regulatory_approval", "regulatory_action", "compliance_requirement", "tax_rule_change", "kyc_aml_update",
    "advisor_tool_launch", "advisor_compensation_change", "advisor_training_program",
    "model_portfolio_change", "research_report_launch",
    "new_market_access", "geographic_expansion", "geographic_restriction", "fractional_shares", "trading_hours_change",
    "data_breach", "fraud_alert", "fund_closure", "margin_requirement_change", "rating_downgrade",
]

URGENT_TYPES = {"fee_increase","benefit_removal","fund_closure","data_breach","product_discontinuation","platform_outage","fraud_alert","regulatory_action","rating_downgrade","margin_requirement_change"}
HIGH_TYPES   = {"fee_reduction","new_fund_launch","acquisition","merger","partnership_ended","eligibility_change","penalty_change","expense_ratio_change"}
MEDIUM_TYPES = {"new_partnership","app_feature_update","promotional_rate","signup_bonus","benefit_addition","new_card_launch","new_loan_product","new_insurance_product","new_account_type","interest_rate_change","apy_change","loan_rate_change","loyalty_reward_change","referral_program","geographic_expansion","geographic_restriction","new_market_access","fractional_shares","trading_hours_change","distribution_expansion","regulatory_approval","compliance_requirement","tax_rule_change","kyc_aml_update","platform_migration","security_update","api_integration"}
INFO_TYPES   = {"advisor_tool_launch","research_report_launch","platform_launch","ai_tool_launch","advisor_compensation_change","advisor_training_program","model_portfolio_change","new_fund_launch","fee_waiver","commission_change","dividend_change","yield_change","product_merger"}

def get_priority(change_type: str) -> str:
    if change_type in URGENT_TYPES: return "urgent"
    if change_type in HIGH_TYPES:   return "high"
    if change_type in MEDIUM_TYPES: return "medium"
    return "informational"

def build_prompt_from_articles(company: str, articles: list[dict]) -> str:
    """Takes raw Tavily articles and extracts structured news JSON."""
    change_types_str = ", ".join(CHANGE_TYPES)

    # Trim content to avoid token limits
    trimmed = []
    for a in articles:
        t = dict(a)
        content = t.get("content", "") or ""
        t["content"] = content[:400] + "..." if len(content) > 400 else content
        trimmed.append(t)

    return f"""You are a financial product intelligence analyst. Extract structured news from these articles about **{company}**.

--- ARTICLES ---
{json.dumps(trimmed, indent=2)}
--- END ---

RULES:
1. Extract EVERY article that is even somewhat about {company}'s financial products, services, or client-facing operations.
2. Be INCLUSIVE — extract as many articles as possible. Better to include a borderline article than miss it.
3. SKIP ONLY: pure stock price commentary, earnings calls with no product info, personal human interest stories.
4. "company" MUST be "{company}". Use "Not specified" for unknown fields, never null.
5. If no relevant articles, return []
6. Do NOT hallucinate. Only use facts from the articles.
7. Each input article should produce one output item if it has any relevance to {company}'s services.

CHANGE TYPES (pick one): {change_types_str}

Return ONLY valid JSON array, no markdown:
[
  {{
    "company": "{company}",
    "title": "exact article title",
    "source": "publication name",
    "url": "article URL",
    "published_date": "YYYY-MM-DD",
    "change_type": "from list above",
    "summary": "one-sentence TL;DR",
    "description": "full detailed breakdown — include all specific numbers, dates, features, eligibility criteria, executive quotes",
    "client_impact": "who benefits, who loses, what action clients need to take and by when",
    "competitor_context": "comparison to LPL Financial or other competitors, or 'Not specified'",
    "sentiment": "opportunity | risk | neutral",
    "sentiment_reason": "one sentence why this matters for LPL advisors",
    "tags": ["relevant", "categories"],
    "relevance_score": 0.0
  }}
]

RELEVANCE: 0.9-1.0=direct fee/benefit change, 0.7-0.8=new product/platform, 0.5-0.6=partnership/feature, 0.3-0.4=informational"""