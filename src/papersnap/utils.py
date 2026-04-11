"""Shared utilities: Rich console, path helpers, base64 encoding."""

import base64
from pathlib import Path

from rich.console import Console

console = Console()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def encode_png_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")
