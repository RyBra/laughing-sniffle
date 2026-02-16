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

## Legacy режим (подробно)

Legacy-агент -- однопроцессное приложение на стандартной библиотеке Python (`threading` + `queue`).
Весь код вынесен в отдельную папку `legacy/` со своим `legacy/requirements.txt` (внешних зависимостей нет).

### Архитектура

Агент использует паттерн **producer-consumer** внутри одного процесса:

1. **main.py** -- точка входа. Принимает CLI-аргумент `--commands`, загружает конфигурацию, создаёт очереди `task_queue` и `result_queue`, запускает потоки воркеров и писателя результатов.
2. **dispatcher.py** -- читает файл команд построчно, фильтрует только `inventory` (остальные игнорирует), кладёт задачи в `task_queue`. Обрабатывает переполнение очереди с таймаутом.
3. **inventory/windows_registry.py** -- собирает данные из реестра Windows (`HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion`): `ProductName`, `DisplayVersion`, `CurrentBuild`, `UBR`, `InstallDate`, `EditionID`.
4. **result_writer.py** -- атомарно записывает `payload.json` (через временный файл + rename).
5. **config.py** -- загружает и валидирует `config.ini`.
6. **logging_setup.py** -- настройка логирования в файл `log.txt` (уровень задаётся в конфиге).

```mermaid
flowchart LR
    CLI["CLI: --commands"] --> Main["main.py"]
    Main --> Dispatcher["dispatcher.py"]
    Dispatcher -->|task_queue| Workers["inventory_worker x N"]
    Workers -->|result_queue| Writer["result_writer"]
    Writer --> Payload["payload.json"]
```

### Структура файлов

```
legacy/
├── requirements.txt          # пустой -- только stdlib
└── src/agent/
    ├── main.py               # точка входа, потоки, shutdown
    ├── dispatcher.py          # разбор команд, валидация
    ├── config.py              # загрузка config.ini
    ├── config.ini             # конфигурация
    ├── logging_setup.py       # настройка логов
    ├── result_writer.py       # атомарная запись payload.json
    └── inventory/
        └── windows_registry.py  # сбор данных из реестра
```

### Конфигурация (`config.ini`)

```ini
[logging]
level = info
log_path = .

[workers]
InventoryWorkers = 1

[queue]
tasks_maxsize = 100
results_maxsize = 100
put_timeout_seconds = 2.0
```

- `InventoryWorkers` -- количество потоков-воркеров (масштабирование внутри процесса).
- `tasks_maxsize` / `results_maxsize` -- защита от переполнения очередей.
- `put_timeout_seconds` -- таймаут записи в очередь (повторяет до 3 раз).

### Потоки и очереди

- **Main thread** -- инициализация, запуск потоков, отправка sentinel-объектов (`TASK_STOP`, `RESULT_STOP`) для graceful shutdown.
- **Worker threads** (daemon) -- `N` штук, читают из `task_queue`, вызывают `collect_windows_inventory()`, пишут результат в `result_queue`.
- **Result writer thread** (daemon) -- один, читает из `result_queue`, валидирует payload (наличие ключа `"os"`), атомарно пишет файл.

### Обработка ошибок

- Отсутствие конфига / невалидные параметры -- ошибка при старте.
- Ошибка сбора инвентаризации -- воркер логирует ошибку, кладёт в `result_queue` payload со статусом `error`, не падает.
- Переполнение очереди -- `_try_put()` повторяет до 3 раз с таймаутом, затем логирует ошибку и сбрасывает задачу.

### Запуск

```bash
python legacy/src/agent/main.py --commands commands.txt
```

### Выходные файлы

- `payload.json` -- результат инвентаризации (атомарная запись).
- `log.txt` -- журнал работы (append, путь настраивается в `config.ini`).

---

## Сравнение: Legacy vs Микросервисы

### Обзор

| Характеристика | Legacy (threading + queue) | Микросервисы (gRPC + Redis) |
|---|---|---|
| Процессы | 1 | 3+ (gateway, inventory, writer, redis) |
| Внешние зависимости | Нет (stdlib) | grpcio, protobuf, redis |
| Инфраструктура | Не нужна | Docker, Redis |
| Масштабирование | Потоки внутри процесса | Горизонтальное (контейнеры) |
| Health checks | Нет | gRPC Health на каждом сервисе |
| Контейнеризация | Не предусмотрена | Docker Compose |

