"""Validated per-user settings stored as a small JSON configuration file."""
import json
import os
from pathlib import Path

DEFAULTS = {
    "application_name": "PCB Analyzer",
    "subtitle": "Analysis & Diagnostics Workbench",
    "ollama_host": "http://127.0.0.1:11434",
    "ollama_model": "llama3",
    "theme": "dark",
}


def settings_path():
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return os.path.join(root, "pcb-analyzer", "settings.json")


def load_settings(path=None):
    """Load supported settings, falling back safely when the file is absent/bad."""
    result = dict(DEFAULTS)
    target = path or settings_path()
    try:
        with open(target, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        if isinstance(data, dict):
            for key in DEFAULTS:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    result[key] = value.strip()
    except (OSError, ValueError, TypeError):
        pass
    if result["theme"] not in ("dark", "light"):
        result["theme"] = DEFAULTS["theme"]
    return result


def save_settings(settings, path=None):
    """Atomically save only recognized settings with private user permissions."""
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        value = settings.get(key, DEFAULTS[key])
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()
    if values["theme"] not in ("dark", "light"):
        raise ValueError("theme must be 'dark' or 'light'")
    target = os.path.abspath(os.path.expanduser(path or settings_path()))
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    temp = target + ".tmp"
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(values, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
        os.chmod(target, 0o600)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
    return target
