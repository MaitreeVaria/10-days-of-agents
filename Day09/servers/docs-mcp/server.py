#!/usr/bin/env python3
from __future__ import annotations
import sys, json, re
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]  # repo root
SEARCH_DIRS = [ROOT / "Day07", ROOT / "Day08"]

def ok(id_, result): return {"id": id_, "ok": True, "result": result}
def err(id_, msg, code="ERR", retryable=False):
    return {"id": id_, "ok": False, "error": msg, "code": code, "retryable": retryable}

# ---- Rate limit ----
RL_FILE = Path(__file__).with_name("rate_limit.json")
TOOL_LIMITS = {"search_local_docs": 10}  # calls/min

def _now_utc(): return datetime.now(timezone.utc)
def _minute_key(ts): return ts.strftime("%Y%m%d%H%M")
def _load_rl():
    if RL_FILE.exists():
        try: return json.loads(RL_FILE.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}
def _save_rl(d): RL_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
def _check_rate(tool: str) -> bool:
    lim = TOOL_LIMITS.get(tool)
    if not lim: return True
    d = _load_rl(); tools = d.setdefault("tools", {}); t = tools.setdefault(tool, {})
    key = _minute_key(_now_utc())
    cnt = int(t.get(key, 0))
    if cnt >= lim: return False
    t[key] = cnt + 1; tools[tool] = t; d["tools"] = tools; _save_rl(d); return True

def list_tools():
    return [{"name": "search_local_docs", "schema": 1}]

def _collect_files() -> List[Path]:
    files = []
    for base in SEARCH_DIRS:
        if not base.exists(): continue
        for p in base.rglob("*.md"):
            files.append(p)
    return files

def search_local_docs(args: Dict[str, Any]) -> Dict[str, Any]:
    if not _check_rate("search_local_docs"):
        raise RateLimit("search_local_docs")
    q = (args.get("query") or "").strip()
    k = int(args.get("top_k", 5))
    if not q: return {"hits": []}
    rx = re.compile(re.escape(q), re.IGNORECASE)
    hits = []
    for fp in _collect_files():
        try:
            txt = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if rx.search(txt):
            lines = [ln for ln in txt.splitlines() if rx.search(ln)]
            snippet = " | ".join(lines[:3])
            rel = fp.relative_to(ROOT).as_posix()
            hits.append({"path": rel, "snippet": snippet})
            if len(hits) >= k:
                break
    return {"hits": hits}

class RateLimit(Exception): ...

def main():
    raw = sys.stdin.read()
    if not raw: return
    last_line = raw.strip().splitlines()[-1]
    try:
        req = json.loads(last_line)
    except Exception as e:
        print(json.dumps(err(None, f"bad json: {e}")), flush=True); return

    mid = req.get("id"); method = req.get("method")
    if method == "list_tools":
        print(json.dumps(ok(mid, {"tools": list_tools()})), flush=True); return
    if method == "call":
        p = req.get("params") or {}; tool = p.get("tool"); args = p.get("args") or {}
        try:
            if tool == "search_local_docs":
                res = search_local_docs(args)
            else:
                print(json.dumps(err(mid, f"unknown tool: {tool}")), flush=True); return
            print(json.dumps(ok(mid, res)), flush=True)
        except RateLimit:
            print(json.dumps(err(mid, "rate limit", code="RATE_LIMIT")), flush=True)
        except Exception as e:
            print(json.dumps(err(mid, str(e))), flush=True)
        return
    print(json.dumps(err(mid, f"unknown method: {method}")), flush=True)

if __name__ == "__main__":
    main()
