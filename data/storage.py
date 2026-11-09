import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

DATA_DIR = Path(__file__).parent


class JsonStorage:
    """Safe, modular JSON storage helper for bot persistent data."""

    def __init__(self, filename: str, default_data: Any = None):
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        self.file_path = DATA_DIR / filename
        self.default_data = default_data if default_data is not None else {}
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the file with default data if it does not exist."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.save(self.default_data)

    def load(self) -> Any:
        """Load JSON data from disk."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return self.default_data

    def save(self, data: Any) -> None:
        """Atomically write JSON data to disk to avoid corruption."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = self.file_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        temp_file.replace(self.file_path)

    def get(self, key: str, default: Any = None) -> Any:
        data = self.load()
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        if not isinstance(data, dict):
            data = {}
        data[key] = value
        self.save(data)
