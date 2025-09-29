from pathlib import Path
from blackboard import Blackboard
from agents.coder import CoderAgent

def main() -> None:
    base = Path(__file__).parent  # Day07/
    task_spec = {
        "id": "task-001",
        "goal": "Smoke-test the blackboard with a Coder agent",
        "scope": {"in": ["create a file"], "out": []},
        "constraints": {"paths_allowed": ["out/**"], "max_file_kb": 256, "deadline": None},
        "acceptance": [{"type": "file_exists", "path": "out/hello.txt"}],
        "budget": {"max_steps": 10, "max_tool_calls": 10, "max_seconds": 60},
        "notes": ""
    }

    bb = Blackboard(base, task_spec=task_spec, fresh=True)
    st_id = bb.add_subtask(
        owner="coder",
        kind="code_request",
        input_payload={"out_path": "hello.txt", "content": "Hello, Day 07!\n"}
    )

    CoderAgent(bb).handle(st_id)
    bb.save()
    snap = bb.snapshot("001-coder-done")

    st = bb.get_subtask(st_id)
    print(f"Subtask {st_id} → status={st['status']}")
    print(f"Snapshot: {snap}")
    print(f"Artifacts: {[a['path'] for a in bb.to_dict()['artifacts']]}")

if __name__ == "__main__":
    main()
