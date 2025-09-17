# Day05/json_utils.py
import json
import re
from typing import Any, Optional

def extract_json(text: str) -> Optional[str]:
    """
    Extract a JSON object from arbitrary text.
    Tries fenced ```json blocks first, then falls back to the first {...} block.
    """
    if not text:
        return None

    # fenced code block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # first top-level object (greedy balanced braces heuristic)
    # simple heuristic: find first '{' and last '}' and hope content is JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1].strip()

    return None

def parse_json(text: str) -> Any:
    blob = extract_json(text)
    if blob is None:
        raise ValueError("No JSON found in model response")
    return json.loads(blob)
