#!/usr/bin/env python3
"""
Day06 Step 3: Idempotency — skip steps already completed.
"""
import argparse
import json
from pathlib import Path
import sys
import yaml
from datetime import datetime, timezone

from tools import TOOL_REGISTRY
from idempotency_store import IdempotencyStore  # [IDEMPOTENCY]

REQUIRED_STEP_KEYS = {"tool"}

def load_runbook(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Runbook not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("Runbook is empty.")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Runbook must contain a non-empty list under 'steps'.")

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f"Step {i} must be a mapping/object.")
        missing = REQUIRED_STEP_KEYS - set(step.keys())
        if missing:
            raise ValueError(f"Step {i} is missing required key(s): {', '.join(sorted(missing))}")
        if not isinstance(step["tool"], str) or not step["tool"].strip():
            raise ValueError(f"Step {i} 'tool' must be a non-empty string.")
        if "params" in step and not isinstance(step["params"], dict):
            raise ValueError(f"Step {i} 'params' must be a mapping/object when provided.")

        step.setdefault("name", step["tool"])
        step.setdefault("params", {})

        # [IDEMPOTENCY] normalize nested shape
        idem = step.get("idempotency")
        if idem is not None and not isinstance(idem, dict):
            raise ValueError(f"Step {i} 'idempotency' must be a mapping/object when provided.")
        if idem and "key" in idem and not isinstance(idem["key"], str):
            raise ValueError(f"Step {i} 'idempotency.key' must be a string when provided.")

    return data

def execute_step(step: dict, dry_run: bool) -> dict:
    tool_name = step["tool"]
    params = dict(step.get("params", {}))  # shallow copy
    params["dry_run"] = dry_run

    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")

    fn = TOOL_REGISTRY[tool_name]
    return fn(**params)  # type: ignore[arg-type]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runbook", required=True, help="Path to runbook YAML")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without side effects")
    parser.add_argument("--state", default=".ops_state.json", help="Path to idempotency state file")  # [IDEMPOTENCY]
    args = parser.parse_args()

    # [IDEMPOTENCY] init store
    store = IdempotencyStore(Path(args.state))

    try:
        runbook = load_runbook(Path(args.runbook))
    except Exception as e:
        print(f"✗ Runbook error: {e}", file=sys.stderr)
        sys.exit(1)

    mode = "DRY-RUN" if args.dry_run else "REAL"
    print(f"✓ Runbook loaded. Mode: {mode}")
    print(f"State file: {args.state}")  # [IDEMPOTENCY]

    for idx, step in enumerate(runbook["steps"], start=1):
        name = step['name']
        tool = step['tool']
        params = step.get('params', {})
        idem_key = (step.get("idempotency") or {}).get("key")  # [IDEMPOTENCY]

        print(f"\n[{idx}] {name}")
        print(f"    tool:   {tool}")
        print(f"    params: {json.dumps(params, ensure_ascii=False)}")
        if idem_key:
            print(f"    idempotency.key: {idem_key}")

        # [IDEMPOTENCY] skip if already success
        if idem_key and store.is_success(idem_key):
            prev = store.get(idem_key)
            print("    → skipped (already succeeded)")
            print("      previous-result:", json.dumps(prev.get("result", {}), ensure_ascii=False))
            continue

        try:
            result = execute_step(step, dry_run=args.dry_run)
            print("    → result:", json.dumps(result, ensure_ascii=False))

            # [IDEMPOTENCY] mark success on real run (or even on dry-run if you prefer)
            if idem_key and not args.dry_run:
                store.mark_success(
                    idem_key,
                    {
                        "step": name,
                        "tool": tool,
                        "params": params,
                        "result": result,
                        "when": datetime.now(timezone.utc).isoformat(),
                        "mode": "dry-run" if args.dry_run else "real",
                    },
                )
        except Exception as e:
            print(f"    ✗ step failed: {e}")
            sys.exit(2)

if __name__ == "__main__":
    main()
