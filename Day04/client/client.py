# Day04/client/client.py
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os

async def main():
    # Point to your server command
    token = os.environ.get("MCP_AUTH_TOKEN", "dev-secret-123")
    server_params = StdioServerParameters(
        command="python",
        args=["Day04/mcp-server/server.py"],
        env={"MCP_AUTH_TOKEN": token},
    )

    # Open stdio connection to the server
    async with stdio_client(server_params) as (read, write):
        # Create a session over those streams
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])

            res = await session.call_tool("search_local_docs", {"query": "MCP"})
            print("search_local_docs:", res)

            res = await session.call_tool("run_shell_safe", {"cmd": "echo hello"})
            print("run_shell_safe:", res)

if __name__ == "__main__":
    asyncio.run(main())
