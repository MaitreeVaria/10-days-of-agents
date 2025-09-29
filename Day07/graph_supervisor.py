from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, TypedDict, Optional, List

from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.types import Command
import json, datetime, re

# --------- State type ---------
class GraphState(TypedDict, total=False):
    base_dir: str
    task_spec: Dict[str, Any]
    bb: Dict[str, Any]         # in-memory blackboard (authoritative during the run)
    status: str
    note: str

# --------- Helpers ---------
def _now() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _init_bb(task_spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": f"run-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
        "version": "0.4",
        "started_at": _now(),
        "updated_at": _now(),
        "task": task_spec,
        "subtasks": [],
        "artifacts": [],
        "messages": [],
        "decisions": [],
        "event_log": [],
        "locks": {},
        "metrics": {"steps": 0, "tool_calls": 0, "elapsed_seconds": 0},
        "_counters": {"e": 0, "st": 0, "m": 0, "a": 0, "d": 0},
    }

def _next_id(bb: Dict[str, Any], prefix: str) -> str:
    bb["_counters"][prefix] = bb["_counters"].get(prefix, 0) + 1
    return f"{prefix}-{bb['_counters'][prefix]:03d}"

def _append_event(bb: Dict[str, Any], kind: str, who: str, what: str, refs: Optional[List[str]]=None, delta: Optional[Dict[str, Any]]=None) -> str:
    eid = _next_id(bb, "e")
    bb["event_log"].append({"id": eid, "kind": kind, "who": who, "what": what, "at": _now(), "refs": refs or [], "delta": delta or {}})
    bb["updated_at"] = _now()
    return eid

def _add_message(bb: Dict[str, Any], role: str, type_: str, content: str, refs: Optional[List[str]]=None) -> str:
    mid = _next_id(bb, "m")
    bb["messages"].append({"id": mid, "role": role, "type": type_, "content": content, "refs": refs or [], "ts": _now()})
    _append_event(bb, "message", role, f"{type_}: {content}", refs=[mid] + (refs or []))
    return mid

def _norm_base(base: Path, raw: str) -> Path:
    p = Path(raw.replace("\\", "/"))
    if p.parts and p.parts[0].lower() == "day07":
        p = Path(*p.parts[1:])
    return base / p

def _acceptance_met(base: Path, task: Dict[str, Any]) -> bool:
    rules = task.get("acceptance", [])
    if not rules:
        return False
    for r in rules:
        if r.get("type") == "file_exists":
            raw = r.get("path")
            if not raw or not _norm_base(base, raw).exists():
                return False
        else:
            return False
    return True

def _flush_to_disk(base: Path, bb: Dict[str, Any]) -> None:
    bbdir = base / "blackboard"
    bbdir.mkdir(parents=True, exist_ok=True)
    with (bbdir / "storage.json").open("w", encoding="utf-8") as f:
        json.dump(bb, f, indent=2)

