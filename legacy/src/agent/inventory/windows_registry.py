from __future__ import annotations

from typing import Dict


REG_PATH = r"Software\Microsoft\Windows NT\CurrentVersion"


def collect_windows_inventory() -> Dict[str, Dict[str, str]]:
    """Collect OS details from Windows registry."""
    try:
        import winreg
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


def _read_reg_string(winreg_module, key, name: str) -> str:
    try:
        value, _ = winreg_module.QueryValueEx(key, name)
    except FileNotFoundError:
        return ""
    return str(value)
