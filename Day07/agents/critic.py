from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional
from blackboard import Blackboard

class CriticAgent:
    """
    Tiny Critic:
    - handles 'review_request'
    - input: {"target_path": "out/<file>", "rubric": {"max_words": 120, "min_citations": 0}}
    - checks existence (+ optional max word count & min citations)
    - writes out/review.md and registers it as an artifact
    """

    ROLE = "critic"

    def __init__(self, bb: Blackboard) -> None:
        self.bb = bb

    def handle(self, st_id: str) -> None:
        st = self.bb.get_subtask(st_id)
        assert st["kind"] == "review_request", f"Critic only handles review_request, got {st['kind']}"
        assert st["owner"] == self.ROLE, f"Subtask {st_id} is not owned by {self.ROLE}"

        self.bb.update_subtask(st_id, status="in_progress", started_at=self._now())

        inp: Dict[str, Any] = st["input"]
        target_path: str = inp.get("target_path", "")
        rubric: Dict[str, Any] = inp.get("rubric", {})
        max_words: Optional[int] = rubric.get("max_words")
        min_cites: int = int(rubric.get("min_citations", 0))

        fp = (self.bb.base_dir / target_path)
        if not target_path or not fp.exists():
            self._fail(st_id, f"target not found: {target_path}")
            return

        text = fp.read_text(encoding="utf-8", errors="ignore")
        words = len(text.split())
        import re
        cite_count = len(re.findall(r'https?://\S+', text))

        ok = True
        reasons = []
        if isinstance(max_words, int) and words > max_words:
            ok = False; reasons.append(f"word_count {words} > {max_words}")
        if isinstance(min_cites, int) and cite_count < min_cites:
            ok = False; reasons.append(f"citations {cite_count} < {min_cites}")

        # Write review
        review_rel = "review.md"
        (self.bb.out_dir / review_rel).write_text(
            f"# Review of {target_path}\n"
            f"- exists: yes\n"
            f"- word_count: {words}\n"
            f"- citations: {cite_count}\n"
            f"- max_words: {max_words if max_words is not None else 'n/a'}\n"
            f"- min_citations: {min_cites}\n"
            f"- result: {'PASS' if ok else 'FAIL'}\n",
            encoding="utf-8"
        )

        aid = self.bb.add_artifact(
            type_="report",
            name=Path(review_rel).name,
            path=f"out/{review_rel}",
            content_ref=None,
            owner=self.ROLE
        )

        st_output = {
            "summary": f"Review {'PASS' if ok else 'FAIL'}: {', '.join(reasons) if reasons else 'ok'}",
            "artifacts": [aid],
            "citations": []
        }
        self.bb.update_subtask(st_id, output=st_output, status="done", finished_at=self._now())
        self.bb.add_message(self.ROLE, "review_result", st_output["summary"], refs=[st_id, aid])

    def _fail(self, st_id: str, reason: str) -> None:
        st = self.bb.get_subtask(st_id)
        attempts = st.get("attempts", 0) + 1
        self.bb.update_subtask(st_id, status="failed", attempts=attempts, finished_at=self._now())
        self.bb.add_message(self.ROLE, "review_error", reason, refs=[st_id])

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
