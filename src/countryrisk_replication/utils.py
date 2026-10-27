"""Shared utility types and helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter

import pandas as pd

ProgressLogger = Callable[[str], None]

GZIP_MAGIC = b"\x1f\x8b"


def default_logger(message: str) -> None:
    print(message, flush=True)


def elapsed(start: float) -> str:
    return f"{perf_counter() - start:.1f}s"


def csv_compression(path: Path) -> str | None:
    """Return "gzip" for gzip bytes, whatever the file name says.

    Files downloaded from a series page can be gzip-encoded under a plain .csv name.
    """
    with path.open("rb") as handle:
        return "gzip" if handle.read(2) == GZIP_MAGIC else None


def csv_columns(path: Path) -> set[str]:
    return set(pd.read_csv(path, nrows=0, compression=csv_compression(path)).columns)
