from pathlib import Path
from Day08.client.adapter import MCPClient

def main():
    base = Path(__file__).parent
    reg = base / "registry" / "endpoints.yaml"
    cli = MCPClient(reg)

    print("\n== Cache demo ==")
    r1 = cli.mcp_call("web_search", {"query": "mcp", "top_k": 2})
    print("first:", r1)
    r2 = cli.mcp_call("web_search", {"query": "mcp", "top_k": 2})
    print("second (cached):", r2)

    print("\n== Rate limit + Circuit breaker demo ==")
    # Disable cache so we actually hit the server repeatedly
    for i in range(6):
        r = cli.mcp_call("web_search", {"query": "mcp", "top_k": 2}, use_cache=False)
        print(i, r)

    print("\nNow wait ~30s to let the breaker cool down, then call again to see half-open/closed behavior.")

if __name__ == "__main__":
    main()
