from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END

import json

from states import State
from tools import web_search, doc_query, doc_ingest

from dotenv import load_dotenv
load_dotenv()

# out = doc_ingest()
# print(out)

@tool("web_search")
def web_search_tool(query: str) -> dict:
    """Search the web and return either a short 'text' summary or 'results' with titles+URLs."""
    return web_search(query)

@tool("doc_query")
def doc_query_tool(question: str, top_k: int = 4) -> dict:
    """Retrieve top-k chunks from local docs and return snippets with citations (source/page)."""
    return doc_query(question, top_k)

llm = init_chat_model("openai:gpt-4.1")  # or from CLI arg
llm_with_tools = llm.bind_tools([web_search_tool, doc_query_tool])

def llm_node(state: State):
    # (optional) trim history to avoid ballooning context
    msgs = state["messages"][-8:]

    # If you want to gently steer tool usage, prepend a short system hint
    system = SystemMessage(content=(
        "You can call tools. "
        "Use web_search for live info; if you get URLs, pick one and summarize with citations. "
        "Use doc_query for local documents and always cite as [source: <file> p.<page>]. "
        "If a tool returns ok:false or empty results, recover gracefully or ask for clarification."
    ))
    ai = llm_with_tools.invoke([system] + msgs)
    return {"messages": [ai]}
def run_tool_node(state: State):
    msgs = state["messages"]
    if not msgs:
        return {}

    last = msgs[-1]
    if not hasattr(last, "tool_calls") or not last.tool_calls:
        return {}

    tool_call = last.tool_calls[0]  # Day 02: handle first call only
    name = tool_call["name"]
    args = tool_call.get("args", {}) or {}

    if name == "web_search":
        q = args.get("query") or args.get("searchString") or args.get("q") or ""
        out = web_search(q)               # expects {"query": "..."}
    elif name == "doc_query":
        out = doc_query(**args)                # expects {"question": "...", "top_k": 4}
    else:
        out = {"ok": False, "error": f"unknown tool: {name}"}

    tmsg = ToolMessage(
        content=json.dumps(out),
        name=name,
        tool_call_id=tool_call["id"],
    )
    return {"messages": [tmsg], "steps": state["steps"] + 1}

def needs_tool(state: State) -> str:
    if state.get("steps", 0) > 5:
        return "finalize"
    last = state["messages"][-1] if state["messages"] else None
    if last and hasattr(last, "tool_calls") and last.tool_calls:
        return "run_tool"
    return "finalize"

def finalize_node(state: State):
    return {}

graph_builder = StateGraph(State)
graph_builder.add_node("llm", llm_node)
graph_builder.add_node("run_tool", run_tool_node)
graph_builder.add_node("finalize", finalize_node)

graph_builder.add_edge(START, "llm")
graph_builder.add_conditional_edges("llm", needs_tool, {"run_tool": "run_tool", "finalize": "finalize"})
graph_builder.add_edge("run_tool", "llm")
graph_builder.add_edge("finalize", END)
graph = graph_builder.compile()

from IPython.display import Image, display

try:
    img = Image(graph.get_graph().draw_mermaid_png())
    with open("output.png", "wb") as f:
        f.write(img.data)
except Exception:
    pass


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    # conversation state (messages will grow with each turn)
    state: State = {"messages": [], "steps": 0}

    print("Day02 Agent (type 'exit' or 'quit' to stop)")
    while True:
        user_input = input("You: ")
        if user_input.strip().lower() in {"quit", "exit"}:
            print("Goodbye!")
            break

        # add user message
        state["messages"].append(HumanMessage(content=user_input))

        # run graph with current state (which already includes history)
        state = graph.invoke(state)

        # show the last AI response
        print("AI:", state["messages"][-1].content)


