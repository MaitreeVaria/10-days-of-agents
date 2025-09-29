from __future__ import annotations
import subprocess, json, time, hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import yaml
from datetime import datetime, timezone

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _ts() -> float:
    return _utc_now().timestamp()

class MCPClient:
    """
    Minimal stdio MCP client with:
      - per-tool circuit breaker
      - per-tool+args response cache
    State persists under Day08/client/.state/
    """

    def __init__(self, registry_path: Path):
        self.registry_path = Path(registry_path).resolve()
        with self.registry_path.open("r", encoding="utf-8") as f:
            self.reg = yaml.safe_load(f)
        self._tool_index = self._build_index(self.reg)

        # Resolve Day08 root = <registry>/..
        self.root = self.registry_path.parent.parent
        self.state_dir = self.root / "client" / ".state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.breaker_file = self.state_dir / "breaker.json"
        self.cache_file = self.state_dir / "cache.json"
        self._breaker = self._load_json(self.breaker_file) or {}
        self._cache = self._load_json(self.cache_file) or {}

        # breaker params
        self.BREAKER_THRESHOLD = 3      # failures
        self.BREAKER_WINDOW_SEC = 60    # seconds
        self.BREAKER_COOLDOWN_SEC = 30  # seconds

        # cache params
        self.CACHE_TTL_SEC = 60
        self.CACHE_TOOLS = {"web_search", "search_local_docs"}  # cache read-only tools

    # ---------- index ----------
    @staticmethod
    def _build_index(reg: Dict[str, Any]) -> Dict[str, Tuple[str, Dict[str, Any]]]:
        index = {}
        servers = reg.get("servers", {})
        for sid, s in servers.items():
            for t in s.get("tools", []):
                index[t["name"]] = (sid, s)
        return index

    # ---------- utils ----------
    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return None

    def _save_json(self, path: Path, obj: Dict[str, Any]) -> None:
        path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def _cache_key(self, tool: str, args: Dict[str, Any]) -> str:
        blob = json.dumps({"tool": tool, "args": args}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ---------- breakers ----------
    def _get_breaker(self, tool: str) -> Dict[str, Any]:
        return self._breaker.setdefault(tool, {"failures": [], "state": "closed", "opened_at": 0.0})

    def _record_failure(self, tool: str) -> None:
        b = self._get_breaker(tool)
        now = _ts()
        # drop old failures
        b["failures"] = [t for t in b["failures"] if now - t <= self.BREAKER_WINDOW_SEC]
        b["failures"].append(now)
        if len(b["failures"]) >= self.BREAKER_THRESHOLD and b["state"] != "open":
            b["state"] = "open"
            b["opened_at"] = now
        self._breaker[tool] = b
        self._save_json(self.breaker_file, self._breaker)

    def _record_success(self, tool: str) -> None:
        b = self._get_breaker(tool)
        b["failures"] = []
        b["state"] = "closed"
        b["opened_at"] = 0.0
        self._breaker[tool] = b
        self._save_json(self.breaker_file, self._breaker)

    def _precheck_breaker(self, tool: str) -> Tuple[str, bool]:
        """
        Returns (state, allow_call)
        state: 'closed' | 'open' | 'half_open'
        allow_call: whether to proceed to server
        """
        b = self._get_breaker(tool)
        if b["state"] == "open":
            now = _ts()
            if now - b["opened_at"] < self.BREAKER_COOLDOWN_SEC:
                return "open", False
            else:
                # cooldown elapsed -> half-open (single trial)
                return "half_open", True
        return "closed", True

    # ---------- public ----------
    def list_tools(self, server_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        sid, server = server_id, self.reg["servers"][server_id]
        return self._rpc_once(server, {"id": 1, "method": "list_tools"}, timeout)

    def mcp_call(self, tool: str, args: Dict[str, Any], timeout: float = 15.0, use_cache: bool = True) -> Dict[str, Any]:
        if tool not in self._tool_index:
            return {"ok": False, "error": f"tool not in registry: {tool}", "server_id": None}

        sid, server = self._tool_index[tool]

        # Cache pre-check
        cache_flag = "miss"
        if use_cache and tool in self.CACHE_TOOLS:
            key = self._cache_key(tool, args)
            entry = self._cache.get(key)
            if entry and (_ts() - float(entry["ts"])) <= self.CACHE_TTL_SEC:
                return {
                    "ok": True,
                    "server_id": sid,
                    "latency_ms": 0,
                    "result": entry["result"],
                    "from_cache": True,
                    "circuit": "closed"
                }

        # Circuit breaker pre-check
        circuit_state, allow = self._precheck_breaker(tool)
        if not allow:
            return {"ok": False, "server_id": sid, "latency_ms": 0, "error": "circuit open", "code": "CIRCUIT_OPEN",
                    "circuit": "open", "from_cache": False}

        # RPC
        t0 = time.time()
        req = {"id": 1, "method": "call", "params": {"tool": tool, "args": args}}
        resp = self._rpc_once(server, req, timeout)
        dt = int((time.time() - t0) * 1000)

        # Normalize + breaker/cache updates
        if not resp.get("ok"):
            self._record_failure(tool)
            return {
                "ok": False, "server_id": sid, "latency_ms": dt,
                "error": resp.get("error"), "code": resp.get("code"),
                "circuit": self._get_breaker(tool)["state"], "from_cache": False
            }

        # success
        self._record_success(tool)

        result = {"ok": True, "server_id": sid, "latency_ms": dt, "result": resp.get("result"),
                  "circuit": self._get_breaker(tool)["state"], "from_cache": False}

        # Cache save
        if use_cache and tool in self.CACHE_TOOLS:
            key = self._cache_key(tool, args)
            self._cache[key] = {"ts": _ts(), "result": resp.get("result")}
            self._save_json(self.cache_file, self._cache)

        return result

    # ---------- stdio transport ----------
    def _rpc_once(self, server: Dict[str, Any], req_obj: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        cmd = server["command"]; cwd = server["cwd"]
        proc = subprocess.Popen(
            cmd, cwd=str(Path(cwd)),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            req_line = json.dumps(req_obj) + "\n"
            out, err = proc.communicate(input=req_line, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"ok": False, "error": "timeout", "code": "TIMEOUT"}
        except Exception as e:
            proc.kill()
            return {"ok": False, "error": str(e)}
        lines = [ln for ln in (out or "").splitlines() if ln.strip()]
        if not lines:
            return {"ok": False, "error": f"no response; stderr={err.strip() if err else ''}"}
        try:
            resp = json.loads(lines[-1])
        except Exception as e:
            return {"ok": False, "error": f"bad json: {e}; raw={lines[-1][:200]}"}
        return resp
