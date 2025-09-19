import json
from pathlib import Path
from typing import Any, Dict

class IdempotencyStore:
    def __init__(self, path: Path):
        self.path = path
        if not self.path.exists():
            self._save({})

    def _load(self) -> Dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_success(self, key: str) -> bool:
        data = self._load()
        entry = data.get(key)
        return bool(entry and entry.get("status") == "success")

    def get(self, key: str) -> Dict[str, Any]:
        data = self._load()
        return data.get(key, {})

    def mark_success(self, key: str, payload: Dict[str, Any]) -> None:
        data = self._load()
        data[key] = {"status": "success", **payload}
        self._save(data)
