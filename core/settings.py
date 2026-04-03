"""
core/settings.py
Persists app preferences to %APPDATA%/DragonwildsManager/settings.json
"""

import json
import os
from pathlib import Path

_APP_DIR  = Path(os.getenv("APPDATA", ".")) / "DragonwildsManager"
_SETTINGS = _APP_DIR / "settings.json"

DEFAULTS = {
    "install_dir":  str(Path.home() / "DragonWildsServer"),
    "server_exe":   "",          # overridden once found/chosen
    "owner_id":     "",
    "server_name":  "",
    "world_name":   "",
    "admin_pass":   "",
    "world_pass":   "",
    "port":         "7777",
    "window_x":     -1,
    "window_y":     -1,
}


def load() -> dict:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    if _SETTINGS.exists():
        try:
            data = json.loads(_SETTINGS.read_text(encoding="utf-8"))
            # fill in any missing keys from DEFAULTS
            for k, v in DEFAULTS.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULTS)


def save(data: dict) -> None:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")


def app_dir() -> Path:
    return _APP_DIR
