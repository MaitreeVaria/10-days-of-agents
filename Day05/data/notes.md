# Notes on MCP and Agents

- MCP stands for Model Context Protocol. It defines a standard way for AI models and clients to discover and call external tools.
- Tools exposed by an MCP server describe themselves with JSON Schemas, so clients know the exact parameters.
- Example tools could be: `search_local_docs` (to look through local files) or `run_shell_safe` (to run limited shell commands).
- MCP is inspired by ideas from Language Server Protocol (LSP), but designed for AI/LLM agents.
- Key goals: safety, discoverability, portability across ecosystems (Anthropic, OpenAI, Microsoft, etc.).
