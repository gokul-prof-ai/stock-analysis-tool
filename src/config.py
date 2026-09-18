from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class IngestionConfig:
    max_file_mb: int = 50
    allowed_extensions: tuple[str, ...] = (
        ".pdf",
        ".xlsx",
        ".xls",
        ".csv",
        ".json",
    )


@dataclass(frozen=True)
class AppConfig:
    name: str
    version: str
    environment: str
    database: DatabaseConfig
    ingestion: IngestionConfig
    raw: dict[str, Any] = field(default_factory=dict)


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load TOML configuration from disk."""
    config_path = Path(path or os.getenv("STOCK_ANALYSIS_CONFIG") or "config.toml")
    config_path = config_path.expanduser().resolve()

    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"Failed to parse TOML config: {config_path}") from exc

    app = payload.get("app", {})
    db = payload.get("database", {})
    ing = payload.get("ingestion", {})
    base_dir = config_path.parent

    allowed = tuple(
        str(ext).lower()
        for ext in ing.get(
            "allowed_extensions",
            [".pdf", ".xlsx", ".xls", ".csv", ".json"],
        )
    )

    return AppConfig(
        name=str(app.get("name", "Stock Analysis Tool")),
        version=str(app.get("version", "2.0.0")),
        environment=str(app.get("environment", "dev")),
        database=DatabaseConfig(
            path=_resolve_path(base_dir, str(db.get("path", "data/stock_analysis.db")))
        ),
        ingestion=IngestionConfig(
            max_file_mb=int(ing.get("max_file_mb", 50)),
            allowed_extensions=allowed,
        ),
        raw=payload,
    )