### Legacy: плюсы

1. **Простота запуска** -- одна команда, один процесс, никакой инфраструктуры:

   ```bash
   python legacy/src/agent/main.py --commands commands.txt
   ```

   В микросервисной версии нужно поднять Redis, gateway, writer и отдельно запустить inventory-worker.

2. **Нет внешних зависимостей** -- `legacy/requirements.txt` пуст, используется только стандартная библиотека Python. Микросервисная версия требует `grpcio`, `protobuf`, `redis`.

3. **Простая отладка** -- все потоки внутри одного процесса, один лог-файл, стандартный Python debugger работает напрямую. В микросервисах логи разнесены по контейнерам.

4. **Быстрое взаимодействие компонентов** -- очередь `Queue(maxsize=100)` работает в памяти процесса без сетевых задержек:

   ```python
   task_queue = Queue(maxsize=config.queue.tasks_maxsize)
   ```

   В микросервисах аналогичная функциональность реализована через Redis и адаптер `RedisTaskQueueAdapter`, который проверяет `LLEN` и выполняет `LPUSH` по сети.

5. **Атомарность shutdown** -- main thread отправляет sentinel-объекты и вызывает `task_queue.join()`, гарантируя обработку всех задач перед завершением. В микросервисах координация остановки сложнее (нужно останавливать контейнеры в правильном порядке).

### Legacy: минусы

1. **Ограничен одним хостом** -- все компоненты работают в одном процессе на одной машине. Нельзя распределить нагрузку между серверами.

2. **GIL Python** -- `threading` не дает истинной параллельности для CPU-bound задач. Увеличение `InventoryWorkers` в `config.ini` не ускоряет CPU-операции. Микросервисы запускают воркеры в отдельных процессах/контейнерах.

3. **Нет горизонтального масштабирования** -- в legacy количество воркеров задаётся в `config.ini`:

   ```ini
   [workers]
   InventoryWorkers = 1
   ```

   В микросервисах можно запустить произвольное число контейнеров:

   ```bash
   docker compose up --scale inventory-service=5
   ```

4. **Нет health checks** -- невозможно проверить состояние агента извне. Микросервисы предоставляют gRPC `Health` endpoint на каждом сервисе (порты 50051, 50052, 50053).

5. **Отказоустойчивость** -- падение процесса останавливает весь пайплайн. В микросервисах падение одного воркера не влияет на остальные; задачи остаются в Redis до перезапуска.

6. **Нет контейнеризации** -- legacy требует предустановленного Python и Windows. Микросервисы упакованы в Docker-образы с фиксированным окружением.

### Микросервисы: плюсы

1. **Горизонтальное масштабирование** -- каждый сервис масштабируется независимо через Docker Compose или оркестратор.

2. **Изоляция сбоев** -- ошибка в `inventory-service` не роняет `result-writer` или `agent-gateway`. Задачи сохраняются в Redis и будут обработаны после перезапуска воркера.

3. **Health checks** -- каждый сервис имеет gRPC `Health` endpoint, что позволяет интегрироваться с системами мониторинга и оркестраторами (Kubernetes, Docker healthcheck).

4. **Гибкость развертывания** -- inventory-worker запускается на Windows-хосте (где доступен `winreg`), остальные сервисы -- в Linux-контейнерах. В legacy все компоненты должны быть на одной Windows-машине.

5. **Расширяемость** -- добавление нового типа воркера (например, `audit-service`) не затрагивает существующие сервисы -- достаточно подписаться на новую очередь в Redis.

### Микросервисы: минусы

1. **Сложность инфраструктуры** -- требуется Redis, Docker, gRPC. Больше точек отказа, больше конфигурации (переменные окружения на каждый сервис).

2. **Сетевые задержки** -- каждое взаимодействие проходит через Redis по сети (`LPUSH` / `BRPOP`), что медленнее in-memory `Queue`.

3. **Сложнее локальная разработка** -- для запуска нужен Docker, а inventory-worker все равно требует Windows. В legacy достаточно `python main.py`.

4. **Мониторинг** -- логи разнесены по контейнерам, требуется агрегация (ELK, Loki и т.п.). В legacy -- один файл `log.txt`.

