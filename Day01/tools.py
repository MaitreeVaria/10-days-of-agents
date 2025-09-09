import os, glob, re

def calculator(expr: str) -> dict:
    """Evaluate safe math expressions with support for percentages.

    Returns:
        {"ok": True, "result": float} on success
        {"ok": False, "error": str} on failure
    """
    # 1. Basic validation
    if not expr or len(expr) > 200:
        return {"ok": False, "error": "Invalid input length"}

    # 2. Allow only digits, ., + - * / ( ), %, spaces, and "of"
    safe_pattern = r"^[0-9\.\+\-\*\/\(\)\s%ofOF]+$"
    if not re.fullmatch(safe_pattern, expr):
        return {"ok": False, "error": "Unsafe characters in expression"}

    # 3. Handle "20% of 50" → "(20/100)*50"
    expr2 = re.sub(
        r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)",
        lambda m: f"({float(m.group(1))/100}*{m.group(2)})",
        expr,
        flags=re.I
    )

    # 4. Handle standalone "20%" → "(20/100)"
    expr2 = re.sub(
        r"(\d+(?:\.\d+)?)\s*%",
        lambda m: f"({float(m.group(1))/100})",
        expr2
    )

    # 5. Evaluate safely
    try:
        result = eval(expr2, {"__builtins__": {}}, {})
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}



def local_search(query: str, top_k: int = 3) -> dict:
    """Search ./data/*.md for query terms and return filenames + snippets.

    Returns:
      {"ok": True, "results": [{"file": "...", "snippet": "..."}]}
      or {"ok": False, "error": "..."}
    """
    # 1) basic input checks
    if not isinstance(query, str):
        return {"ok": False, "error": "Query must be a string"}
    q = query.strip()
    if not q or len(q) > 200:
        return {"ok": False, "error": "Invalid input length (min:1, max:200)"}

    # 2) tokenize query into simple lowercase terms
    terms = re.findall(r"\w+", q.lower())
    if not terms:
        return {"ok": False, "error": "No searchable terms in query"}

    # 3) find markdown files under ./data
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    files = glob.glob(os.path.join(data_dir, "*.md"))

    hits = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                text = f.read()
            text_lower = text.lower()

            # 4) simple score = sum of occurrences of each term
            score = sum(text_lower.count(t) for t in terms)

            if score > 0:
                # 5) locate first occurrence of any term for snippet
                first_idx = min(
                    (text_lower.find(t) for t in terms if text_lower.find(t) != -1),
                    default=-1
                )
                # build a short snippet around the first match
                if first_idx != -1:
                    start = max(0, first_idx - 60)
                    end = min(len(text), first_idx + 160)
                    snippet = text[start:end].replace("\n", " ").strip()
                else:
                    snippet = text[:200].replace("\n", " ").strip()

                hits.append({
                    "score": score,
                    "file": os.path.basename(fp),
                    "snippet": snippet
                })
        except Exception as e:
            # ignore unreadable files; you could also return an error if you prefer
            continue

    # 6) sort & truncate
    hits.sort(key=lambda h: h["score"], reverse=True)
    results = [{"file": h["file"], "snippet": h["snippet"]} for h in hits[:max(1, int(top_k))]]

    return {"ok": True, "results": results}