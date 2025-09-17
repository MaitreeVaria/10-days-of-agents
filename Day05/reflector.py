# Day05/reflector.py
from __future__ import annotations
import json, os
from typing import Any, Dict, Tuple

from tool_registry import TOOLS
from executor import save_plan

def _is_numberish(x: Any) -> bool:
    if isinstance(x, (int, float)):
        return True
    try:
        float(str(x))
        return True
    except Exception:
        return False

def _passes_expect(step: Dict[str, Any]) -> bool:
    exp = (step.get("expect") or "").lower().strip()
    if not exp:
        return True  # nothing to check
    res = step.get("result")
    out = step.get("output", {})

    # Very small set of cheap checks (extend as needed)
    if "number" in exp:
        return _is_numberish(res)
    if "non-empty" in exp or "not empty" in exp:
        return bool(res)
    if "file exists" in exp and isinstance(out, dict):
        # if file_write_safe returned ok True with bytes>0, we consider it "exists"
        return out.get("ok") is True and (out.get("bytes", 0) > 0)
    # fallback: assume ok
    return True

def _tweak_inputs_for(tool: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    tweaked = dict(inputs)

    if tool == "search_local_docs":
        # Small bump to widen scope
        k = tweaked.get("top_k", 3)
        try:
            tweaked["top_k"] = max(1, min(int(k) + 2, 10))
        except Exception:
            tweaked["top_k"] = 5

    if tool == "file_write_safe":
        # Normalize path if the planner accidentally included the out dir prefix
        p = tweaked.get("path", "")
        if isinstance(p, str) and p.lower().startswith("day05/out/"):
            tweaked["path"] = p.split("day05/out/", 1)[1]

    return tweaked

def reflect(plan: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Inspect the last executed step and decide:
    - "retry" same step (if policy allows)
    - "tweak+retry" with tiny parameter changes
    - "stop": nothing to do
    Returns (updated_plan, action_str)
    """
    steps = plan.get("steps", [])
    if not steps:
        return plan, "stop"

    # find the last step that has any execution status
    last_idx = -1
    for i in range(len(steps) - 1, -1, -1):
        if "status" in steps[i]:
            last_idx = i
            break
    if last_idx == -1:
        return plan, "stop"

    step = steps[last_idx]
    status = step.get("status")
    tool = step.get("tool")
    inputs = step.get("input", {})
    on_fail = step.get("on_fail", "abort")
    retries_allowed = int(step.get("retries", 0))
    attempts = int(step.get("attempts", 1))

    # If step "ok" but expectation fails, treat as a soft failure
    if status == "ok" and not _passes_expect(step):
        status = "error"
        step["status"] = "error"
        step["error"] = "expectation_failed"

    # If the step is fine, nothing to do
    if status == "ok":
        return plan, "stop"

    # If it failed, decide recovery
    # 1) plain retry if allowed and attempts <= retries
    if on_fail == "retry" and attempts <= retries_allowed:
        fn = TOOLS.get(tool, {}).get("fn")
        if fn is None:
            return plan, "stop"

        # Reuse the input the executor rendered (if present), else raw
        rendered = step.get("input_rendered", inputs)
        out = fn(**rendered)
        step["attempts"] = attempts + 1
        step["output"] = out
        step["status"] = "ok" if (isinstance(out, dict) and out.get("ok", True)) else "error"
        step["result"] = out.get("result") if isinstance(out, dict) and "result" in out else json.dumps(out)[:200]
        save_plan(plan, suffix=f"{step.get('id','s')}-retry")
        return plan, "retry"

    # 2) small tweak + one retry
    if on_fail == "tweak":
        fn = TOOLS.get(tool, {}).get("fn")
        if fn is None:
            return plan, "stop"
        tweaked = _tweak_inputs_for(tool, step.get("input_rendered", inputs))
        out = fn(**tweaked)
        step["attempts"] = attempts + 1
        step["input_rendered"] = tweaked
        step["output"] = out
        step["status"] = "ok" if (isinstance(out, dict) and out.get("ok", True)) else "error"
        step["result"] = out.get("result") if isinstance(out, dict) and "result" in out else json.dumps(out)[:200]
        save_plan(plan, suffix=f"{step.get('id','s')}-tweak")
        return plan, "tweak+retry"

    # 3) ask_user / abort → stop
    return plan, "stop"
