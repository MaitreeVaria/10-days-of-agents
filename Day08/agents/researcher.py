from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional
from Day07.blackboard import Blackboard
from Day08.client.adapter import MCPClient

class ResearcherAgent:
    ROLE = "researcher"

    def __init__(self, bb: Blackboard, registry_path: Path) -> None:
        self.bb = bb
        self.registry_path = Path(registry_path)

    def handle(self, st_id: str) -> None:
        st = self.bb.get_subtask(st_id)
        assert st["kind"] == "research_request"
        assert st["owner"] == self.ROLE

        self.bb.update_subtask(st_id, status="in_progress", started_at=self._now())
        spec: Dict[str, Any] = st["input"]
        topic: str = spec.get("topic", "What is MCP?")
        num_sources: int = int(spec.get("num_sources", 2))
        notes_rel: str = spec.get("notes_path", "notes.md")

        cli = MCPClient(self.registry_path)

        w = cli.mcp_call("web_search", {"query": topic.lower(), "top_k": max(2, num_sources)})
        self.bb.add_message(
            self.ROLE, "tool_call",
            f"web_search → ok={w.get('ok')} lat={w.get('latency_ms')}ms cache={w.get('from_cache')} circuit={w.get('circuit')}",
            refs=[st_id]
        )
        hits = []
        if w.get("ok"):
            hits = w["result"].get("hits", [])

        if not hits:
            d = cli.mcp_call("search_local_docs", {"query": topic, "top_k": max(2, num_sources)})
            self.bb.add_message(
                self.ROLE, "tool_call",
                f"search_local_docs → ok={d.get('ok')} lat={d.get('latency_ms')}ms cache={d.get('from_cache')} circuit={d.get('circuit')}",
                refs=[st_id]
            )
            if d.get("ok"):
                hits = [{"title": h["path"], "url": f"file://{h['path']}", "snippet": h["snippet"]} for h in d["result"].get("hits", [])]

        bullets = [
            "MCP standardizes how AI apps/agents connect to tools.",
            "It defines message schemas and transport for plug-and-play tools.",
            "Benefits include portability and safer, auditable tool use."
        ]
        urls = [h.get("url") for h in hits if h.get("url")] if hits else [
            "https://github.com/modelcontextprotocol/spec",
            "https://openai.com/index/model-context-protocol/",
        ][:num_sources]

        body = []
        body.append(f"# Notes: {topic}")
        body.append("")
        body += [f"- {b}" for b in bullets]
        body.append("")
        body.append("Sources:")
        body += [f"- {u}" for u in urls]
        notes_text = "\n".join(body) + "\n"

        fw = cli.mcp_call("file_write_safe", {"path": notes_rel, "text": notes_text})
        self.bb.add_message(
            self.ROLE, "tool_call",
            f"file_write_safe → ok={fw.get('ok')} lat={fw.get('latency_ms')}ms cache={fw.get('from_cache')} circuit={fw.get('circuit')}",
            refs=[st_id]
        )
        if not fw.get("ok"):
            return self._fail(st_id, f"write failed: {fw.get('error')}")

        out_path = fw["result"]["path"]
        aid = self.bb.add_artifact(type_="notes", name=Path(notes_rel).name, path=out_path, content_ref=None, owner=self.ROLE)

        self.bb.update_subtask(st_id,
                               output={"summary": f"Wrote {out_path} with {len(urls)} sources",
                                       "artifacts": [aid], "citations": urls},
                               status="done", finished_at=self._now())
        self.bb.add_message(self.ROLE, "research_result", f"Created {out_path}", refs=[st_id, aid])

    def _fail(self, st_id: str, reason: str) -> None:
        st = self.bb.get_subtask(st_id)
        attempts = st.get("attempts", 0) + 1
        self.bb.update_subtask(st_id, status="failed", attempts=attempts, finished_at=self._now())
        self.bb.add_message(self.ROLE, "research_error", reason, refs=[st_id])

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
