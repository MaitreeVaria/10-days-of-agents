#!/usr/bin/env python3
from __future__ import annotations
import sys, json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

# -------- Sandbox --------
SANDBOX_ROOT = (Path(__file__).resolve().parents[2] / "out").resolve()
SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 256 * 1024

# -------- Rate limits (per tool, per minute) --------
RL_FILE = Path(__file__).with_name("rate_limit.json")
TOOL_LIMITS = {
    "file_write_safe": 60,  # writes/min
    "file_read_safe": 120,  # reads/min
}

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _minute_key(ts: datetime) -> str:
    return ts.strftime("%Y%m%d%H%M")

def _load_rl() -> Dict[str, Any]:
    if RL_FILE.exists():
        try: return json.loads(RL_FILE.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _save_rl(data: Dict[str, Any]) -> None:
    RL_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _check_rate(tool: str) -> bool:
    limit = TOOL_LIMITS.get(tool)
    if not limit:
        return True
    data = _load_rl()
    tools = data.setdefault("tools", {})
    tdata = tools.setdefault(tool, {})
    key = _minute_key(_now_utc())
    count = int(tdata.get(key, 0))
    if count >= limit:
        return False
    tdata[key] = count + 1
    tools[tool] = tdata
    data["tools"] = tools
    _save_rl(data)
    return True

# -------- RPC helpers --------
def ok(id_, result): return {"id": id_, "ok": True, "result": result}
def err(id_, msg, code="ERR", retryable=False):
    return {"id": id_, "ok": False, "error": msg, "code": code, "retryable": retryable}

# -------- Tool impl --------
def list_tools():
    return [
        {"name": "file_write_safe", "schema": 1},
        {"name": "file_read_safe", "schema": 1},
    ]

def file_write_safe(args: Dict[str, Any]) -> Dict[str, Any]:
    if not _check_rate("file_write_safe"):
        raise RateLimit("file_write_safe")
    path = args.get("path", "")
    text = args.get("text", "")
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise ValueError("invalid path")
    if ".." in Path(path).parts:
        raise ValueError("path traversal not allowed")
    if not isinstance(text, str):
        raise ValueError("text must be string")

    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("payload too large")

    target = (SANDBOX_ROOT / path).resolve()
    try:
        target.relative_to(SANDBOX_ROOT)
    except ValueError:
        raise ValueError("path escapes sandbox")

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"path": f"out/{Path(path).as_posix()}"}

def file_read_safe(args: Dict[str, Any]) -> Dict[str, Any]:
    if not _check_rate("file_read_safe"):
        raise RateLimit("file_read_safe")
    path = args.get("path", "")
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise ValueError("invalid path")
    if ".." in Path(path).parts:
        raise ValueError("path traversal not allowed")

    target = (SANDBOX_ROOT / path).resolve()
    try:
        target.relative_to(SANDBOX_ROOT)
    except ValueError:
        raise ValueError("path escapes sandbox")

    if not target.exists() or target.is_dir():
        raise FileNotFoundError("file not found")
    text = target.read_text(encoding="utf-8", errors="ignore")
    return {"text": text}

class RateLimit(Exception):
    def __init__(self, tool: str):
        super().__init__(f"rate limit exceeded for {tool}")

def main():
    raw = sys.stdin.read()
    if not raw:
        return
    last_line = raw.strip().splitlines()[-1]
    try:
        req = json.loads(last_line)
    except Exception as e:
        print(json.dumps(err(None, f"bad json: {e}")), flush=True)
        return

    mid = req.get("id")
    method = req.get("method")
    if method == "list_tools":
        print(json.dumps(ok(mid, {"tools": list_tools()})), flush=True)
        return

    if method == "call":
        params = req.get("params") or {}
        tool = params.get("tool")
        args = params.get("args") or {}
        try:
            if tool == "file_write_safe":
                res = file_write_safe(args)
            elif tool == "file_read_safe":
                res = file_read_safe(args)
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
