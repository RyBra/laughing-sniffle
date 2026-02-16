from __future__ import annotations

import importlib
from typing import Any

REG_PATH = r"Software\Microsoft\Windows NT\CurrentVersion"


def collect_windows_inventory() -> dict[str, dict[str, str]]:
    """Collect OS details from Windows registry."""
    try:
        winreg = importlib.import_module("winreg")
    except ImportError as exc:
        raise RuntimeError("winreg is available only on Windows") from exc

    fields = {
        "ProductName": "",
        "DisplayVersion": "",
        "CurrentBuild": "",
        "UBR": "",
        "InstallDate": "",
        "EditionID": "",
    }

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH) as key:
        for name in list(fields):
            fields[name] = _read_reg_string(winreg, key, name)

        if not fields["DisplayVersion"]:
            fields["DisplayVersion"] = _read_reg_string(winreg, key, "ReleaseId")

    return {"os": fields}


def _read_reg_string(winreg_module: Any, key: Any, name: str) -> str:
    try:
        value, _ = winreg_module.QueryValueEx(key, name)
    except FileNotFoundError:
        return ""
    return str(value)
