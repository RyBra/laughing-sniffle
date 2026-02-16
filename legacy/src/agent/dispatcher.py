from __future__ import annotations

import logging
from pathlib import Path
from queue import Full, Queue

INVENTORY_COMMAND = "inventory"


def dispatch_commands(
    commands_file: Path,
    task_queue: Queue,
    put_timeout_seconds: float,
) -> int:
    """
    Read commands from file and enqueue only allowed commands.

    Returns count of successfully queued inventory tasks.
    """
    if not commands_file.exists():
        raise FileNotFoundError(f"Commands file not found: {commands_file}")

    accepted = 0
    for line in commands_file.read_text(encoding="utf-8").splitlines():
        command = line.strip().lower()
        if not command:
            continue

        if command != INVENTORY_COMMAND:
            logging.info("Ignored unsupported command: %s", line.strip())
            continue

        try:
            task_queue.put(INVENTORY_COMMAND, timeout=put_timeout_seconds)
            accepted += 1
            logging.info("Queued command: %s", INVENTORY_COMMAND)
        except Full:
            logging.error("Task queue overflow: inventory command skipped")

    return accepted
