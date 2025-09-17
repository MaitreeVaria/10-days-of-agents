# Day05/plan_schema.py
from __future__ import annotations
from typing import Any, Dict, List, TypedDict, Literal
from datetime import datetime
from tool_registry import TOOLS

# ---------- Typed shapes (for clarity) ----------
OnFail = Literal["retry", "tweak", "ask_user", "abort"]

class Step(TypedDict, total=False):
    id: str                 # "s1", "s2"...
    tool: str               # must be in TOOLS
    input: Dict[str, Any]   # keys must match the tool's params
    expect: str             # optional natural-language check
    on_fail: OnFail         # default: "abort"
    retries: int            # default: 0 (executor may add 1)

class Plan(TypedDict):
    task: str
    created_at: str         # ISO8601
    steps: List[Step]

# ---------- Defaults ----------
DEFAULT_ON_FAIL: OnFail = "abort"
DEFAULT_RETRIES = 0
MAX_STEPS = 6

# ---------- Validation ----------
def validate_plan(plan: Dict[str, Any]) -> Plan:
    """
    Validate and normalize a plan dict.
    - Ensures shape, allowed tools, param keys
    - Fills defaults (id, on_fail, retries)
    - Caps step count
    Raises ValueError on fatal problems.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict")

    task = plan.get("task")
    steps = plan.get("steps")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("plan.task must be a non-empty string")
    if not isinstance(steps, list) or not steps:
        raise ValueError("plan.steps must be a non-empty list")

    # Trim to MAX_STEPS
    steps = steps[:MAX_STEPS]

    normalized_steps: List[Step] = []
    for idx, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"steps[{idx}] must be an object")

        tool = raw.get("tool")
        if tool not in TOOLS:
            raise ValueError(f"steps[{idx}].tool '{tool}' is not in registry")

        # Validate param keys against the registry's declared params
        declared = set(TOOLS[tool]["params"].keys())
        supplied = raw.get("input", {})
        if not isinstance(supplied, dict):
            raise ValueError(f"steps[{idx}].input must be an object")
        extraneous = set(supplied.keys()) - declared
        missing = declared - set(supplied.keys())
        # Allow optional params by not strictly requiring all 'declared' keys.
        # If you want strictness, uncomment next line:
        # if missing: raise ValueError(f"steps[{idx}] missing params: {sorted(missing)}")
        if extraneous:
            raise ValueError(f"steps[{idx}] unknown params: {sorted(extraneous)}")

        step: Step = {
            "id": raw.get("id") or f"s{idx}",
            "tool": tool,
            "input": supplied,
            "expect": raw.get("expect", "").strip() or "",
            "on_fail": raw.get("on_fail") or DEFAULT_ON_FAIL,
            "retries": int(raw.get("retries", DEFAULT_RETRIES)),
        }
        if step["on_fail"] not in ("retry", "tweak", "ask_user", "abort"):
            raise ValueError(f"steps[{idx}].on_fail invalid: {step['on_fail']}")
        if step["retries"] < 0 or step["retries"] > 3:
            raise ValueError(f"steps[{idx}].retries out of range (0..3)")

        normalized_steps.append(step)

    created_at = plan.get("created_at") or datetime.utcnow().isoformat()

    return {
        "task": task.strip(),
        "created_at": created_at,
        "steps": normalized_steps,
    }
