# Day10/app/streamlit_app.py
import time
from pathlib import Path
import pandas as pd
import streamlit as st

from sql_utils import (
    DB_PATH, list_tables, list_columns, run_sql, is_safe_sql, quick_examples
)

st.set_page_config(page_title="Day10 – Rides SQL Workbench", layout="wide")
st.title("Day 10 — Rides SQL Workbench (DuckDB)")

# ---- Sidebar: DB info & schema browser
st.sidebar.header("Database")
st.sidebar.caption(f"📂 {DB_PATH}")
with st.sidebar.expander("Settings", expanded=False):
    try:
        from Day10.observability.tracing import set_tracing
    except Exception:
        set_tracing = None
    tracing_on = st.checkbox("Enable tracing", value=True, key="trace_on")
    if set_tracing:
        set_tracing(tracing_on)
    # Clear semantic memory
    try:
        from Day10.memory.semantic import clear_all_memory, SemanticMemory
    except Exception:
        clear_all_memory = None
        SemanticMemory = None
    if st.button("Clear semantic memory", key="clear_memory_btn"):
        if clear_all_memory:
            clear_all_memory()
            st.success("Semantic memory cleared.")
    if SemanticMemory:
        mem = SemanticMemory()
        st.caption(f"Semantic items: {mem.count()}")
        if st.checkbox("Show memory items", value=False, key="show_mem_items"):
            items = mem.list_texts(limit=50)
            if items:
                st.write("\n\n".join(f"- {t}" for t in items))
            else:
                st.caption("No items.")
    # Clear chat context
    if st.button("Clear chat context", key="clear_chat_btn"):
        st.session_state.chat_history = []
        st.success("Chat context cleared.")

tabs_df = list_tables()
if tabs_df.empty:
    st.sidebar.error("No tables found in schema `day10` — did you run the build script?")
else:
    with st.sidebar.expander("Tables", expanded=True):
        for t in tabs_df["table_name"].tolist():
            if st.checkbox(t, value=False, key=f"tbl_{t}"):
                cols = list_columns(t)
                st.write(f"**{t}**")
                st.dataframe(cols, use_container_width=True, hide_index=True)

# ---- English → SQL (Agent)
st.subheader("English → SQL (Agent)")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of dicts {role, content}

# Chat transcript (last 10) above the input
if st.session_state.chat_history:
    for msg in st.session_state.chat_history[-10:]:
        if msg["role"] == "user":
            st.markdown(f"**You:** {msg['content']}")
        else:
            st.markdown("**Agent (SQL):**")
            st.code(msg["content"], language="sql")
else:
    st.caption("No chat yet.")

nl_text = st.text_input("Ask a question about the data", key="nl2sql_q")
if st.button("✨ Generate SQL", key="gen_sql_btn"):
    try:
        import sys
        from pathlib import Path as _Path
        _app_dir = str(_Path(__file__).resolve().parent)
        _day10_dir = str(_Path(__file__).resolve().parents[1])
        _project_root = str(_Path(__file__).resolve().parents[2])
        for _p in (_app_dir, _day10_dir, _project_root):
            if _p not in sys.path:
                sys.path.append(_p)
        try:
            from agent_adapter import chat_generate_sql, memory_write_from_last_exchange  # local import for Streamlit run context
        except Exception:
            from Day10.app.agent_adapter import chat_generate_sql, memory_write_from_last_exchange  # absolute import
        hist_tuples = [(h["role"], h["content"]) for h in st.session_state.chat_history]
        proposed = (chat_generate_sql(hist_tuples, nl_text) or "").strip()
        if not proposed:
            st.warning("No SQL generated. Try rephrasing your question.")
        else:
            st.session_state.pending_editor_sql = proposed
            st.success("Generated SQL loaded into editor.")
            st.session_state.chat_history.append({"role": "user", "content": nl_text})
            st.session_state.chat_history.append({"role": "assistant", "content": proposed})
            try:
                stored = memory_write_from_last_exchange(hist_tuples + [("user", nl_text), ("assistant", proposed)], proposed)
                if stored:
                    st.caption(f"Memory stored: {stored}")
            except Exception:
                pass
            st.rerun()
    except Exception as e:
        st.error(f"Generation failed: {e}")

# ---- Main: Query editor
st.subheader("Query")
examples = quick_examples()
example_name = st.selectbox("Examples", ["(none)"] + list(examples.keys()))
if "editor_sql" not in st.session_state:
    st.session_state.editor_sql = ""
if "pending_editor_sql" not in st.session_state:
    st.session_state.pending_editor_sql = ""

if example_name != "(none)":
    st.session_state.editor_sql = examples[example_name]

# Apply any pending load request (set by buttons below) before rendering the editor
if st.session_state.pending_editor_sql:
    st.session_state.editor_sql = st.session_state.pending_editor_sql
    st.session_state.pending_editor_sql = ""

sql = st.text_area(
    "Write a **read-only** SQL query (SELECT/WITH/EXPLAIN):",
    key="editor_sql",
    height=180,
    placeholder="SELECT * FROM v_rides_analytics LIMIT 20;"
)

col_run, col_clear, col_save = st.columns([1,1,1])

if "history" not in st.session_state:
    st.session_state.history = []  # list of dicts: {sql, rows, ms, at}

def add_history(entry):
    st.session_state.history.insert(0, entry)
    # keep last 20
    st.session_state.history = st.session_state.history[:20]

run_clicked = col_run.button("▶ Run")
clear_clicked = col_clear.button("🧹 Clear Results")
save_clicked = col_save.button("⭐ Save to History")

# ---- Results / actions
res_placeholder = st.empty()
meta_placeholder = st.empty()

if run_clicked:
    if not is_safe_sql(sql):
        st.warning("Only read queries are allowed for now (SELECT / WITH / EXPLAIN).")
    else:
        t0 = time.perf_counter()
        try:
            try:
                from agent_adapter import run_sql_safe  # local
            except Exception:
                from Day10.app.agent_adapter import run_sql_safe  # absolute
            df = run_sql_safe(sql)
            ms = int((time.perf_counter() - t0) * 1000)
            meta_placeholder.info(f"Returned {len(df):,} rows in {ms} ms")
            if len(df):
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.write("No rows.")
            add_history({"sql": sql, "rows": len(df), "ms": ms, "at": time.strftime("%H:%M:%S")})
        except Exception as e:
            st.error(f"Query failed: {e}")

if clear_clicked:
    meta_placeholder.empty()
    res_placeholder.empty()

if save_clicked and sql.strip():
    add_history({"sql": sql, "rows": None, "ms": None, "at": time.strftime("%H:%M:%S")})
    st.success("Saved to session history.")

# ---- History
st.subheader("Session History")
if not st.session_state.history:
    st.caption("No history yet.")
else:
    for i, h in enumerate(st.session_state.history, start=1):
        with st.expander(f"{i}. {h['sql'][:80]}"):
            st.code(h["sql"], language="sql")
            meta = []
            if h["rows"] is not None:
                meta.append(f"rows={h['rows']}")
            if h["ms"] is not None:
                meta.append(f"time={h['ms']}ms")
            meta.append(f"at={h['at']}")
            st.caption(" • ".join(meta))
            if st.button("Load into editor", key=f"load_{i}"):
                st.session_state.pending_editor_sql = h["sql"]
                st.rerun()

## (chat transcript now shown above input)
