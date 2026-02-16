from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: Path, level_name: str) -> Path:
    """Configure file logging in append mode."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "log.txt"

    level = _parse_level(level_name)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        filename=str(log_file),
        filemode="a",
    )
    return log_file


def _parse_level(level_name: str) -> int:
    normalized = level_name.lower().strip()
    mapping = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    if normalized not in mapping:
        raise ValueError(
            "Invalid logging level. Allowed values: debug, info, warning, error."
        )
    return mapping[normalized]
