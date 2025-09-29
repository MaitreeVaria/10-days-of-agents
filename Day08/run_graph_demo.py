from pathlib import Path
from Day08.graph_supervisor import build_graph
import json
from datetime import datetime, UTC

def main():
    base = Path(__file__).parent
    task_spec = {
        "id": "day08-rcr",
        "goal": "Research → Code → Review via MCP servers",
        "scope": {"in": ["produce notes (web/docs), summary, and review"], "out": []},
        "constraints": {"paths_allowed": ["out/**"], "max_file_kb": 256, "deadline": None},
        "acceptance": [
            {"type": "file_exists", "path": "out/mcp.md"},
            {"type": "file_exists", "path": "out/review.md"}
        ],
        "budget": {"max_steps": 80, "max_tool_calls": 50, "max_seconds": 300},
        "notes": ""
    }

    graph = build_graph()
    initial = {"base_dir": str(base), "task_spec": task_spec, "status": "continue"}
    config = {"configurable": {"thread_id": "day08-graph"}, "recursion_limit": 200}

    result = graph.invoke(initial, config)

    print("Graph status:", result.get("status"))
    for fn in ["notes.md", "mcp.md", "review.md"]:
        print(f"{fn}:", (base / "out" / fn).exists())

    # final snapshot
    bb_dir = base / "blackboard"; bb_dir.mkdir(parents=True, exist_ok=True)
    storage = bb_dir / "storage.json"
    if storage.exists():
        snaps = bb_dir / "snapshots"; snaps.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        snap = snaps / f"{ts}-final.json"
        snap.write_text(storage.read_text(encoding="utf-8"), encoding="utf-8")
        (base / "run.json").write_text(storage.read_text(encoding="utf-8"), encoding="utf-8")
        print("Snapshot:", snap)
        print("Final run.json:", base / "run.json")

if __name__ == "__main__":
    main()
