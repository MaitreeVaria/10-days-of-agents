from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage,ToolMessage, HumanMessage
from langchain_core.tools import tool

import json
import argparse

from states import State
from tools import calculator,local_search

from dotenv import load_dotenv
load_dotenv()


# defined tools using langchain_core.tools using tools from tools.py
@tool("calculator")
def calculator_tool(expr: str) -> dict:
    """Evaluate arithmetic. Supports + - * / ( ) and patterns like '20% of 50'."""
    return calculator(expr)

@tool("local_search")
def local_search_tool(query: str, top_k: int = 3) -> dict:
    """Search ./data/*.md for query terms and return filenames + snippets."""
    return local_search(query, top_k)

# Start building a Graph
graph_builder = StateGraph(State)


# define llm model and tools
llm = init_chat_model("openai:gpt-4.1")
llm_with_tools = llm.bind_tools([calculator_tool, local_search_tool])


def llm_node(state: State):
    # send current messages to the tool-enabled model
    MAX_MSG = 8  # last 8 messages is plenty for Day 01
    msgs = state["messages"][-MAX_MSG:]
    ai_msg: AIMessage = llm_with_tools.invoke(msgs)
    return {"messages": [ai_msg]}



def run_tool_node(state: State):
    """If the last AI message requested a tool, run it and append a ToolMessage."""
    msgs = state["messages"]
    if not msgs:
        return {}

    last = msgs[-1]
    # We only act if the last message is an AIMessage with tool calls
    if not hasattr(last, "tool_calls") or not last.tool_calls:
        return {}

    # handle only the first tool call
    tool_call = last.tool_calls[0]
    name = tool_call["name"]
    args = tool_call.get("args", {}) or {}

    # Dispatch to your Python tools
    if name == "calculator":
        out = calculator(**args)  # expects {"expr": "..."}
    elif name == "local_search":
        out = local_search(**args)  # expects {"query": "...", "top_k": 3}
    else:
        out = {"ok": False, "error": f"unknown tool: {name}"}

    # Append a ToolMessage with the JSON result; tie it to the tool_call id
    tool_msg = ToolMessage(
        content=json.dumps(out),
        name=name,
        tool_call_id=tool_call["id"],
    )
    # increment your loop counter too
    return {"messages": [tool_msg], "steps": state["steps"] + 1}

def needs_tool(state: State) -> str:
    """Decide next hop after the LLM node."""
    msgs = state["messages"]
    if not msgs:
        return "finalize"
    last = msgs[-1]
    # stop if too many steps (safety cap)
    if state.get("steps", 0) > 5:
        return "finalize"
    # if model asked for a tool, go run it; else finalize
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "run_tool"
    return "finalize"


def finalize_node(state: State):
    """Let the model produce a short final answer (no tools)."""
    # You can keep this super simple on Day 01: if we got here,
    # just return the last AI message as the final; or ask the model
    # for a concise wrap-up. We'll do the minimal path.
    return {}  # nothing to add; graph will END

# build the graph

graph_builder.add_node("llm", llm_node)
graph_builder.add_node("run_tool", run_tool_node)
graph_builder.add_node("finalize", finalize_node)
graph_builder.add_edge(START, "llm")

graph_builder.add_conditional_edges(
    "llm",
    needs_tool,
    {
        "run_tool": "run_tool",
        "finalize": "finalize",
    },
)
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
    state: State = {"messages": [], "steps": 0}
    while True:
        user_input = input("You: ")
        if user_input.lower() in {"quit", "exit"}:
            break
        state["messages"].append(HumanMessage(content=user_input))
        state = graph.invoke(state)
        print("AI:", state["messages"][-1].content)

