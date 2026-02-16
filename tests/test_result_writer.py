from __future__ import annotations

import json
from pathlib import Path

from legacy.src.agent.result_writer import write_payload_atomic


class TestWritePayloadAtomic:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "payload.json"
        payload = {"os": {"ProductName": "Windows 11", "CurrentBuild": "22631"}}

        write_payload_atomic(payload_path, payload)

        assert payload_path.exists()
        data = json.loads(payload_path.read_text(encoding="utf-8"))
        assert data == payload

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "nested" / "dir" / "payload.json"
        payload = {"os": {"ProductName": "Test"}}

        write_payload_atomic(payload_path, payload)

        assert payload_path.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "payload.json"
        payload_path.write_text("{}", encoding="utf-8")

        payload = {"os": {"ProductName": "Updated"}}
        write_payload_atomic(payload_path, payload)

        data = json.loads(payload_path.read_text(encoding="utf-8"))
        assert data["os"]["ProductName"] == "Updated"

    def test_file_ends_with_newline(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "payload.json"
        payload = {"os": {"ProductName": "Test"}}

        write_payload_atomic(payload_path, payload)

        content = payload_path.read_text(encoding="utf-8")
        assert content.endswith("\n")

    def test_json_is_indented(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "payload.json"
        payload = {"os": {"ProductName": "Test"}}

        write_payload_atomic(payload_path, payload)

        content = payload_path.read_text(encoding="utf-8")
        assert "  " in content  # indented with 2 spaces
