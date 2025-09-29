from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional
from Day07.blackboard import Blackboard
from Day08.client.adapter import MCPClient
import re

class CriticAgent:
    ROLE = "critic"

    def __init__(self, bb: Blackboard, registry_path: Path) -> None:
        self.bb = bb
        self.registry_path = Path(registry_path)

    def handle(self, st_id: str) -> None:
        st = self.bb.get_subtask(st_id)
        assert st["kind"] == "review_request"
        assert st["owner"] == self.ROLE

        self.bb.update_subtask(st_id, status="in_progress", started_at=self._now())

        inp: Dict[str, Any] = st["input"]
        target_path: str = inp.get("target_path", "out/mcp.md")
        rubric: Dict[str, Any] = inp.get("rubric", {})
        max_words: Optional[int] = rubric.get("max_words")
        min_cites: int = int(rubric.get("min_citations", 0))

        cli = MCPClient(self.registry_path)
        tp = target_path
        if tp.startswith("out/"):
            tp = tp.split("/", 1)[1]

        fr = cli.mcp_call("file_read_safe", {"path": tp})
        self.bb.add_message(self.ROLE, "tool_call",
                            f"file_read_safe → ok={fr.get('ok')} lat={fr.get('latency_ms')}ms cache={fr.get('from_cache')} circuit={fr.get('circuit')}",
                            refs=[st_id])
        if not fr.get("ok"):
            return self._fail(st_id, f"read failed: {fr.get('error')}")

        text = fr["result"]["text"]
        words = len(text.split())
        cite_count = len(re.findall(r'https?://\S+', text))

        ok = True; reasons = []
        if isinstance(max_words, int) and words > max_words:
            ok = False; reasons.append(f"word_count {words} > {max_words}")
        if isinstance(min_cites, int) and cite_count < min_cites:
            ok = False; reasons.append(f"citations {cite_count} < {min_cites}")

        rev_text = (
            f"# Review of {target_path}\n"
            f"- exists: yes\n"
            f"- word_count: {words}\n"
            f"- citations: {cite_count}\n"
            f"- max_words: {max_words if max_words is not None else 'n/a'}\n"
            f"- min_citations: {min_cites}\n"
            f"- result: {'PASS' if ok else 'FAIL'}\n"
        )

        fw = cli.mcp_call("file_write_safe", {"path": "review.md", "text": rev_text})
        self.bb.add_message(self.ROLE, "tool_call",
                            f"file_write_safe → ok={fw.get('ok')} lat={fw.get('latency_ms')}ms cache={fw.get('from_cache')} circuit={fw.get('circuit')}",
                            refs=[st_id])
        if not fw.get("ok"):
            return self._fail(st_id, f"write failed: {fw.get('error')}")

        out_path = fw["result"]["path"]
        aid = self.bb.add_artifact(type_="report", name="review.md", path=out_path, content_ref=None, owner=self.ROLE)

        summary = f"Review {'PASS' if ok else 'FAIL'}: {', '.join(reasons) if reasons else 'ok'}"
        self.bb.update_subtask(st_id,
                               output={"summary": summary, "artifacts": [aid], "citations": []},
                               status="done", finished_at=self._now())
        self.bb.add_message(self.ROLE, "review_result", summary, refs=[st_id, aid])

    def _fail(self, st_id: str, reason: str) -> None:
        st = self.bb.get_subtask(st_id)
        attempts = st.get("attempts", 0) + 1
        self.bb.update_subtask(st_id, status="failed", attempts=attempts, finished_at=self._now())
        self.bb.add_message(self.ROLE, "review_error", reason, refs=[st_id])

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
