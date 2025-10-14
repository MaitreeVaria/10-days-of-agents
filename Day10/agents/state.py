from typing import Annotated, TypedDict
from typing_extensions import NotRequired
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    episodic_summary: NotRequired[str]
    nl_query: NotRequired[str]
    sql: NotRequired[str]
    schema_summary: NotRequired[str]
    tool_events: NotRequired[list[dict]]
    memory_hits: NotRequired[list[str]]


