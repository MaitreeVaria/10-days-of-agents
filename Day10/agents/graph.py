import os
import re
from typing import List
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from Day10.agents.state import AgentState
from Day10.app.sql_utils import list_tables, list_columns, is_safe_sql
from Day10.tools.registry import registry
from Day10.tools.duckdb_tool import query as duckdb_query
from Day10.tools.schema_tool import list_tables_tool, describe_table_tool, schema_summary_tool
from Day10.memory.semantic import SemanticMemory
from Day10.observability.tracing import trace_span


# Register tools
registry.register("duckdb.query", duckdb_query)
registry.register("schema.list", list_tables_tool)
registry.register("schema.describe", describe_table_tool)
registry.register("schema.summary", schema_summary_tool)


def build_schema_summary() -> str:
    # Route via registry to keep a consistent tool mesh
    return registry.call("schema.summary")


llm = init_chat_model(os.getenv("DAY10_MODEL", "openai:gpt-4o-mini"))
semantic = SemanticMemory()
MEMORY_ON = os.getenv("SEMANTIC_ENABLED", "true").lower() == "true"


def supervisor(state: AgentState) -> AgentState:
    # Simple routing: if nl_query exists and no sql yet -> generate; if sql present -> validate
    return {"messages": []}


def fetch_schema(state: AgentState) -> AgentState:
    with trace_span("schema.summary"):
        schema = build_schema_summary()
    # Optional: log the tool call in state
    events = (state.get("tool_events") or []) + [{
        "tool": "schema.summary",
        "ok": True,
        "len": len(schema),
    }]
    return {"schema_summary": schema, "tool_events": events, "messages": []}


def memory_retrieve(state: AgentState) -> AgentState:
    nl = (state.get("nl_query") or "").strip()
    hits = []
    if MEMORY_ON and nl:
        with trace_span("memory.retrieve"):
            raw_hits = semantic.search(nl, k=int(os.getenv("MEMORY_K", "3")))
            # filter out time-window prefs to avoid biasing all queries
            hits = [h for h in raw_hits if not _is_time_window_pref(h)]
    return {"memory_hits": hits, "messages": []}


def nl2sql(state: AgentState) -> AgentState:
    nl = (state.get("nl_query") or "").strip()
    schema = state.get("schema_summary", "")
    mem = state.get("memory_hits") or []
    if not nl:
        return {"messages": []}
    system = SystemMessage(content=(
        "You are a helpful SQL generator for DuckDB. Output only SQL for read-only queries.\n"
        "- Use only SELECT/WITH/EXPLAIN.\n- Prefer existing views if present.\n"
        "- Use table/view names exactly as given.\n"
        "- Do NOT include markdown code fences or any explanation.\n"
        "- Unless the CURRENT user question explicitly asks for a date/time window, DO NOT add any time filters.\n"
        + ("Known user context:\n" + "\n".join(f"- {h}" for h in mem) + "\n" if mem else "")
        + "Schema:\n" + schema
    ))
    prior_msgs = state.get("messages") or []
    # Ensure only Human/AI messages are passed (System is provided above)
    # If the current question has no time window, drop any prior time-window-only messages to avoid bias
    current_has_time = _is_time_window_pref(nl)
    def _msg_ok(m):
        content = getattr(m, "content", "")
        return current_has_time or not _is_time_window_pref(content)
    convo = [m for m in prior_msgs if isinstance(m, (HumanMessage, AIMessage)) and _msg_ok(m)]
    human = HumanMessage(content=nl)
    with trace_span("nl2sql.invoke", msgs=len(convo) + 1):
        ai = llm.invoke([system] + convo + [human])
    sql = _sanitize_sql_output(ai.content)
    return {"sql": sql, "messages": [ai]}


def sql_safety(state: AgentState) -> AgentState:
    sql = (state.get("sql") or "").strip()
    if not sql:
        return {"messages": []}
    with trace_span("sql.safety"):
        ok = is_safe_sql(sql)
    if not ok:
        raise ValueError("Unsafe SQL proposed by model")
    return {"messages": []}


def executor(state: AgentState) -> AgentState:
    sql = (state.get("sql") or "").strip()
    if not sql:
        return {"messages": []}
    # Execute via tool registry (MCP-like)
    df = registry.call("duckdb.query", sql)
    # We do not return DataFrame in state for now; adapter will run executor directly
    return {"messages": []}


def compile_graph():
    builder = StateGraph(AgentState)
    builder.add_node("fetch_schema", fetch_schema)
    builder.add_node("memory_retrieve", memory_retrieve)
    builder.add_node("nl2sql", nl2sql)
    builder.add_node("sql_safety", sql_safety)
    builder.add_node("executor", executor)
    builder.add_edge(START, "fetch_schema")
    builder.add_edge("fetch_schema", "memory_retrieve")
    builder.add_edge("memory_retrieve", "nl2sql")
    builder.add_edge("nl2sql", "sql_safety")
    builder.add_edge("sql_safety", END)
    return builder.compile()


graph = compile_graph()


# --- helpers
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*\n|\n```$", re.MULTILINE)

def _sanitize_sql_output(text: str) -> str:
    text = (text or "").strip()
    # remove markdown fences if present
    text = text.strip("`")
    text = _FENCE_RE.sub("", text).strip()
    # keep only first statement
    parts = [p.strip() for p in text.split(";") if p.strip()]
    if not parts:
        return ""
    return parts[0] + (";" if not parts[0].endswith(";") else "")

def _is_time_window_pref(text: str) -> bool:
    t = (text or "").lower()
    keys = [
        "last 7 days", "last seven days", "past week",
        "last 30 days", "last thirty days", "past month",
        "last 90 days", "past 3 months", "past three months",
        "today", "yesterday", "this week", "this month",
    ]
    return any(k in t for k in keys)


def write_memory_from_exchange(user_text: str, ai_sql: str) -> str:
    """Extract ONE durable user preference/fact from the last exchange and persist.
    Returns the stored fact or empty string if none."""
    user_text = (user_text or "").strip()
    ai_sql = (ai_sql or "").strip()
    if not user_text or not ai_sql:
        return ""
    prompt = [
        SystemMessage(content=(
            "Extract ONE stable user preference/fact from the exchange below.\n"
            "- It should be useful across future queries (e.g., time window like last 30 days, preferred cab_type, city filter).\n"
            "- If none, reply EXACTLY with: NONE"
        )),
        HumanMessage(content=f"User: {user_text}\nSQL: {ai_sql}")
    ]
    try:
        candidate = llm.invoke(prompt).content.strip()
    except Exception:
        return ""
    if not candidate or candidate.upper() == "NONE":
        return ""
    if len(candidate) < 6 or len(candidate) > 240:
        return ""
    # avoid storing short-term time window prefs like "last 30 days"
    lower = candidate.lower()
    if any(key in lower for key in ["last 7 days", "last 30 days", "last 90 days", "past week", "past month", "past 3 months"]):
        return ""
    try:
        semantic.add(candidate, tags=["pref"], confidence=0.7)
        return candidate
    except Exception:
        return ""


