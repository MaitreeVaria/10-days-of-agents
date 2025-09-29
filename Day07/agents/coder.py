from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
from blackboard import Blackboard
from tools import file_write_safe

class CoderAgent:
    """
    Minimal Coder:
    - handles 'code_request'
    - input options:
        {"out_path": "mcp.md", "content": "text ..."}
      OR {"out_path": "mcp.md", "source_path": "out/notes.md", "summary_words": 120}
    - writes file under Day07/out/, registers artifact, updates subtask
    """

    ROLE = "coder"

    def __init__(self, bb: Blackboard) -> None:
        self.bb = bb

    def handle(self, st_id: str) -> None:
        st = self.bb.get_subtask(st_id)
        assert st["kind"] == "code_request", f"Coder only handles code_request, got {st['kind']}"
        assert st["owner"] == self.ROLE, f"Subtask {st_id} is not owned by {self.ROLE}"

        self.bb.update_subtask(st_id, status="in_progress", started_at=self._now())

        spec: Dict[str, Any] = st["input"]
        out_rel = spec.get("out_path")
        content = spec.get("content")
        source_path = spec.get("source_path")
        summary_words = int(spec.get("summary_words", 120))

        if not out_rel:
            self._fail(st_id, "Missing 'out_path' in code_request")
            return

        lock_key = f"{out_rel}"
        try:
            self.bb.lock(lock_key, owner=self.ROLE)

            if source_path:
                # naive summarizer from notes: take bullet lines and trim to N words
                notes_fp = (self.bb.base_dir / source_path).resolve()
                notes_text = notes_fp.read_text(encoding="utf-8", errors="ignore") if notes_fp.exists() else ""
                lines = [ln.strip("- ").strip() for ln in notes_text.splitlines() if ln.strip().startswith("- ")]
                summary = " ".join(lines).strip()
                words = summary.split()
                if len(words) > summary_words:
                    summary = " ".join(words[:summary_words])
                # carry up to 2 cites
                import re
                cites = []
                for u in re.findall(r'https?://\S+', notes_text):
                    u = u.rstrip(".,);]")
                    if u not in cites:
                        cites.append(u)
                    if len(cites) >= 2:
                        break
                if cites:
                    summary += "\n\nSources: " + "; ".join(cites)
                to_write = (summary or "No notes available.") + "\n"
            else:
                to_write = (content or "Hello from Coder!\n")

            # safe write under out/
            written_rel = file_write_safe(self.bb.out_dir, out_rel, to_write, overwrite=True)

            # normalize to "out/..."
            rel_for_art = written_rel if written_rel.startswith("out/") else f"out/{Path(written_rel).name}"

            aid = self.bb.add_artifact(
                type_="code",
                name=Path(rel_for_art).name,
                path=rel_for_art,
                content_ref=None,
                owner=self.ROLE
            )

            st_output = {
                "summary": f"Wrote {rel_for_art} ({len(to_write)} bytes)",
                "artifacts": [aid],
                "citations": []
            }
            self.bb.update_subtask(st_id, output=st_output, status="done", finished_at=self._now())
            self.bb.add_message(self.ROLE, "code_result", f"Created {rel_for_art}", refs=[st_id, aid])

        except Exception as e:
            self._fail(st_id, f"Error: {e}")
        finally:
            try:
                self.bb.unlock(lock_key, owner=self.ROLE)
            except Exception:
                pass

    def _fail(self, st_id: str, reason: str) -> None:
        st = self.bb.get_subtask(st_id)
        attempts = st.get("attempts", 0) + 1
        self.bb.update_subtask(st_id, status="failed", attempts=attempts, finished_at=self._now())
        self.bb.add_message(self.ROLE, "code_error", reason, refs=[st_id])

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
