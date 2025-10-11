#!/usr/bin/env python3
from __future__ import annotations
import sys, json, time
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

def ok(id_, result): return {"id": id_, "ok": True, "result": result}
def err(id_, msg, code="ERR", retryable=False):
    return {"id": id_, "ok": False, "error": msg, "code": code, "retryable": retryable}

TOOLS = [{"name": "web_search", "schema": 1}]

# ---- Rate limit: very small to demo breaker ----
RL_FILE = Path(__file__).with_name("rate_limit.json")
TOOL_LIMITS = {"web_search": 3}  # 3 calls/min triggers RL quickly

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

STUB_DB = {
    "mcp": [
        {"title": "Model Context Protocol (spec)", "url": "https://github.com/modelcontextprotocol/spec",
         "snippet": "MCP standardizes how AI agents and tools communicate."},
        {"title": "Intro to MCP", "url": "https://openai.com/index/model-context-protocol/",
         "snippet": "Overview and motivation for MCP as a tool interface."},
        {"title": "Why MCP matters", "url": "https://example.com/mcp-overview",
         "snippet": "Portability, safety, orchestration benefits."}
    ]
}

def web_search(args: Dict[str, Any]):
    if not _check_rate("web_search"):
        raise RateLimit("web_search")
    q = (args.get("query") or "").strip().lower()
    k = int(args.get("top_k", 3))
    if not q: return {"hits": []}
    hits = STUB_DB.get(q, STUB_DB["mcp"])[:k]
    time.sleep(0.05)
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
        print(json.dumps(ok(mid, {"tools": TOOLS})), flush=True); return
    if method == "call":
        p = req.get("params") or {}; tool = p.get("tool"); args = p.get("args") or {}
        try:
            if tool == "web_search":
                res = web_search(args)
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
