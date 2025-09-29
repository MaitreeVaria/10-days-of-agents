from __future__ import annotations
from pathlib import Path

# Payload cap: 256 KiB is plenty for Day 7
MAX_BYTES = 256 * 1024

def file_write_safe(root: Path, rel_path: str, text: str, overwrite: bool = True) -> str:
    """
    Safely write UTF-8 text to a file under 'root' (allowlist directory).
    Returns the RELATIVE path that was written (relative to base project root like 'out/x.txt').

    Guardrails:
      - root MUST be a directory you control (e.g., Day07/out/)
      - rel_path MUST be relative and cannot traverse out of root
      - enforce size limit
    """
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ValueError("invalid path")
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    # Normalize to forward slashes
    rp = rel_path.replace("\\", "/").strip()
    if rp.startswith("/") or rp.startswith("\\"):
        raise ValueError("absolute paths not allowed")
    if ".." in Path(rp).parts:
        raise ValueError("path traversal not allowed")

    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError(f"payload too large (> {MAX_BYTES} bytes)")

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / rp).resolve()

    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("path escapes allowed directory")

    if target.exists() and target.is_dir():
        raise ValueError("target is a directory")

    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with target.open(mode, encoding="utf-8", newline="\n") as f:
        f.write(text)

    # Return canonical "out/..." style relative path if root endswith /out
    try:
        # If root looks like ".../Day07/out"
        if root.name == "out":
            prefix_index = str(target).lower().rfind("/out/")
            if prefix_index != -1:
                return str(target)[prefix_index+1:]  # drop the leading slash
    except Exception:
        pass
    # fallback: return path relative to root folder
    return str(target.relative_to(root.parent))
