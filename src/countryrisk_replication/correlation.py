"""Compatibility facade for country-risk correlation tools.

The implementation lives in focused modules:
discovery, panel, stats, output, pipeline, and cli. This module keeps older
imports working for notebooks, scripts, and tests that used
countryrisk_replication.correlation directly.
"""

from __future__ import annotations

from countryrisk_replication.cli import main, parse_args, parse_countries
from countryrisk_replication.discovery import (
    CODE_TO_COUNTRY_SLUG,
    COUNTRY_SLUG_TO_CODE,
    country_code_from_reproduced_file,
    discover_reproduced_files,
)
from countryrisk_replication.output import (
    GVKEY_QUARTER_FIELDS,
    MANIFEST_FIELDS,
    QUARTER_FIELDS,
    build_output_rows,
    file_sha256,
    write_csv,
    write_manifest,
)
from countryrisk_replication.panel import (
    QUARTER_DTYPE,
    SCORE_SCALE,
    DtaPanelResult,
    ReproducedPanelResult,
    build_reproduced_panel,
    load_dta_panel,
    normalize_gvkey_series,
    quarter_code_from_date_like,
    quarter_label,
    stata_internal_carry_forward,
)
from countryrisk_replication.pipeline import DTA_FILE, OUT_DIR, REPRODUCED_DIR, RunConfig, RunResult, run
from countryrisk_replication.stats import (
    VARIANTS,
    CorrelationResult,
    QuarterSums,
    RunningStats,
    VariantConfig,
    add_quarter_stats,
    correlate_panels,
)
from countryrisk_replication.utils import ProgressLogger, default_logger, elapsed

__all__ = [
    "CODE_TO_COUNTRY_SLUG",
    "COUNTRY_SLUG_TO_CODE",
    "DTA_FILE",
    "GVKEY_QUARTER_FIELDS",
    "MANIFEST_FIELDS",
    "OUT_DIR",
    "QUARTER_DTYPE",
    "QUARTER_FIELDS",
    "REPRODUCED_DIR",
    "SCORE_SCALE",
    "VARIANTS",
    "CorrelationResult",
    "DtaPanelResult",
    "ProgressLogger",
    "QuarterSums",
    "ReproducedPanelResult",
    "RunConfig",
    "RunResult",
    "RunningStats",
    "VariantConfig",
    "add_quarter_stats",
    "build_output_rows",
    "build_reproduced_panel",
    "correlate_panels",
    "country_code_from_reproduced_file",
    "default_logger",
    "discover_reproduced_files",
    "elapsed",
    "file_sha256",
    "load_dta_panel",
    "main",
    "normalize_gvkey_series",
    "parse_args",
    "parse_countries",
    "quarter_code_from_date_like",
    "quarter_label",
    "run",
    "stata_internal_carry_forward",
    "write_csv",
    "write_manifest",
]


if __name__ == "__main__":
    main()
