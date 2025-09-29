from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
from Day07.blackboard import Blackboard
from Day08.client.adapter import MCPClient
import re

class CoderAgent:
    ROLE = "coder"

    def __init__(self, bb: Blackboard, registry_path: Path) -> None:
        self.bb = bb
        self.registry_path = Path(registry_path)

    def handle(self, st_id: str) -> None:
        st = self.bb.get_subtask(st_id)
        assert st["kind"] == "code_request"
        assert st["owner"] == self.ROLE

        self.bb.update_subtask(st_id, status="in_progress", started_at=self._now())
        spec: Dict[str, Any] = st["input"]
        out_rel = spec.get("out_path", "mcp.md")
        source_path = spec.get("source_path")
        summary_words = int(spec.get("summary_words", 120))
        content = spec.get("content")

        cli = MCPClient(self.registry_path)

        if source_path:
            sp = Path(source_path).as_posix()
            if sp.startswith("out/"):
                sp = sp.split("/", 1)[1]
            fr = cli.mcp_call("file_read_safe", {"path": sp})
            self.bb.add_message(self.ROLE, "tool_call",
                                f"file_read_safe → ok={fr.get('ok')} lat={fr.get('latency_ms')}ms cache={fr.get('from_cache')} circuit={fr.get('circuit')}",
                                refs=[st_id])
            if not fr.get("ok"):
                return self._fail(st_id, f"read failed: {fr.get('error')}")
            notes_text = fr["result"]["text"]
            lines = [ln.strip("- ").strip() for ln in notes_text.splitlines() if ln.strip().startswith("- ")]
            summary = " ".join(lines).strip()
            words = summary.split()
            if len(words) > summary_words:
                summary = " ".join(words[:summary_words])
            cites = []
            for u in re.findall(r'https?://\S+', notes_text):
                u = u.rstrip(".,);]")
                if u not in cites:
                    cites.append(u)
                if len(cites) >= 2:
                    break
            if cites:
                summary += "\n\nSources: " + "; ".join(cites)
            to_write = summary + "\n"
        else:
            to_write = (content or "Hello from Coder!\n")

        fw = cli.mcp_call("file_write_safe", {"path": out_rel, "text": to_write})
        self.bb.add_message(self.ROLE, "tool_call",
                            f"file_write_safe → ok={fw.get('ok')} lat={fw.get('latency_ms')}ms cache={fw.get('from_cache')} circuit={fw.get('circuit')}",
                            refs=[st_id])
        if not fw.get("ok"):
            return self._fail(st_id, f"write failed: {fw.get('error')}")

        out_path = fw["result"]["path"]
        aid = self.bb.add_artifact(type_="code", name=Path(out_rel).name, path=out_path, content_ref=None, owner=self.ROLE)

        self.bb.update_subtask(st_id,
                               output={"summary": f"Wrote {out_path}", "artifacts": [aid], "citations": []},
                               status="done", finished_at=self._now())
        self.bb.add_message(self.ROLE, "code_result", f"Created {out_path}", refs=[st_id, aid])

    def _fail(self, st_id: str, reason: str) -> None:
        st = self.bb.get_subtask(st_id)
        attempts = st.get("attempts", 0) + 1
        self.bb.update_subtask(st_id, status="failed", attempts=attempts, finished_at=self._now())
        self.bb.add_message(self.ROLE, "code_error", reason, refs=[st_id])

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
