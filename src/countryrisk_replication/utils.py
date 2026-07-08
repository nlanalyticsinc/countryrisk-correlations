"""Shared utility types and helpers."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

ProgressLogger = Callable[[str], None]


def default_logger(message: str) -> None:
    print(message, flush=True)


def elapsed(start: float) -> str:
    return f"{perf_counter() - start:.1f}s"
