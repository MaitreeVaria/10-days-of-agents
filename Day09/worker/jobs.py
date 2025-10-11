# Day09/worker/jobs.py
import os
import time
from pathlib import Path

from Day08.graph_supervisor import build_graph
from Day08.client.adapter import MCPClient
from Day09.registry.loader import load_registry
from Day07.blackboard import Blackboard

from Day09.tracing.otel import init_tracer

BASE = Path("/workspace").resolve()
D08 = BASE / "Day08"
BB_DIR = D08 / "blackboard"
OUT_DIR = D08 / "out"

def run_pipeline(run_id: str, goal: str) -> dict:
    print(f"[worker] run_pipeline start run_id={run_id} goal={goal}", flush=True)

    # tracer
    tracer = init_tracer(service_name="agents-worker")

    # minimal task_spec (same happy path as Day08)
    task_spec = {
        "id": run_id,
        "goal": goal,
        "scope": {"in": ["research", "write file", "review"], "out": []},
        "constraints": {"paths_allowed": ["Day08/out/**"], "max_file_kb": 256, "deadline": None},
        "acceptance": [
            {"type": "file_exists", "path": "Day08/out/notes.md"},
            {"type": "file_exists", "path": "Day08/out/mcp.md"},
            {"type": "file_exists", "path": "Day08/out/review.md"},
        ],
        "budget": {"max_steps": 20, "max_tool_calls": 20, "max_seconds": 120},
        "notes": "",
    }

    # Blackboard (fresh per run)
    bb = Blackboard(D08, task_spec=task_spec, fresh=True)

    # MCP client (from Day08)
    reg = load_registry(D08 / "registry" / "endpoints.yaml")
    client = MCPClient(registry=reg, bb=bb)

    # LangGraph orchestration (Day08 build_graph that uses MCP tools)
    graph = build_graph(bb, client)

    with tracer.start_as_current_span("run.plan", attributes={"run.id": run_id, "task.goal": goal}):
        # the actual invoke that runs researcher -> coder -> critic
        result = graph.invoke({"run_id": run_id, "task": task_spec}, {"recursion_limit": 50})

    bb.save()
    snap_path = BB_DIR / "snapshots" / f"{run_id}-final.json"
    snap = bb.snapshot(f"{run_id}-final")
    print(f"[worker] run_pipeline done run_id={run_id} blackboard={bb.storage_path} snapshot={snap}", flush=True)

    return {"ok": True, "run_id": run_id, "blackboard": str(bb.storage_path), "snapshot": str(snap)}