# --------- ProxyBlackboard (duck-typed to your agents) ---------
class ProxyBlackboard:
    def __init__(self, base_dir: Path, bb: Dict[str, Any]):
        self.base_dir = base_dir
        self.out_dir = base_dir / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._bb = bb

    # --- API used by agents/supervisor ---
    def to_dict(self) -> Dict[str, Any]:
        return self._bb

    def add_message(self, role: str, type_: str, content: str, refs: Optional[List[str]] = None) -> str:
        return _add_message(self._bb, role, type_, content, refs)

    def add_subtask(self, owner: str, kind: str, input_payload: Dict[str, Any], depends_on: Optional[List[str]] = None) -> str:
        st_id = _next_id(self._bb, "st")
        st = {
            "id": st_id, "owner": owner, "kind": kind, "status": "queued",
            "input": input_payload, "output": {"summary": "", "artifacts": [], "citations": []},
            "attempts": 0, "started_at": None, "finished_at": None, "depends_on": depends_on or []
        }
        self._bb["subtasks"].append(st)
        _append_event(self._bb, "state_change", "supervisor", f"Added subtask {st_id}", refs=[st_id])
        return st_id

    def update_subtask(self, st_id: str, **fields: Any) -> None:
        st = self.get_subtask(st_id)
        before = {k: st.get(k) for k in ("status", "attempts", "started_at", "finished_at")}
        st.update(fields)
        after = {k: st.get(k) for k in ("status", "attempts", "started_at", "finished_at")}
        _append_event(self._bb, "state_change", st.get("owner", "unknown"), f"Updated subtask {st_id}", refs=[st_id], delta={"before": before, "after": after})

    def get_subtask(self, st_id: str) -> Dict[str, Any]:
        for st in self._bb["subtasks"]:
            if st["id"] == st_id:
                return st
        raise KeyError(f"subtask not found: {st_id}")

    def add_artifact(self, type_: str, name: str, path: str, content_ref: Optional[str] = None, owner: Optional[str] = None) -> str:
        # enforce "out/..." and sandbox
        p = (self.base_dir / path).resolve()
        if not path.replace("\\", "/").startswith("out/"):
            raise ValueError("artifact path must start with 'out/'")
        try:
            p.relative_to(self.out_dir.resolve())
        except ValueError:
            raise ValueError("artifact path must be under Day07/out/")
        aid = _next_id(self._bb, "a")
        self._bb["artifacts"].append({"id": aid, "type": type_, "name": name, "path": path, "content_ref": content_ref, "version": 1, "owner": owner})
        _append_event(self._bb, "io", owner or "unknown", f"Registered artifact {name}", refs=[aid, path])
        return aid

    # simple locks
    def lock(self, key: str, owner: str) -> None:
        if key in self._bb["locks"]:
            raise RuntimeError(f"Lock exists for {key} owned by {self._bb['locks'][key]}")
        self._bb["locks"][key] = owner
        _append_event(self._bb, "state_change", owner, f"Lock acquired: {key}")

    def unlock(self, key: str, owner: str) -> None:
        cur = self._bb["locks"].get(key)
        if cur and cur == owner:
            del self._bb["locks"][key]
            _append_event(self._bb, "state_change", owner, f"Lock released: {key}")

    def bump_tool_calls(self, n: int = 1) -> None:
        self._bb["metrics"]["tool_calls"] += n

    # compatibility
    def save(self) -> None:
        self._bb["updated_at"] = _now()

# --------- Agent imports (after Proxy so duck typing works) ---------
from agents.researcher import ResearcherAgent
from agents.coder import CoderAgent
from agents.critic import CriticAgent

# --------- Planning helpers ---------
def _has_artifact(bb: Dict[str, Any], type_: str) -> bool:
    return any(a.get("type") == type_ for a in bb["artifacts"])

def _last_artifact_path(bb: Dict[str, Any], type_: str) -> Optional[str]:
    arts = [a for a in bb["artifacts"] if a.get("type") == type_]
    return arts[-1]["path"] if arts else None

def _has_subtask_kind(bb: Dict[str, Any], kind: str) -> bool:
    return any(st.get("kind") == kind for st in bb["subtasks"])

def _canonical_out(path: str) -> str:
    p = Path(path.replace("\\", "/"))
    return str(Path(*([pp for pp in p.parts if pp.lower() != "day07"])))

