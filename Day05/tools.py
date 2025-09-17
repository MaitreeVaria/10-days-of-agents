import os, glob, re
from typing import List, Dict
from pathlib import Path

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


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

def _iter_files():
    for root, _, files in os.walk(DATA_DIR):
        for fn in files:
            if any(fn.endswith(ext) for ext in (".md", ".txt", ".py")):
                yield os.path.join(root, fn)

def _score_hit(text: str, query: str) -> int:
    # naive score = count of case-insensitive keyword occurrences
    return len(re.findall(re.escape(query), text, flags=re.IGNORECASE))

def _snippet(text: str, query: str, size: int = 160) -> str:
    m = re.search(re.escape(query), text, re.IGNORECASE)
    if not m:
        return text[:size]
    i = max(0, m.start() - size // 2)
    j = i + size
    return text[i:j].replace("\n", " ")


def search_local_docs(query: str, top_k: int = 3) -> List[Dict]:
    """Search ./data for a keyword and return top snippets."""
    query = (query or "").strip()
    if not query:
        return []  # or [{"error": "missing query"}] if you prefer
    try:
        k = max(1, min(int(top_k), 10))  # small bound
    except Exception:
        k = 3

    results = []
    for path in _iter_files():
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            continue
        score = _score_hit(text, query)
        if score > 0:
            results.append({
                "title": os.path.basename(path),
                "snippet": _snippet(text, query),
                "path": os.path.relpath(path, DATA_DIR),
                "score": score,
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:k]



# Allowlist root for writes
OUT_DIR = (Path(__file__).resolve().parent / "out").resolve()

# Limit to keep payloads small/safe (64 KB is plenty for Day 5)
MAX_BYTES = 64 * 1024  # 64 KiB

def file_write_safe(path: str, text: str) -> dict:
    """
    Safely write UTF-8 text to a file under day05/out/.
    Returns {"ok": True, "bytes": <int>} or {"ok": False, "error": <str>}.
    Guardrails:
      - Allow writes ONLY inside OUT_DIR
      - Reject absolute paths and traversal (..)
      - Enforce size limit (MAX_BYTES)
      - Text only (str)
    """
    # Basic input checks
    if not isinstance(path, str) or not path.strip():
        return {"ok": False, "error": "invalid path"}
    if not isinstance(text, str):
        return {"ok": False, "error": "text must be a string"}
    p_norm = path.replace("\\", "/")
    low = p_norm.lower()
    marker = "/out/"
    if low.startswith("out/"):
        p_norm = p_norm[4:]
    else:
        idx = low.rfind(marker)
        if idx != -1:
            p_norm = p_norm[idx + len(marker):]

    # Replace the original path with the normalized one
    path = p_norm.strip()
    # Size check (bytes, not characters)
    data = text.encode("utf-8", errors="strict")
    if len(data) > MAX_BYTES:
        return {"ok": False, "error": f"payload too large (> {MAX_BYTES} bytes)"}

    try:
        # Ensure out dir exists
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        # Compute the target path IN the allowlisted folder
        # Using resolve() to collapse any .. elements and symlinks
        target = (OUT_DIR / path).resolve()

        # Enforce sandbox: final resolved path must be inside OUT_DIR
        # Path.is_relative_to is 3.9+, emulate for older versions:
        try:
            target.relative_to(OUT_DIR)
        except ValueError:
            return {"ok": False, "error": "path escapes allowed directory"}

        # Disallow writing to directories
        if target.exists() and target.is_dir():
            return {"ok": False, "error": "target is a directory"}

        # Make subdirectories under OUT_DIR if needed
        target.parent.mkdir(parents=True, exist_ok=True)

        # Write text (overwrite if exists)
        with target.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        return {"ok": True, "bytes": len(data)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
