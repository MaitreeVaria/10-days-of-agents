from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage,ToolMessage, HumanMessage, SystemMessage

import os 

from states import State
from memory import SemanticMemory

MEMORY_ON = os.getenv("SEMANTIC_ENABLED", "true").lower() == "true"
MEMORY_K = int(os.getenv("MEMORY_K", "3"))
MAX_MSG = 4  # short-term buffer size

def trim_messages(messages):
    """Return (recent_messages, overflow_messages)."""
    if len(messages) <= MAX_MSG:
        return messages, []
    overflow = messages[:-MAX_MSG]
    recent = messages[-MAX_MSG:]
    return recent, overflow

def summarize_overflow(llm, overflow_messages, prev_summary: str) -> str:
    """Return a 2–4 sentence summary of the overflow + previous summary."""
    if not overflow_messages:
        return prev_summary

    # Build a compact text from overflow (only the message content)
    overflow_text = "\n".join(
        getattr(m, "content", "") for m in overflow_messages if getattr(m, "content", None)
    )

    prompt = (
        "Summarize the PRIOR conversation below into 2-4 sentences. "
        "Keep: user goals, key decisions, references/links mentioned, open TODOs. "
        "Be concise and factual.\n\n"
        f"Previous summary (may be empty): {prev_summary}\n\n"
        f"Conversation to summarize:\n{overflow_text}\n\n"
        "Summary:"
    )
    return llm.invoke(prompt).content.strip()

llm = init_chat_model("openai:gpt-4.1")
semantic = SemanticMemory() if MEMORY_ON else None

def llm_node(state: State):
    # 1) trim to last 8 messages
    recent, overflow = trim_messages(state["messages"])
    state["messages"] = recent
    print(f"[buffer] kept={len(recent)} overflow={len(overflow)}")

    # 2) if we have overflow, update episodic summary
    if overflow:
        new_summary = summarize_overflow(llm, overflow, state.get("episodic_summary", ""))
        state["episodic_summary"] = new_summary
        print(f"[episodic] summary length={len(new_summary)} chars")

    # 3) build the context the model will see:
    #    - a SystemMessage with the episodic summary (if any)
    #    - then the recent messages
    context = []
    if state.get("episodic_summary"):
        context.append(SystemMessage(content=f"Episodic summary: {state['episodic_summary']}"))
    context += state["messages"]

    # find the latest user message
    user_msg = ""
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            user_msg = m.content
            break

    # retrieve top-k semantic memories
    mem_lines = []
    if MEMORY_ON and user_msg:
        hits = semantic.search(user_msg, k=MEMORY_K)
        if hits:
            mem_lines = [f"- {h}" for h in hits]

    # construct context: episodic summary (if you built it earlier), then memories, then recent messages
    system_bits = []
    if state.get("episodic_summary"):
        system_bits.append(f"Episodic summary: {state['episodic_summary']}")
    if mem_lines:
        system_bits.append("Known user context:\n" + "\n".join(mem_lines))

    preface = "\n\n".join(system_bits).strip()
    context = ([SystemMessage(content=preface)] if preface else []) + state["messages"]

    ai = llm.invoke(context)
    if MEMORY_ON:
        # ask the model to extract ONE durable fact, or say NONE
        extract_prompt = [
            SystemMessage(content=(
                "Extract ONE stable user fact or preference from the last exchange, if any. "
                "It should be useful across sessions (e.g., preferences, identity, projects). "
                "If none, reply with EXACTLY: NONE."
            )),
            HumanMessage(content=f"User said: {user_msg}\nAssistant said: {ai.content}")
        ]
        candidate = llm.invoke(extract_prompt).content.strip()
        if candidate and candidate.upper() != "NONE" and 10 <= len(candidate) <= 240:
            semantic.add(candidate, tags=["fact"], confidence=0.7)


    return {"messages": [ai], "episodic_summary": state.get("episodic_summary", "")}


# wire a trivial graph
graph_builder = StateGraph(State)
graph_builder.add_node("llm", llm_node)
graph_builder.add_edge(START, "llm")
graph_builder.add_edge("llm", END)
graph = graph_builder.compile()

if __name__ == "__main__":
    print("Day03 Memory-Only Agent (type 'exit' to quit)")
    state: State = {"messages": [], "steps": 0, "episodic_summary": ""}
    while True:
        text = input("You: ").strip()
        if text.lower() in {"exit", "quit"}:
            break
        state["messages"].append(HumanMessage(content=text))
        state = graph.invoke(state)
        print("AI:", state["messages"][-1].content)



