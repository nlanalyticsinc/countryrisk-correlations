"""Command line interface for country-risk reproduction correlations."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from countryrisk_replication.pipeline import DTA_FILE, OUT_DIR, REPRODUCED_DIR, RunConfig, run

DESCRIPTION = """Correlate reproduced NLA country-risk scores with the paper DTA panel."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--dta-file",
        type=Path,
        default=DTA_FILE,
        help=f"Paper-based firm-country-quarter DTA file. Defaults to {DTA_FILE}.",
    )
    parser.add_argument(
        "--reproduced-dir",
        type=Path,
        default=REPRODUCED_DIR,
        help=(
            "NLA country-risk dataset root, series directory, or legacy flat export directory. "
            f"Defaults to {REPRODUCED_DIR}."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help=f"Directory for generated correlation CSVs. Defaults to {OUT_DIR}.",
    )
    parser.add_argument(
        "--gvkeys-file",
        type=Path,
        help=(
            "GVKEY crosswalk (gvkeys.csv) for firm-level files without a gvkey column. Defaults to the "
            "gvkeys.csv(.gz) at the dataset root or the NLA_*_gvkeys.csv next to the firm-level files."
        ),
    )
    parser.add_argument(
        "--countries",
        help="Optional comma-separated ISO2 country list, useful for a quick test.",
    )
    parser.add_argument("--csv-chunk-size", type=int, default=250_000)
    parser.add_argument("--dta-chunk-size", type=int, default=500_000)
    return parser.parse_args()


def parse_countries(value: str | None) -> set[str] | None:
    if value is None:
        return None
    countries = {code.strip().upper() for code in re.split(r"[, ]+", value) if code.strip()}
    return countries or None


def main() -> None:
    args = parse_args()
    config = RunConfig(
        dta_file=args.dta_file,
        reproduced_dir=args.reproduced_dir,
        out_dir=args.out_dir,
        countries=parse_countries(args.countries),
        csv_chunk_size=args.csv_chunk_size,
        dta_chunk_size=args.dta_chunk_size,
        gvkeys_file=args.gvkeys_file,
    )
    run(config)
