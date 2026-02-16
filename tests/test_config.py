from __future__ import annotations

from pathlib import Path

import pytest

from legacy.src.agent.config import load_config


@pytest.fixture()
def valid_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "[logging]\n"
        "level = info\n"
        f"log_path = {tmp_path}\n"
        "\n"
        "[workers]\n"
        "InventoryWorkers = 2\n"
        "\n"
        "[queue]\n"
        "tasks_maxsize = 50\n"
        "results_maxsize = 50\n"
        "put_timeout_seconds = 1.5\n",
        encoding="utf-8",
    )
    return cfg


class TestLoadConfig:
    def test_valid_config(self, valid_config: Path, tmp_path: Path) -> None:
        cfg = load_config(valid_config)
        assert cfg.logging.level == "info"
        assert cfg.workers.inventory_workers == 2
        assert cfg.queue.tasks_maxsize == 50
        assert cfg.queue.results_maxsize == 50
        assert cfg.queue.put_timeout_seconds == 1.5

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.ini")

    def test_invalid_workers_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[logging]\nlevel = info\n\n"
            "[workers]\nInventoryWorkers = 0\n\n"
            "[queue]\ntasks_maxsize = 10\nresults_maxsize = 10\nput_timeout_seconds = 1.0\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="InventoryWorkers"):
            load_config(cfg)

    def test_invalid_queue_maxsize_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[logging]\nlevel = info\n\n"
            "[workers]\nInventoryWorkers = 1\n\n"
            "[queue]\ntasks_maxsize = 0\nresults_maxsize = 10\nput_timeout_seconds = 1.0\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="maxsize"):
            load_config(cfg)

    def test_invalid_put_timeout_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[logging]\nlevel = info\n\n"
            "[workers]\nInventoryWorkers = 1\n\n"
            "[queue]\ntasks_maxsize = 10\nresults_maxsize = 10\nput_timeout_seconds = -1\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="put_timeout_seconds"):
            load_config(cfg)

    def test_defaults_applied(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[logging]\n[workers]\n[queue]\n", encoding="utf-8")
        result = load_config(cfg)
        assert result.logging.level == "info"
        assert result.workers.inventory_workers == 1
        assert result.queue.tasks_maxsize == 100
        assert result.queue.results_maxsize == 100
        assert result.queue.put_timeout_seconds == 2.0