# --------- Single-node supervisor ---------
def tick(state: GraphState) -> Command:
    base = Path(state["base_dir"])
    task = state["task_spec"]
    bb = state.get("bb") or _init_bb(task)
    bb["task"] = task  # keep spec synced
    bb["metrics"]["steps"] += 1

    # Build proxy (duck-typed to your agents)
    P = ProxyBlackboard(base, bb)

    # Budget guard (prevents any accidental infinite loop)
    max_steps = int(task.get("budget", {}).get("max_steps", 200))
    if bb["metrics"]["steps"] > max_steps:
        _add_message(bb, "supervisor", "status", f"Budget exceeded: steps>{max_steps}")
        _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "done", "note": "budget_exceeded"}, goto=END)

    # 0) Fast stop if acceptance already met
    if _acceptance_met(base, task):
        _add_message(bb, "supervisor", "status", "Acceptance met → stop")
        _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "done", "note": "ok"}, goto=END)

    # 1) Run one queued subtask if present
    runnable_id: Optional[str] = None
    for st in bb["subtasks"]:
        if st["status"] == "queued" and all(next(s for s in bb["subtasks"] if s["id"] == dep)["status"] == "done" for dep in st.get("depends_on", [])):
            runnable_id = st["id"]; break

    if runnable_id:
        st = P.get_subtask(runnable_id)
        owner = st["owner"]
        P.update_subtask(runnable_id, status="in_progress", started_at=_now())
        try:
            if owner == ResearcherAgent.ROLE:
                ResearcherAgent(P).handle(runnable_id)
            elif owner == CoderAgent.ROLE:
                CoderAgent(P).handle(runnable_id)
            elif owner == CriticAgent.ROLE:
                CriticAgent(P).handle(runnable_id)
            else:
                P.add_message("supervisor", "error", f"No agent for owner='{owner}'", refs=[runnable_id])
                P.update_subtask(runnable_id, status="failed", finished_at=_now())
        except Exception as e:
            cur = P.get_subtask(runnable_id)
            attempts = cur.get("attempts", 0) + 1
            P.update_subtask(runnable_id, status="failed", attempts=attempts, finished_at=_now())
            P.add_message("supervisor", "error", f"Agent crash: {e}", refs=[runnable_id])

        P.save()
        _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "continue"}, goto="tick")

    # 2) No runnable work → PLAN next step (research → code → review)
    if not bb["subtasks"]:
        st_id = P.add_subtask(
            owner="researcher",
            kind="research_request",
            input_payload={"topic": "What is MCP?", "num_sources": 2, "notes_path": "notes.md"}
        )
        P.add_message("supervisor", "plan", "Seeded research_request", refs=[st_id])
        P.save(); _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "continue"}, goto="tick")

    has_notes = _has_artifact(bb, "notes")
    has_code = _has_artifact(bb, "code")

    if has_notes and not has_code and not _has_subtask_kind(bb, "code_request"):
        notes_last = _last_artifact_path(bb, "notes") or "out/notes.md"
        st_id = P.add_subtask(
            owner="coder",
            kind="code_request",
            input_payload={"out_path": "mcp.md", "source_path": notes_last, "summary_words": 120}
        )
        P.add_message("supervisor", "plan", f"Queued code_request from {notes_last}", refs=[st_id])
        P.save(); _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "continue"}, goto="tick")

    if has_code and not _has_subtask_kind(bb, "review_request"):
        code_path = _last_artifact_path(bb, "code") or "out/mcp.md"
        target = _canonical_out(code_path)
        st_id = P.add_subtask(
            owner="critic",
            kind="review_request",
            input_payload={"target_path": target, "rubric": {"max_words": 120, "min_citations": 2}}
        )
        P.add_message("supervisor", "plan", f"Queued review for {target}", refs=[st_id])
        P.save(); _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "continue"}, goto="tick")

    # 3) Nothing left to run/plan → stop (PASS or HALT)
    if _acceptance_met(base, task):
        _add_message(bb, "supervisor", "status", "Acceptance met → stop")
        _flush_to_disk(base, bb)
        return Command(update={"bb": bb, "status": "done", "note": "ok"}, goto=END)

    _add_message(bb, "supervisor", "status", "No acceptance and no more work to plan → halting")
    _flush_to_disk(base, bb)
    return Command(update={"bb": bb, "status": "done", "note": "halted_no_acceptance"}, goto=END)

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("tick", tick)
    g.add_edge(START, "tick")  # Command controls tick→tick or tick→END
    return g.compile()
