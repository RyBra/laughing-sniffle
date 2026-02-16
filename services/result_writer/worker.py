from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import redis

from legacy.src.agent.logging_setup import setup_logging
from legacy.src.agent.result_writer import write_payload_atomic


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def run_writer() -> None:
    log_dir = Path(_env_str("LOG_DIR", "."))
    log_level = _env_str("LOG_LEVEL", "info")
    setup_logging(log_dir, log_level)

    redis_host = _env_str("REDIS_HOST", "localhost")
    redis_port = _env_int("REDIS_PORT", 6379)
    result_queue_name = _env_str("RESULT_QUEUE_NAME", "inventory_results")
    payload_path = Path(_env_str("PAYLOAD_PATH", "/data/payload.json"))

    client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    client.ping()
    logging.info("result writer started, listening queue %s", result_queue_name)

    while True:
        _, raw = client.brpop(result_queue_name, timeout=0)
        try:
            message = json.loads(raw)
        except Exception:  # noqa: BLE001
            logging.exception("result writer got malformed payload: %s", raw)
            continue

        status = str(message.get("status", "")).strip().lower()
        if status != "ok":
            logging.error("result writer got error message: %s", message)
            continue

        payload = message.get("payload")
        if not isinstance(payload, dict) or "os" not in payload:
            logging.error("result writer got invalid payload shape: %s", message)
            continue

        try:
            write_payload_atomic(payload_path, payload)
            logging.info("payload.json updated at %s", payload_path)
        except Exception:  # noqa: BLE001
            logging.exception("result writer failed to write payload")


if __name__ == "__main__":
    run_writer()
