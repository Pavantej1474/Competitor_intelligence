import json
import re

def _fix_json_string(json_str: str) -> str:
    """Clean common LLM JSON issues like trailing commas."""
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    return json_str

def _try_parse_json(json_str: str) -> list | None:
    """Try to parse JSON, with multiple fallback strategies."""
    # Strategy 1: Direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Fix trailing commas
    try:
        return json.loads(_fix_json_string(json_str))
    except json.JSONDecodeError:
        pass

    # Strategy 3: If truncated (no closing ]), try to close it
    stripped = json_str.rstrip()
    if stripped and not stripped.endswith(']'):
        # Find the last complete object (ending with })
        last_brace = stripped.rfind('}')
        if last_brace > 0:
            attempt = stripped[:last_brace + 1] + ']'
            try:
                return json.loads(_fix_json_string(attempt))
            except json.JSONDecodeError:
                pass

    # Strategy 4: Extract individual JSON objects and build array
    objects = []
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', json_str):
        try:
            obj = json.loads(_fix_json_string(m.group(0)))
            if isinstance(obj, dict):
                objects.append(obj)
        except json.JSONDecodeError:
            continue
    if objects:
        return objects

    return None

# Minimum relevance score to keep an article — filters out junk
MIN_RELEVANCE = 0.3

def _validate_article(article: dict) -> bool:
    """Check that an article has required fields and is not junk."""
    # Must have a non-null company
    if not article.get("company"):
        return False
    # Must have a title
    if not article.get("title"):
        return False
    # Must have at least a summary
    if not article.get("summary"):
        return False
    # Reject articles below relevance threshold (filters out tangential mentions)
    if article.get("relevance_score", 0) < MIN_RELEVANCE:
        return False
    return True

def parse_output(output):
    try:
        # Extract JSON array using regex
        match = re.search(r'\[.*\]', output, re.DOTALL)

        if match:
            json_str = match.group(0)
            items = _try_parse_json(json_str)

            if items is None:
                # Fallback: try the full output
                items = _try_parse_json(output)

            if items is None:
                print("⚠️ All JSON parse strategies failed")
                return []
        else:
            # No array brackets found — try to recover objects from raw output
            items = _try_parse_json(output)
            if items is None:
                # Last resort: find any JSON-like content
                items = _try_parse_json("[" + output + "]")
                if items is None:
                    print("⚠️ No JSON found in output")
                    return []

        if not isinstance(items, list):
            items = [items] if isinstance(items, dict) else []

        # Validate and deduplicate
        seen_titles = set()
        valid = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if not _validate_article(item):
                continue
            title = item.get("title", "").strip().lower()
            if title in seen_titles:
                continue
            seen_titles.add(title)
            valid.append(item)

        if len(items) > len(valid):
            print(f"  🔍 Parsed {len(items)} articles, {len(valid)} passed validation (filtered {len(items) - len(valid)})")
        return valid

    except Exception as e:
        print("⚠️ JSON parsing failed:", e)
        return []