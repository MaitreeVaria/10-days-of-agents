from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional, List
from blackboard import Blackboard

class ResearcherAgent:
    """
    Minimal Researcher:
    - handles 'research_request'
    - input: {"topic": str, "num_sources": int, "notes_path": "notes.md"}
    - writes notes under Day07/out/, registers artifact, updates subtask
    """

    ROLE = "researcher"

    def __init__(self, bb: Blackboard) -> None:
        self.bb = bb

    def handle(self, st_id: str) -> None:
        st = self.bb.get_subtask(st_id)
        assert st["kind"] == "research_request", f"Researcher only handles research_request, got {st['kind']}"
        assert st["owner"] == self.ROLE, f"Subtask {st_id} is not owned by {self.ROLE}"

        self.bb.update_subtask(st_id, status="in_progress", started_at=self._now())

        spec: Dict[str, Any] = st["input"]
        topic: str = spec.get("topic", "What is MCP?")
        num_sources: int = int(spec.get("num_sources", 2))
        notes_rel: str = spec.get("notes_path", "notes.md")

        if not isinstance(notes_rel, str) or not notes_rel.strip():
            self._fail(st_id, "Missing 'notes_path' in research_request")
            return
        if notes_rel.startswith("/") or notes_rel.startswith("\\") or ".." in Path(notes_rel).parts:
            self._fail(st_id, f"Unsafe notes_path: {notes_rel!r}")
            return

        lock_key = notes_rel
        try:
            self.bb.lock(lock_key, owner=self.ROLE)

            # Stub content (swap later with real search results)
            bullets = [
                "MCP (Model Context Protocol) standardizes how AI apps/agents connect to tools.",
                "It defines message schemas and transport so tools are plug-and-play.",
                "Benefits include portability and safer, auditable tool usage."
            ]
            default_sources: List[str] = [
                "https://github.com/modelcontextprotocol/spec",
                "https://openai.com/index/model-context-protocol/"
            ]
            sources = default_sources[: max(1, num_sources)]

            body = []
            body.append(f"# Notes: {topic}")
            body.append("")
            body += [f"- {b}" for b in bullets]
            body.append("")
            body.append("Sources:")
            body += [f"- {u}" for u in sources]
            notes_text = "\n".join(body) + "\n"

            # Write file
            target = (self.bb.out_dir / notes_rel).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(notes_text, encoding="utf-8")

            # Register artifact path in 'out/...'
            rel_for_art = f"out/{Path(notes_rel).name}" if not str(notes_rel).startswith("out/") else notes_rel
            aid = self.bb.add_artifact(
                type_="notes",
                name=Path(notes_rel).name,
                path=rel_for_art,
                content_ref=None,
                owner=self.ROLE
            )

            st_output = {
                "summary": f"Wrote {rel_for_art} with {len(bullets)} bullets and {len(sources)} sources",
                "artifacts": [aid],
                "citations": sources
            }
            self.bb.update_subtask(st_id, output=st_output, status="done", finished_at=self._now())
            self.bb.add_message(self.ROLE, "research_result", f"Created {rel_for_art}", refs=[st_id, aid])

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
        self.bb.add_message(self.ROLE, "research_error", reason, refs=[st_id])

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
