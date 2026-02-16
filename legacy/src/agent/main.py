from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread
from typing import Any

from legacy.src.agent.config import AppConfig, load_config
from legacy.src.agent.dispatcher import INVENTORY_COMMAND, dispatch_commands
from legacy.src.agent.inventory.windows_registry import collect_windows_inventory
from legacy.src.agent.logging_setup import setup_logging
from legacy.src.agent.result_writer import write_payload_atomic

TASK_STOP = object()
RESULT_STOP = object()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Windows inventory agent")
    parser.add_argument(
        "--commands",
        required=True,
        help="Path to text file with commands",
    )
    return parser.parse_args()


def _try_put(queue_obj: Queue, value: Any, timeout_seconds: float, attempts: int) -> bool:
    for _ in range(attempts):
        try:
            queue_obj.put(value, timeout=timeout_seconds)
            return True
        except Full:
            continue
    return False


def inventory_worker(
    worker_id: int,
    task_queue: Queue,
    result_queue: Queue,
    config: AppConfig,
) -> None:
    while True:
        task = task_queue.get()
        try:
            if task is TASK_STOP:
                logging.debug("Worker-%s received stop signal", worker_id)
                return

            if task != INVENTORY_COMMAND:
                logging.warning("Worker-%s got unknown task: %s", worker_id, task)
                continue

            try:
                payload: dict[str, Any] = collect_windows_inventory()
                if not payload["os"].get("DisplayVersion"):
                    logging.warning(
                        "Worker-%s: DisplayVersion missing; fallback value may be used",
                        worker_id,
                    )
            except Exception as exc:
                logging.exception("Worker-%s failed to collect inventory", worker_id)
                payload = {"error": str(exc)}

            if not _try_put(
                result_queue,
                payload,
                timeout_seconds=config.queue.put_timeout_seconds,
                attempts=3,
            ):
                logging.error("Result queue overflow: result dropped by Worker-%s", worker_id)
        finally:
            task_queue.task_done()


def result_writer(
    result_queue: Queue,
    payload_path: Path,
    workers_count: int,
) -> None:
    stopped_workers = 0
    while stopped_workers < workers_count:
        try:
            result = result_queue.get(timeout=0.5)
        except Empty:
            continue

        try:
            if result is RESULT_STOP:
                stopped_workers += 1
                continue

            if "os" not in result:
                logging.error("ResultWriter got error payload: %s", result)
                continue

            write_payload_atomic(payload_path, result)
            logging.info("payload.json updated: %s", payload_path)
        except Exception:
            logging.exception("ResultWriter failed to write payload")
        finally:
            result_queue.task_done()


def main() -> int:
    args = parse_args()
    script_dir = Path(sys.argv[0]).resolve().parent
    config_path = script_dir / "config.ini"
    payload_path = script_dir / "payload.json"

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
        log_file = setup_logging(config.logging.log_path, config.logging.level)
    except Exception as exc:
        print(f"Failed to initialize app: {exc}", file=sys.stderr)
        return 1

    logging.info("Agent started, log file: %s", log_file)
    task_queue: Queue = Queue(maxsize=config.queue.tasks_maxsize)
    result_queue: Queue = Queue(maxsize=config.queue.results_maxsize)

    writer_thread = Thread(
        target=result_writer,
        args=(result_queue, payload_path, config.workers.inventory_workers),
        daemon=True,
        name="ResultWriter",
    )
    writer_thread.start()

    workers = [
        Thread(
            target=inventory_worker,
            args=(idx + 1, task_queue, result_queue, config),
            daemon=True,
            name=f"InventoryWorker-{idx + 1}",
        )
        for idx in range(config.workers.inventory_workers)
    ]
    for worker in workers:
        worker.start()

    exit_code = 0
    try:
        accepted = dispatch_commands(
            commands_file=Path(args.commands),
            task_queue=task_queue,
            put_timeout_seconds=config.queue.put_timeout_seconds,
        )
        logging.info("Dispatch finished, accepted inventory commands: %s", accepted)
    except Exception:
        logging.exception("Dispatcher failed")
        exit_code = 1
    finally:
        for _ in workers:
            _try_put(
                task_queue,
                TASK_STOP,
                timeout_seconds=config.queue.put_timeout_seconds,
                attempts=100,
            )

    task_queue.join()
    for worker in workers:
        worker.join(timeout=2)

    for _ in workers:
        _try_put(
            result_queue,
            RESULT_STOP,
            timeout_seconds=config.queue.put_timeout_seconds,
            attempts=100,
        )

    result_queue.join()
    writer_thread.join(timeout=2)
    logging.info("Agent finished")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
