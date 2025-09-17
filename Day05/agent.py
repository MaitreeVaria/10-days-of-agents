# Day05/agent.py
from __future__ import annotations
import argparse, os
from dotenv import load_dotenv

load_dotenv()  # load OPENAI_API_KEY if present

from planner import make_plan
from executor import execute_plan, save_plan
from reflector import reflect

def run_task(task: str, max_reflect_cycles: int = 2):
    print(f"Task: {task}\n")
    plan = make_plan(task)
    print("Plan generated.")
    # First execution
    plan, last = execute_plan(plan)

    cycles = 0
    while cycles < max_reflect_cycles:
        # If the last executed step failed, try reflector
        plan, action = reflect(plan)
        if action == "stop":
            break
        print(f"Reflector action: {action}")
        # After a reflect retry/tweak, continue executing remaining steps
        plan, last = execute_plan(plan)
        cycles += 1

    path = save_plan(plan, suffix="final")
    print(f"\nSaved executed plan: {path}")

    # Final short summary
    steps = plan.get("steps", [])
    failures = [s for s in steps if s.get("status") != "ok"]
    if failures:
        last_failed = failures[-1]
        print("Outcome: ❌ failure")
        print(f"Failed at step {last_failed.get('id')} ({last_failed.get('tool')}): {last_failed.get('output')}")
    else:
        print("Outcome: ✅ success")
        if steps:
            print(f"Last step: {steps[-1].get('id')} ({steps[-1].get('tool')})")
            print(f"Result: {steps[-1].get('result')}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Day 05 Planner→Executor→Reflector agent")
    parser.add_argument("--task", type=str, required=True, help='Task, e.g. "Compute 12*(3+4) and write it into answer.txt"')
    parser.add_argument("--reflect-cycles", type=int, default=2, help="Max reflector cycles")
    args = parser.parse_args()

    run_task(args.task, max_reflect_cycles=args.reflect_cycles)
