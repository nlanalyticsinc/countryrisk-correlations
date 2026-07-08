"""Correlation pipeline for reproduced country-risk scores."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd

from countryrisk_replication.discovery import discover_reproduced_files
from countryrisk_replication.output import (
    GVKEY_QUARTER_FIELDS,
    QUARTER_FIELDS,
    build_output_rows,
    write_csv,
    write_manifest,
)
from countryrisk_replication.panel import build_reproduced_panel, load_dta_panel, quarter_label
from countryrisk_replication.stats import correlate_panels
from countryrisk_replication.utils import ProgressLogger, default_logger, elapsed

DTA_FILE = Path("data/original/FirmCountryQuarter_withexposure.dta")
REPRODUCED_DIR = Path("data/reproduced_v1.0")
OUT_DIR = Path("data/correlations")


@dataclass(frozen=True)
class RunConfig:
    dta_file: Path = DTA_FILE
    reproduced_dir: Path = REPRODUCED_DIR
    out_dir: Path = OUT_DIR
    countries: set[str] | None = None
    csv_chunk_size: int = 250_000
    dta_chunk_size: int = 500_000


@dataclass(frozen=True)
class RunResult:
    gvkey_quarter_rows: pd.DataFrame
    quarter_rows: pd.DataFrame
    gvkey_quarter_path: Path
    quarter_path: Path
    manifest_path: Path
    countries: tuple[str, ...]


def run(config: RunConfig, logger: ProgressLogger | None = default_logger) -> RunResult:
    start = perf_counter()
    files = discover_reproduced_files(config.reproduced_dir, config.countries, logger=logger)
    country_ids = {code: index for index, code in enumerate(sorted(files), start=1)}
    if logger is not None:
        logger(f"Countries: {', '.join(sorted(files))}")

    dta = load_dta_panel(
        config.dta_file,
        country_ids,
        config.dta_chunk_size,
        logger=logger,
    )
    if logger is not None:
        logger(f"DTA quarter range: {quarter_label(dta.quarter_start)}-{quarter_label(dta.quarter_end)}")

    reproduced = build_reproduced_panel(
        files,
        country_ids,
        config.csv_chunk_size,
        dta.quarter_start,
        dta.quarter_end,
        logger=logger,
    )
    if logger is not None:
        logger(f"Reproduced panel rows, union observed/filled: {len(reproduced.panel):,}")

    correlations = correlate_panels(
        dta.panel,
        reproduced.panel,
        config.dta_chunk_size,
        logger=logger,
    )
    gvkey_rows, quarter_rows = build_output_rows(
        correlations.stats,
        correlations.quarter_acc,
        dta.rows_by_country,
        reproduced.observed_counts,
        reproduced.filled_counts,
        country_ids,
        files,
    )

    gvkey_quarter_path = config.out_dir / "gvkey_quarter_correlations.csv"
    quarter_path = config.out_dir / "quarter_correlations.csv"
    manifest_path = config.out_dir / "data_manifest.csv"
    write_csv(gvkey_quarter_path, gvkey_rows, GVKEY_QUARTER_FIELDS)
    write_csv(quarter_path, quarter_rows, QUARTER_FIELDS)
    write_manifest(
        manifest_path,
        dta_file=config.dta_file,
        dta_rows=dta.total_rows,
        reproduced_files=files,
        reproduced_row_counts=reproduced.row_counts,
        country_ids=country_ids,
    )
    if logger is not None:
        logger(f"Wrote {gvkey_quarter_path}")
        logger(f"Wrote {quarter_path}")
        logger(f"Wrote {manifest_path}")
        logger(f"Done in {elapsed(start)}.")
    return RunResult(
        gvkey_quarter_rows=gvkey_rows,
        quarter_rows=quarter_rows,
        gvkey_quarter_path=gvkey_quarter_path,
        quarter_path=quarter_path,
        manifest_path=manifest_path,
        countries=tuple(sorted(files)),
    )
