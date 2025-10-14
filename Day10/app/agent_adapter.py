from typing import Optional, List, Tuple
import pandas as pd

from langchain_core.messages import HumanMessage

from agents.graph import graph
from agents.state import AgentState
from tools.registry import registry
from Day10.observability.tracing import trace_span


def generate_sql(nl_query: str) -> str:
    state: AgentState = {
        "messages": [HumanMessage(content=nl_query)],
        "nl_query": nl_query,
        "sql": "",
        "schema_summary": "",
    }
    with trace_span("adapter.generate_sql"):
        out = graph.invoke(state)
    # After graph run, sql should be in state (set by nl2sql)
    return (out.get("sql") or "").strip()


def run_sql_safe(sql: str) -> pd.DataFrame:
    from Day10.tools.duckdb_tool import query
    with trace_span("adapter.run_sql_safe"):
        return query(sql)


def chat_generate_sql(history: List[Tuple[str, str]], user_text: str) -> str:
    """history: list of (role, content) where role in {"user","assistant"}."""
    msgs = []
    for role, content in history[-10:]:
        if role == "user":
            msgs.append(HumanMessage(content=content))
        else:
            from langchain_core.messages import AIMessage
            msgs.append(AIMessage(content=content))
    state: AgentState = {
        "messages": msgs + [HumanMessage(content=user_text)],
        "nl_query": user_text,
    }
    with trace_span("adapter.chat_generate_sql", hist_len=len(history)):
        out = graph.invoke(state)
    return (out.get("sql") or "").strip()


def memory_write_from_last_exchange(history: List[Tuple[str, str]], ai_sql: str) -> str:
    """Persist one durable preference extracted from the last user→assistant pair.
    Returns the stored fact (string) or empty string."""
    user_text = ""
    for role, content in reversed(history):
        if role == "user":
            user_text = content
            break
    # Lazy import to avoid stale module caching and import order issues
    try:
        import importlib, agents.graph as g  # type: ignore
        g = importlib.reload(g)
        fn = getattr(g, "write_memory_from_exchange", None)
        if fn is None:
            raise AttributeError
        with trace_span("adapter.memory_write"):
            return fn(user_text, ai_sql)
    except Exception:
        try:
            import importlib, Day10.agents.graph as g2  # type: ignore
            g2 = importlib.reload(g2)
            fn2 = getattr(g2, "write_memory_from_exchange", None)
            if fn2 is None:
                return ""
            with trace_span("adapter.memory_write"):
                return fn2(user_text, ai_sql)
        except Exception:
            return ""


