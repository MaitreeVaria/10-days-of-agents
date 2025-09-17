# Day05/registry.py
from typing import Callable, Dict, Any
from tools import calculator, search_local_docs, file_write_safe  # note the relative import

# Simple registry: name -> { fn, params, desc }
TOOLS: Dict[str, Dict[str, Any]] = {
    "calculator": {
        "fn": calculator,
        "params": {"expr": "str"},
        "desc": "Safely evaluate arithmetic expressions (supports %, ( ), + - * /).",
    },
    "search_local_docs": {
        "fn": search_local_docs,
        "params": {"query": "str", "top_k": "int"},
        "desc": "Keyword search in Day05/data; returns title, snippet, path, score.",
    },
    "file_write_safe": {
        "fn": file_write_safe,
        "params": {"path": "str", "text": "str"},
        "desc": "Write UTF-8 text under Day05/out only; size-limited and sandboxed.",
    },
}

NAMES = list(TOOLS.keys())

def get(name: str) -> Callable[..., dict]:
    """Return the callable for a tool name, or raise KeyError."""
    return TOOLS[name]["fn"]

def describe_for_planner() -> str:
    """Human-readable summary you can dump into a system prompt for the planner."""
    lines = []
    for name, meta in TOOLS.items():
        params = ", ".join(f"{k}:{v}" for k, v in meta["params"].items())
        lines.append(f"- {name}({params}) — {meta['desc']}")
    return "\n".join(lines)
