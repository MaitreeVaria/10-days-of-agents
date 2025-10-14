from typing import Callable, Dict, Any


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]):
        if not callable(fn):
            raise TypeError("Tool must be callable")
        self._tools[name] = fn

    def get(self, name: str) -> Callable[..., Any]:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def call(self, name: str, *args, **kwargs):
        return self.get(name)(*args, **kwargs)


registry = ToolRegistry()



