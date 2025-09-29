from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import datetime

def _now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False

class Blackboard:
    """
    Minimal file-backed blackboard:
      base_dir/blackboard/storage.json       (live state)
      base_dir/blackboard/snapshots/*.json   (snapshots)
      base_dir/out/                          (artifacts)
    """

    def __init__(self, base_dir: Path, task_spec: Dict[str, Any], fresh: bool = False) -> None:
        self.base_dir = base_dir.resolve()
        self.bb_dir = (self.base_dir / "blackboard")
        self.out_dir = (self.base_dir / "out")
        self.snapshots_dir = (self.bb_dir / "snapshots")
        self.bb_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        self.storage_path = self.bb_dir / "storage.json"
        if fresh or not self.storage_path.exists():
            self.data: Dict[str, Any] = {
                "run_id": f"run-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
                "version": "0.3",
                "started_at": _now_iso(),
                "updated_at": _now_iso(),
                "task": task_spec,
                "subtasks": [],        # [{id, owner, kind, status, input, output, attempts, depends_on, started_at, finished_at}]
                "artifacts": [],       # [{id, type, name, path (out/..), version, owner}]
                "messages": [],        # [{id, role, type, content, refs, ts}]
                "decisions": [],
                "event_log": [],
                "locks": {},           # {key: owner}
                "metrics": {"steps": 0, "tool_calls": 0, "elapsed_seconds": 0},
            }
            self._counters: Dict[str, int] = {"e": 0, "st": 0, "m": 0, "a": 0, "d": 0}
            self.append_event("checkpoint", "supervisor", "Initialized blackboard", refs=[], delta={})
            self.save()
        else:
            with self.storage_path.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
            # rebuild counters approximately from existing ids
            self._counters = {"e": 0, "st": 0, "m": 0, "a": 0, "d": 0}
            for k, pref in [("event_log", "e"), ("subtasks", "st"), ("messages", "m"), ("artifacts", "a"), ("decisions", "d")]:
                maxn = 0
                for item in self.data.get(k, []):
                    try:
                        n = int(str(item.get("id", "x-000"))[-3:])
                        maxn = max(maxn, n)
                    except Exception:
                        pass
                self._counters[pref] = maxn

    # ---------- core I/O ----------
    def save(self) -> None:
        self._touch()
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def snapshot(self, name: str) -> Path:
        p = self.snapshots_dir / f"{name}.json"
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        return p

    # ---------- counters / ids ----------
    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]:03d}"

    def _touch(self) -> None:
        self.data["updated_at"] = _now_iso()

    # ---------- logging ----------
    def append_event(self, kind: str, who: str, what: str, refs: Optional[List[str]] = None, delta: Optional[Dict[str, Any]] = None) -> str:
        eid = self._next_id("e")
        self.data["event_log"].append({
            "id": eid, "kind": kind, "who": who, "what": what, "at": _now_iso(),
            "refs": refs or [], "delta": delta or {}
        })
        return eid

    def add_message(self, role: str, type_: str, content: str, refs: Optional[List[str]] = None) -> str:
        mid = self._next_id("m")
        self.data["messages"].append({
            "id": mid, "role": role, "type": type_, "content": content, "refs": refs or [], "ts": _now_iso()
        })
        self.append_event("message", role, f"{type_}: {content}", refs=[mid] + (refs or []))
        return mid

    # ---------- subtasks ----------
    def add_subtask(self, owner: str, kind: str, input_payload: Dict[str, Any], depends_on: Optional[List[str]] = None) -> str:
        st_id = self._next_id("st")
        st = {
            "id": st_id, "owner": owner, "kind": kind, "status": "queued",
            "input": input_payload, "output": {"summary": "", "artifacts": [], "citations": []},
            "attempts": 0, "started_at": None, "finished_at": None, "depends_on": depends_on or []
        }
        self.data["subtasks"].append(st)
        self.append_event("state_change", "supervisor", f"Added subtask {st_id}", refs=[st_id])
        return st_id

    def update_subtask(self, st_id: str, **fields: Any) -> None:
        st = self.get_subtask(st_id)
        before = {k: st.get(k) for k in ("status", "attempts", "started_at", "finished_at")}
        st.update(fields)
        after = {k: st.get(k) for k in ("status", "attempts", "started_at", "finished_at")}
        self.append_event("state_change", st.get("owner", "unknown"), f"Updated subtask {st_id}", refs=[st_id], delta={"before": before, "after": after})

    def get_subtask(self, st_id: str) -> Dict[str, Any]:
        for st in self.data["subtasks"]:
            if st["id"] == st_id:
                return st
        raise KeyError(f"subtask not found: {st_id}")

    # ---------- artifacts & locks ----------
    def add_artifact(self, type_: str, name: str, path: str, content_ref: Optional[str] = None, owner: Optional[str] = None) -> str:
        # must be "out/..." and live under self.out_dir on disk
        p = (self.base_dir / path).resolve()
        if not path.replace("\\", "/").startswith("out/"):
            raise ValueError("artifact path must start with 'out/'")
        if not _is_under(p, self.out_dir):
            raise ValueError(f"artifact path must be under {self.out_dir}, got {p}")

        aid = self._next_id("a")
        self.data["artifacts"].append({
            "id": aid, "type": type_, "name": name, "path": path, "content_ref": content_ref, "version": 1, "owner": owner
        })
        self.append_event("io", owner or "unknown", f"Registered artifact {name}", refs=[aid, path])
        return aid

    def lock(self, key: str, owner: str) -> None:
        if key in self.data["locks"]:
            raise RuntimeError(f"Lock exists for {key} owned by {self.data['locks'][key]}")
        self.data["locks"][key] = owner
        self.append_event("state_change", owner, f"Lock acquired: {key}")

    def unlock(self, key: str, owner: str) -> None:
        current = self.data["locks"].get(key)
        if current and current == owner:
            del self.data["locks"][key]
            self.append_event("state_change", owner, f"Lock released: {key}")

    # ---------- metrics ----------
    def bump_tool_calls(self, n: int = 1) -> None:
        self.data["metrics"]["tool_calls"] += n

    # ---------- export ----------
    def to_dict(self) -> Dict[str, Any]:
        return self.data
