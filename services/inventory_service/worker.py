from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import redis

from legacy.src.agent.inventory.windows_registry import collect_windows_inventory
from legacy.src.agent.logging_setup import setup_logging


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def run_worker() -> None:
    log_dir = Path(_env_str("LOG_DIR", "."))
    log_level = _env_str("LOG_LEVEL", "info")
    setup_logging(log_dir, log_level)

    redis_host = _env_str("REDIS_HOST", "localhost")
    redis_port = _env_int("REDIS_PORT", 6379)
    task_queue_name = _env_str("TASK_QUEUE_NAME", "inventory_tasks")
    result_queue_name = _env_str("RESULT_QUEUE_NAME", "inventory_results")

    client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    client.ping()
    logging.info("inventory worker started, listening queue %s", task_queue_name)

    while True:
        _, raw = client.brpop(task_queue_name, timeout=0)
        task_id = ""
        command = ""
        try:
            message = json.loads(raw)
            task_id = str(message.get("task_id", ""))
            command = str(message.get("command", "")).strip().lower()
        except Exception:  # noqa: BLE001
            logging.exception("inventory worker got malformed task: %s", raw)
            continue

        if command != "inventory":
            logging.warning("inventory worker ignored unsupported command: %s", command)
            continue

        try:
            payload = collect_windows_inventory()
            result = {
                "task_id": task_id,
                "status": "ok",
                "payload": payload,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            logging.exception("inventory collection failed for task_id=%s", task_id)
            result = {
                "task_id": task_id,
                "status": "error",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }

        client.lpush(result_queue_name, json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    run_worker()
