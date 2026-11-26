"""Tiny JSON settings file stored locally on this PC (%LOCALAPPDATA%\\MoonlightVPN)."""
import json
import os

import core


def _path() -> str:
    return os.path.join(core.data_dir(), "settings.json")


def get(key: str, default=None):
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except (OSError, ValueError):
        return default


def set(key: str, value) -> None:  # noqa: A001
    data = {}
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data[key] = value
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(data, f)
