"""PCB Analyzer — core package."""
from pathlib import Path

try:
    __version__ = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    __version__ = "0.6.28"
