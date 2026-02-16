FROM python:3.10-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── runtime ──────────────────────────────────
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local

COPY proto /app/proto
COPY services /app/services
COPY legacy /app/legacy

CMD ["python", "-m", "services.result_writer.worker"]
