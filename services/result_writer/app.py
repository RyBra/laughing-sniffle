from __future__ import annotations

import logging
import os
from concurrent import futures
from pathlib import Path

import grpc

from proto import agent_pb2, agent_pb2_grpc
from legacy.src.agent.logging_setup import setup_logging


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


class ResultWriterHealthServicer(agent_pb2_grpc.ResultWriterServicer):
    def Health(
        self, request: agent_pb2.HealthRequest, context: grpc.ServicerContext
    ) -> agent_pb2.HealthResponse:
        del request, context
        return agent_pb2.HealthResponse(ok=True, service="result-writer")


def serve() -> None:
    log_dir = Path(_env_str("LOG_DIR", "."))
    log_level = _env_str("LOG_LEVEL", "info")
    setup_logging(log_dir, log_level)

    grpc_host = _env_str("GRPC_HOST", "0.0.0.0")
    grpc_port = _env_int("GRPC_PORT", 50053)
    max_workers = _env_int("GRPC_WORKERS", 5)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    agent_pb2_grpc.add_ResultWriterServicer_to_server(ResultWriterHealthServicer(), server)

    listen_addr = f"{grpc_host}:{grpc_port}"
    server.add_insecure_port(listen_addr)
    server.start()
    logging.info("result-writer health endpoint listening on %s", listen_addr)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