5. **Дополнительный код** -- адаптеры, protobuf-определения, Dockerfile'ы, docker-compose.yml увеличивают объем и сложность кодовой базы.

### Когда что использовать

- **Legacy** -- быстрое прототипирование, запуск на одном хосте, минимальная инфраструктура, простые сценарии с небольшим объемом задач.
- **Микросервисы** -- продакшен с требованиями к масштабированию, отказоустойчивости, мониторингу и гибкому развертыванию (например, inventory-worker на Windows, остальное в облаке).

---

## Developer Experience (DevEx)

В проекте настроен полный набор инструментов для удобной разработки и развёртывания.

### Быстрый старт

```bash
make install            # создать venv + установить все зависимости (включая dev)
source .venv/bin/activate
pre-commit install      # установить git-хуки
```

### Makefile

Все типовые команды собраны в `Makefile`. Список целей:

```bash
make help               # показать все доступные цели
make up                 # docker compose up --build -d
make down               # docker compose down
make restart            # restart = down + up
make logs               # docker compose logs -f
make proto              # перегенерировать gRPC stubs из proto/agent.proto
make lint               # ruff check .
make fmt                # ruff format + fix
make typecheck          # mypy services/ legacy/
make test               # pytest -v
make check              # lint + typecheck + test (все проверки разом)
make clean              # удалить кеши и артефакты сборки
```

### Управление зависимостями

- `pyproject.toml` -- единая точка конфигурации проекта (PEP 621): runtime-зависимости с пинами мажорных версий, dev-зависимости (ruff, mypy, pytest, pre-commit), настройки всех инструментов.
- `requirements.txt` -- runtime-зависимости для Docker-сборки (пины совпадают с pyproject.toml).
- `.env.example` -- документация всех переменных окружения с дефолтными значениями.

### Линтинг, форматирование, type checking

- **ruff** -- быстрый линтер + форматтер (заменяет flake8, isort, black). Конфигурация в `pyproject.toml`.
- **mypy** -- статическая проверка типов. Особенно полезен для gRPC-кода.
- **pre-commit** -- автоматический запуск ruff и базовых проверок (trailing whitespace, end-of-file, YAML/JSON валидация) перед каждым коммитом.

### Тестирование

Unit-тесты в `tests/` покрывают ключевые модули legacy-кода (не требуют Windows):

- `test_dispatcher.py` -- `dispatch_commands()`: корректные и неизвестные команды, пустой файл, переполнение очереди, case-insensitivity.
- `test_config.py` -- `load_config()`: валидный конфиг, отсутствие файла, невалидные значения, дефолты.
- `test_result_writer.py` -- `write_payload_atomic()`: корректная запись, создание директорий, атомарность, формат.

```bash
make test               # или: pytest -v
```

### CI/CD (GitHub Actions)

Файл `.github/workflows/ci.yml` запускается на каждый push/PR в `main`:

1. **lint** -- `ruff check` + `ruff format --check`
2. **typecheck** -- `mypy`
3. **test** -- `pytest`

Все три джоба запускаются параллельно на `ubuntu-latest` с Python 3.10.

### Docker

- **Multi-stage Dockerfiles** -- `builder` stage устанавливает зависимости, `runtime` stage копирует только site-packages и код. Уменьшает размер итоговых образов.
- **Health checks в docker-compose.yml**:
  - `redis` -- `redis-cli ping`
  - `agent-gateway` -- gRPC Health endpoint
  - `depends_on: condition: service_healthy` -- сервисы стартуют только когда Redis готов.
- `.dockerignore` -- исключает `.git/`, `.venv/`, тесты, документацию из контекста сборки.

### Dev Container

`.devcontainer/devcontainer.json` позволяет запустить единое окружение разработки в VS Code, Cursor или GitHub Codespaces:

- Python 3.10, Docker-in-Docker.
- Автоматическая установка зависимостей и pre-commit хуков.
- Рекомендованные расширения: ruff, mypy, proto3 syntax.
- Проброс портов: 50051 (gRPC), 6379 (Redis).

### Гигиена репозитория

- `.gitignore` -- исключает `__pycache__/`, `.venv/`, `data/`, `logs/`, кеши инструментов.
- `.dockerignore` -- минимизирует контекст Docker-сборки.
- `.editorconfig` -- единый стиль отступов и кодировки (4 пробела для Python, 2 для YAML/JSON/proto, табы для Makefile).

