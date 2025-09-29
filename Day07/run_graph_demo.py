from pathlib import Path
from graph_supervisor import build_graph
import json, datetime

def main() -> None:
    base = Path(__file__).parent  # Day07/
    task_spec = {
        "id": "day07-final",
        "goal": "Research → Code → Review using in-memory state + file persistence",
        "scope": {"in": ["produce notes, summary, and review"], "out": []},
        "constraints": {"paths_allowed": ["out/**"], "max_file_kb": 256, "deadline": None},
        "acceptance": [
            {"type": "file_exists", "path": "out/mcp.md"},
            {"type": "file_exists", "path": "out/review.md"}
        ],
        "budget": {"max_steps": 60, "max_tool_calls": 50, "max_seconds": 300},
        "notes": ""
    }

    graph = build_graph()
    initial = {"base_dir": str(base), "task_spec": task_spec, "status": "continue"}
    config = {"configurable": {"thread_id": "day07-graph"}, "recursion_limit": 200}

    result = graph.invoke(initial, config)
    print("Graph status:", result.get("status"))
    print("notes.md:", (base / "out" / "notes.md").exists())
    print("mcp.md:", (base / "out" / "mcp.md").exists())
    print("review.md:", (base / "out" / "review.md").exists())
    storage = base / "blackboard" / "storage.json"
    if storage.exists():
        print("Blackboard:", storage)

    bb_dir = base / "blackboard"
    bb_dir.mkdir(parents=True, exist_ok=True)
    storage = bb_dir / "storage.json"
    if storage.exists():
        # copy to a versioned snapshot and to run.json
        snapshots = bb_dir / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        snap = snapshots / f"{ts}-final.json"
        snap.write_text(storage.read_text(encoding="utf-8"), encoding="utf-8")
        (base / "run.json").write_text(storage.read_text(encoding="utf-8"), encoding="utf-8")
        print("Snapshot:", snap)
        print("Final run.json:", base / "run.json")


if __name__ == "__main__":
    main()
    
    
