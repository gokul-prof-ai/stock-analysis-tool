from __future__ import annotations

import json
from pathlib import Path

from .base import DataSource, IngestionError, RawExtract, UnsupportedFileError


class JSONParser(DataSource):
    """Structured JSON extractor."""

    source_name = "file_upload"

    def load(self, target: str | Path) -> RawExtract:
        path = Path(target).expanduser().resolve()

        if not path.exists():
            raise IngestionError(f"JSON file not found: {path}")
        if path.suffix.lower() != ".json":
            raise UnsupportedFileError(f"Not a JSON file: {path}")

        try:
            text = path.read_text(encoding="utf-8-sig")
            payload = json.loads(text)
        except Exception as exc:
            raise IngestionError(f"Failed to parse JSON: {path}") from exc

        return RawExtract(
            source=self.source_name,
            source_file=path.name,
            metadata={
                "file_path": str(path),
                "json": payload,
            },
            tables=[],
        )
