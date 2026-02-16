from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict


def write_payload_atomic(payload_path: Path, payload: Dict[str, Dict[str, str]]) -> None:
    """Write payload.json atomically to keep file consistent on failures."""
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=payload_path.parent,
        delete=False,
    ) as temp_file:
        json.dump(payload, temp_file, indent=2, ensure_ascii=False)
        temp_file.write("\n")
        temp_name = temp_file.name

    Path(temp_name).replace(payload_path)
