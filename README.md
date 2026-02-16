# Windows Inventory Agent (test task)

Проект содержит две реализации:

- **legacy**: однопроцессный агент на `threading + queue` в `legacy/src/agent/`.
- **microservices**: сервисы `agent-gateway`, `inventory-service`, `result-writer` + Redis и gRPC.

## Микросервисная архитектура (gRPC + Redis)

### Компоненты

- `agent-gateway`:
  - gRPC API (`Run`, `Health`),
  - читает `commands.txt`,
  - валидирует команды через `legacy/src/agent/dispatcher.py`,
  - публикует задачи в Redis (`inventory_tasks`).

- `inventory-service`:
  - воркер, который читает задачи из Redis,
  - выполняет `collect_windows_inventory()` из `legacy/src/agent/inventory/windows_registry.py`,
  - публикует результат в Redis (`inventory_results`).
  - отдельный gRPC health endpoint в `services/inventory_service/app.py`.

- `result-writer`:
  - воркер, который читает результаты из Redis,
  - пишет `payload.json` атомарно через `legacy/src/agent/result_writer.py`.
  - отдельный gRPC health endpoint в `services/result_writer/app.py`.

- `redis`:
  - внешний брокер очередей задач/результатов.

### Контракты

- Protobuf: `proto/agent.proto`
- Сгенерированные stubs: `proto/agent_pb2.py`, `proto/agent_pb2_grpc.py`

### Структура

- `proto/agent.proto`
- `services/agent_gateway/app.py`
- `services/inventory_service/worker.py`
- `services/inventory_service/app.py`
- `services/result_writer/worker.py`
- `services/result_writer/app.py`
- `docker-compose.yml`

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt`:

- `grpcio`
- `grpcio-tools`
- `protobuf`
- `redis`

## Запуск микросервисной версии

### 1) Поднять Redis + gateway + writer

```bash
docker compose up --build
```

Это поднимет:

- `redis` на `localhost:6379`
- `agent-gateway` gRPC на `localhost:50051`
- `result-writer` воркер (пишет `./data/payload.json`)

### 2) Запустить inventory-worker на Windows-хосте

Важно: `winreg` доступен только на Windows.

```bash
set REDIS_HOST=127.0.0.1
set REDIS_PORT=6379
set TASK_QUEUE_NAME=inventory_tasks
set RESULT_QUEUE_NAME=inventory_results
set LOG_DIR=.
set LOG_LEVEL=info
python -m services.inventory_service.worker
```

### 3) Вызвать gRPC `Run` у gateway

Пример через Python:

```python
import grpc
from proto import agent_pb2, agent_pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = agent_pb2_grpc.AgentGatewayStub(channel)
resp = stub.Run(agent_pb2.RunRequest(commands_file="/workspace/commands.txt"))
print(resp)
```

Для контейнера `agent-gateway` файл команд должен быть доступен в контейнере.
В `docker-compose.yml` весь репозиторий примонтирован как `/workspace`, поэтому путь `/workspace/commands.txt` работает.

## Ожидаемый результат

- В `commands.txt` обрабатываются только команды `inventory`.
- `inventory-service` формирует payload по реестру Windows.
- `result-writer` записывает `payload.json` атомарно в `./data/payload.json`.
- Ошибки инвентаризации не роняют пайплайн: в очередь результатов отправляется сообщение со статусом `error`.

## Legacy режим (вынесен отдельно)

Legacy код вынесен в отдельную папку `legacy/` со своим `legacy/requirements.txt`.

Запуск:

```bash
python legacy/src/agent/main.py --commands commands.txt
```

