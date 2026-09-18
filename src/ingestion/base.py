from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class IngestionError(Exception):
    """Base ingestion failure."""


class UnsupportedFileError(IngestionError):
    """Raised when a file type is not supported."""


@dataclass
class ParsedTable:
    """A generic table extracted from any source."""

    name: str
    columns: list[str]
    rows: list[list[Any]] = field(default_factory=list)


@dataclass
class RawExtract:
    """Raw parser/scraper output before normalization."""

    source: str
    source_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tables: list[ParsedTable] = field(default_factory=list)


class DataSource(ABC):
    """Common interface for online and file-based ingestion."""

    source_name: str = "unknown"

    @abstractmethod
    def load(self, target: str | Path) -> RawExtract:
        """Load raw data from a ticker, URL, or file path."""
        raise NotImplementedError
