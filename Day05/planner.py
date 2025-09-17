# Day05/planner.py
from typing import Dict, Any
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from tool_registry import describe_for_planner
from prompts import PLANNER_SYSTEM
from plan_schema import validate_plan, Plan
from json_utils import parse_json
from dotenv import load_dotenv
load_dotenv()

# You can switch models later via env or arg if you want
LLM_MODEL = "openai:gpt-4.1"

def make_plan(task: str) -> Plan:
    """
    Build a short, valid plan for `task` using the current tool registry.
    Returns a validated Plan (dict) or raises ValueError on failure.
    """
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")

    tools_summary = describe_for_planner()

    sys = SystemMessage(
    content=PLANNER_SYSTEM.replace("{TOOLS_SUMMARY}", tools_summary))

    user = HumanMessage(
        content=f'Create a plan for this task:\n"{task.strip()}"\n'
                f'Use ISO 8601 for created_at (you may set it to "{datetime.utcnow().isoformat()}").\n'
                f"Return STRICT JSON only."
    )

    llm = init_chat_model(LLM_MODEL)
    reply = llm.invoke([sys, user])

    # 1) parse JSON
    try:
        raw_plan: Dict[str, Any] = parse_json(reply.content)
    except Exception as e:
        # one retry with a stricter instruction can be added if you like
        raise ValueError(f"Planner did not return valid JSON: {e}")

    # 2) validate + normalize
    plan = validate_plan(raw_plan)
    return plan
