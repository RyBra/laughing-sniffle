from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    log_path: Path


@dataclass(frozen=True)
class WorkersConfig:
    inventory_workers: int


@dataclass(frozen=True)
class QueueConfig:
    tasks_maxsize: int
    results_maxsize: int
    put_timeout_seconds: float


@dataclass(frozen=True)
class AppConfig:
    logging: LoggingConfig
    workers: WorkersConfig
    queue: QueueConfig


def load_config(config_path: Path) -> AppConfig:
    """Load and validate config.ini."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    parser = ConfigParser()
    parser.read(config_path, encoding="utf-8")

    log_level = parser.get("logging", "level", fallback="info").lower().strip()
    log_dir_raw = Path(
        parser.get("logging", "log_path", fallback=str(config_path.parent))
    )
    log_dir = (
        log_dir_raw
        if log_dir_raw.is_absolute()
        else (config_path.parent / log_dir_raw).resolve()
    )

    inventory_workers = parser.getint("workers", "InventoryWorkers", fallback=1)
    if inventory_workers < 1:
        raise ValueError("workers.InventoryWorkers must be >= 1")

    tasks_maxsize = parser.getint("queue", "tasks_maxsize", fallback=100)
    results_maxsize = parser.getint("queue", "results_maxsize", fallback=100)
    put_timeout_seconds = parser.getfloat("queue", "put_timeout_seconds", fallback=2.0)
    if tasks_maxsize < 1 or results_maxsize < 1:
        raise ValueError("queue maxsize values must be >= 1")
    if put_timeout_seconds <= 0:
        raise ValueError("queue.put_timeout_seconds must be > 0")

    return AppConfig(
        logging=LoggingConfig(level=log_level, log_path=log_dir),
        workers=WorkersConfig(inventory_workers=inventory_workers),
        queue=QueueConfig(
            tasks_maxsize=tasks_maxsize,
            results_maxsize=results_maxsize,
            put_timeout_seconds=put_timeout_seconds,
        ),
    )
