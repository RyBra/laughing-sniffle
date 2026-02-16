from __future__ import annotations

from pathlib import Path
from queue import Full, Queue

import pytest

from legacy.src.agent.dispatcher import dispatch_commands


@pytest.fixture()
def tmp_commands(tmp_path: Path) -> Path:
    return tmp_path / "commands.txt"


class TestDispatchCommands:
    def test_inventory_commands_accepted(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("inventory\ninventory\n", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=10)
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=1.0)
        assert accepted == 2
        assert q.qsize() == 2

    def test_unsupported_commands_ignored(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("audit\ninstall 7zip\nreboot\n", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=10)
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=1.0)
        assert accepted == 0
        assert q.empty()

    def test_mixed_commands(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("inventory\naudit\ninventory\nreboot\n", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=10)
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=1.0)
        assert accepted == 2

    def test_empty_file(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=10)
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=1.0)
        assert accepted == 0

    def test_blank_lines_skipped(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("\n\n  \ninventory\n\n", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=10)
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=1.0)
        assert accepted == 1

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_such_file.txt"
        q: Queue[str] = Queue(maxsize=10)
        with pytest.raises(FileNotFoundError):
            dispatch_commands(missing, q, put_timeout_seconds=1.0)

    def test_queue_overflow_skips_command(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("inventory\ninventory\ninventory\n", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=1)
        q.put("placeholder")  # fill the queue
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=0.01)
        assert accepted == 0

    def test_case_insensitive(self, tmp_commands: Path) -> None:
        tmp_commands.write_text("INVENTORY\nInventory\n", encoding="utf-8")
        q: Queue[str] = Queue(maxsize=10)
        accepted = dispatch_commands(tmp_commands, q, put_timeout_seconds=1.0)
        assert accepted == 2
