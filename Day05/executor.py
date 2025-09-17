# Day05/executor.py
from __future__ import annotations
import json, os, re, time
from copy import deepcopy
from typing import Any, Dict, Tuple

from tool_registry import TOOLS, get as get_tool
from plan_schema import Plan

PLANS_DIR = os.path.join(os.path.dirname(__file__), "plans")
os.makedirs(PLANS_DIR, exist_ok=True)

# -------- templating: {{s1.result}} or {{last.result}} ----------
RESULT_PATTERN = re.compile(r"\{\{\s*(s\d+|last)\.result\s*\}\}")
ANGLE_RESULT_PATTERN = re.compile(r"<\s*result\s+of\s+(s\d+|last)\s*>", re.IGNORECASE)

def _render_value(val: Any, ctx: Dict[str, Any]) -> Any:
    if not isinstance(val, str):
        return val

    def _lookup(step_id: str) -> str:
        if step_id == "last":
            step_id = ctx.get("_last_step_id", "")
        result = ctx.get(step_id, {}).get("result")
        return "" if result is None else str(result)

    # 1) Handle {{s1.result}} / {{last.result}}
    def _sub_curly(m: re.Match) -> str:
        return _lookup(m.group(1))
    s = RESULT_PATTERN.sub(_sub_curly, val)

    # 2) Handle <result of s1> / <result of last>
    def _sub_angle(m: re.Match) -> str:
        return _lookup(m.group(1))
    s = ANGLE_RESULT_PATTERN.sub(_sub_angle, s)

    return s


def _render_inputs(inputs: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Render an input dict recursively (only string values need substitution)."""
    rendered = {}
    for k, v in inputs.items():
        if isinstance(v, dict):
            rendered[k] = _render_inputs(v, ctx)
        elif isinstance(v, list):
            rendered[k] = [_render_value(x, ctx) for x in v]
        else:
            rendered[k] = _render_value(v, ctx)
    return rendered

# -------- plan persistence ----------
def save_plan(plan: Plan, suffix: str = "") -> str:
    ts = plan.get("created_at", "run")
    safe_ts = ts.replace(":", "-").replace(" ", "_")
    name = f"{safe_ts}{('-' + suffix) if suffix else ''}.json"
    path = os.path.join(PLANS_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    return path

# -------- executor ----------
def execute_plan(plan: Plan, max_total_steps: int = 6) -> Tuple[Plan, Dict[str, Any] | None]:
    """
    Execute steps in order.
    - Applies simple templating from prior results
    - Calls the tool function
    - Records status/timings/results on each step
    - Persists plan after each step
    Returns: (updated_plan, last_result_dict or None)
    """
    plan = deepcopy(plan)  # don’t mutate original
    steps = plan.get("steps", [])[: max_total_steps]
    ctx: Dict[str, Any] = {}           # per-step results live here, keyed by step id
    last_output: Dict[str, Any] | None = None

    for i, step in enumerate(steps, start=1):
        step_id = step.get("id", f"s{i}")
        tool_name = step["tool"]
        raw_inputs = step.get("input", {})
        plan.setdefault("logs", [])
        step["status"] = "running"
        step["attempts"] = step.get("attempts", 0) + 1
        step["started_at"] = time.time()

        # Render inputs using previous results
        ctx["_last_step_id"] = steps[i-2]["id"] if i > 1 else ""
        inputs = _render_inputs(raw_inputs, ctx)

        # Resolve function
        fn = TOOLS.get(tool_name, {}).get("fn")
        if fn is None:
            step["status"] = "error"
            step["error"] = f"unknown tool: {tool_name}"
            plan["logs"].append({"step": step_id, "tool": tool_name, "error": step["error"]})
            save_plan(plan, suffix=f"{step_id}-error")
            break

        # Call tool with timing
        t0 = time.time()
        try:
            output = fn(**inputs)
        except Exception as e:
            output = {"ok": False, "error": str(e)}
        elapsed = round((time.time() - t0) * 1000, 1)

        # Record outputs
        step["finished_at"] = time.time()
        step["elapsed_ms"] = elapsed
        step["input_rendered"] = inputs
        step["output"] = output

        # Consider anything "ok" unless the tool explicitly returns {"ok": False}
        is_ok = True
        if isinstance(output, dict):
            if output.get("ok", True) is False:
                is_ok = False
        step["status"] = "ok" if is_ok else "error"

        # Normalize a "result" for chaining
        if isinstance(output, dict) and "result" in output:
            res = output["result"]
        elif isinstance(output, (str, int, float)):
            res = output
        else:
            # list, None, or any other structure → stringify (preserve unicode)
            res = json.dumps(output, ensure_ascii=False)[:500]
        step["result"] = res


        # Write to ctx for placeholders
        ctx[step_id] = {"result": step["result"], "output": output}
        last_output = output

        # Log + persist
        plan["logs"].append({
            "step": step_id,
            "tool": tool_name,
            "ok": step["status"] == "ok",
            "elapsed_ms": elapsed,
        })
        save_plan(plan, suffix=step_id)

        # Stop early if a step failed (reflector will decide what to do next)
        if step["status"] != "ok":
            break

    return plan, last_output
