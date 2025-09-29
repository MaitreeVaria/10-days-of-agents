from pathlib import Path
from Day08.client.adapter import MCPClient  # package-qualified import

def main():
    base = Path(__file__).parent
    reg = base / "registry" / "endpoints.yaml"
    cli = MCPClient(reg)

    for sid in ["fs", "web", "docs"]:
        resp = cli.list_tools(sid)
        print(f"{sid}: {resp}")

if __name__ == "__main__":
    main()
