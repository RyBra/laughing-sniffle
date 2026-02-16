FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY proto /app/proto
COPY services /app/services
COPY legacy /app/legacy

CMD ["python", "-m", "services.result_writer.worker"]
