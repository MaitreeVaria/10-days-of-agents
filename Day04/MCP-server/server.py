# Day04/mcp-server/server.py
from mcp.server.fastmcp import FastMCP
import shlex, subprocess
from typing import List, Dict
import os, re

mcp = FastMCP("My Demo MCP")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

def _auth_ok(meta: dict | None) -> bool:
    # FastMCP passes request metadata via thread-local context; easiest hack:
    # require the token at process start (env variable)
    return bool(AUTH_TOKEN)

# Call this early (module import time)
if not _auth_ok(None):
    # You can still start the process, but tools will reject calls.
    pass

def _require_auth() -> Dict | None:
    if not AUTH_TOKEN:
        return {"error": "unauthorized: server missing MCP_AUTH_TOKEN"}
    return None

def _iter_files():
    print(print(DATA_DIR))
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

@mcp.tool()
def search_local_docs(query: str, top_k: int = 3) -> List[Dict]:
    """Search ./data for a keyword and return top snippets."""
    err = _require_auth()
    if err:
        return [err]
    query = (query or "").strip()
    if not query:
        return [{"error": "missing query"}]
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
    return results[: max(1, int(top_k))]


BLOCKED_PATTERNS = ("|", "&&", ";", ">", "<", "`", "$(", "*", "sudo", "rm", "chmod", "chown")

@mcp.tool()
def run_shell_safe(cmd: str, timeout_s: int = 3) -> Dict:
    """Run whitelisted shell commands: echo, ls. Reject anything else."""
    err = _require_auth()
    if err:
        return [err]
    cmd = (cmd or "").strip()
    if not cmd:
        return {"error": "missing cmd"}

    # prevent obvious injections
    if any(p in cmd for p in BLOCKED_PATTERNS):
        return {"error": "disallowed syntax"}

    parts = shlex.split(cmd)
    if not parts:
        return {"error": "empty command"}
    allowed = {"echo", "ls"}
    if parts[0] not in allowed:
        return {"error": f"command '{parts[0]}' not allowed"}

    try:
        p = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_s)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}

    out = (p.stdout or "") + (("\nERR:\n" + p.stderr) if p.stderr else "")
    # trim to keep responses small/safe
    if len(out) > 2000:
        out = out[:2000] + "\n…(truncated)"
    return {"code": p.returncode, "output": out}


if __name__ == "__main__":
    # simplest direct exec; works fine for local dev
    mcp.run()  # transport defaults to stdio when invoked via an MCP client
