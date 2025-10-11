# Day09/registry/loader.py
from pathlib import Path

def load_registry():
    """
    Return a simple registry structure the pipeline expects.
    Adjust this to match how your Day09 pipeline discovers tools/servers.
    """
    # Example: if your MCP servers are optional, return a dict with their sockets/ports/etc.
    return {
        "mcp": {
            "fs": {"host": "day09-fs-mcp", "port": None},   # stdio servers don't need ports
            "web": {"host": "day09-web-mcp", "port": None},
            "docs": {"host": "day09-docs-mcp", "port": None},
        },
        "paths": {
            "out_dir": str(Path("/workspace/Day08/out").resolve()),
            "logs_dir": str(Path("/workspace/Day09/logs").resolve()),
        },
    }
