from __future__ import annotations

import json
import logging
import os
import uuid
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path
from queue import Full
from typing import Any, cast

import grpc
import redis

from legacy.src.agent.dispatcher import dispatch_commands
from legacy.src.agent.logging_setup import setup_logging
from proto import agent_pb2, agent_pb2_grpc

_agent_pb2 = cast(Any, agent_pb2)
HealthResponse = _agent_pb2.HealthResponse
RunResponse = _agent_pb2.RunResponse


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


class RedisTaskQueueAdapter:
    def __init__(
        self,
        redis_client: redis.Redis,
        queue_name: str,
        maxsize: int,
    ) -> None:
        self._redis = redis_client
        self._queue_name = queue_name
        self._maxsize = maxsize

    def put(self, command: str, timeout: float | None = None) -> None:
        del timeout
        if self._maxsize > 0:
            current_size = self._redis.llen(self._queue_name)
            if current_size >= self._maxsize:
                raise Full("Redis task queue overflow")

        message = {
            "task_id": str(uuid.uuid4()),
            "command": command,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._redis.lpush(self._queue_name, json.dumps(message, ensure_ascii=False))


class AgentGatewayServicer(agent_pb2_grpc.AgentGatewayServicer):
    def __init__(
        self,
        redis_client: redis.Redis,
        task_queue_name: str,
        task_queue_maxsize: int,
        put_timeout_seconds: float,
    ) -> None:
        self._redis = redis_client
        self._task_queue_name = task_queue_name
        self._task_queue_maxsize = task_queue_maxsize
        self._put_timeout_seconds = put_timeout_seconds

    def Run(self, request: Any, context: grpc.ServicerContext) -> Any:
        commands_file = Path(request.commands_file)
        if not commands_file.exists():
            return RunResponse(ok=False, accepted=0, error="commands file not found")

        queue_adapter = RedisTaskQueueAdapter(
            redis_client=self._redis,
            queue_name=self._task_queue_name,
            maxsize=self._task_queue_maxsize,
        )
        try:
            accepted = dispatch_commands(
                commands_file=commands_file,
                task_queue=queue_adapter,  # type: ignore[arg-type]
                put_timeout_seconds=self._put_timeout_seconds,
            )
            logging.info("Run accepted %s commands from %s", accepted, commands_file)
            return RunResponse(ok=True, accepted=accepted, error="")
        except Exception as exc:
            logging.exception("Failed to dispatch commands from %s", commands_file)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return RunResponse(ok=False, accepted=0, error=str(exc))

    def Health(self, request: Any, context: grpc.ServicerContext) -> Any:
        del request, context
        return HealthResponse(ok=True, service="agent-gateway")


def serve() -> None:
    log_dir = Path(_env_str("LOG_DIR", "."))
    log_level = _env_str("LOG_LEVEL", "info")
    setup_logging(log_dir, log_level)

    redis_host = _env_str("REDIS_HOST", "localhost")
    redis_port = _env_int("REDIS_PORT", 6379)
    task_queue_name = _env_str("TASK_QUEUE_NAME", "inventory_tasks")
    task_queue_maxsize = _env_int("TASK_QUEUE_MAXSIZE", 100)
    put_timeout_seconds = _env_float("PUT_TIMEOUT_SECONDS", 2.0)
    grpc_host = _env_str("GRPC_HOST", "0.0.0.0")
    grpc_port = _env_int("GRPC_PORT", 50051)
    max_workers = _env_int("GRPC_WORKERS", 10)

    redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    redis_client.ping()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    agent_pb2_grpc.add_AgentGatewayServicer_to_server(
        AgentGatewayServicer(
            redis_client=redis_client,
            task_queue_name=task_queue_name,
            task_queue_maxsize=task_queue_maxsize,
            put_timeout_seconds=put_timeout_seconds,
        ),
        server,
    )

    listen_addr = f"{grpc_host}:{grpc_port}"
    server.add_insecure_port(listen_addr)
    server.start()
    logging.info("agent-gateway listening on %s", listen_addr)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
