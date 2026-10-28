"""Build and write correlation output tables."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import pandas as pd

from countryrisk_replication.discovery import (
    CODE_TO_COUNTRY_SLUG,
    dataset_date,
    reproduced_file_label,
    reproduced_file_metadata,
)
from countryrisk_replication.panel import GvkeyCrosswalk, quarter_label
from countryrisk_replication.stats import VARIANTS, QuarterSums, RunningStats
from countryrisk_replication.utils import csv_compression

GVKEY_QUARTER_FIELDS = [
    "country_code",
    "country_slug",
    "metric",
    "variant",
    "level",
    "dta_value",
    "reproduced_value",
    "n_pairs",
    "n_dta_country_rows",
    "n_reproduced_observed_gvkey_quarters",
    "n_reproduced_filled_gvkey_quarters",
    "reproduced_file",
    "pearson",
]

QUARTER_FIELDS = [
    "country_code",
    "country_slug",
    "metric",
    "variant",
    "level",
    "dta_value",
    "reproduced_value",
    "n_pairs",
    "matched_gvkey_quarters",
    "first_quarter",
    "last_quarter",
    "reproduced_file",
    "pearson",
]

MANIFEST_FIELDS = [
    "role",
    "country_code",
    "path",
    "source_layout",
    "dataset_date",
    "series_version",
    "series_id",
    "compression",
    "bytes",
    "rows",
    "sha256",
]


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_output_rows(
    stats: dict[tuple[int, str], RunningStats],
    quarter_acc: dict[tuple[int, int, str], QuarterSums],
    dta_rows_by_country: dict[int, int],
    observed_counts: dict[int, int],
    filled_counts: dict[int, int],
    country_ids: dict[str, int],
    files: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    id_to_country = {value: key for key, value in country_ids.items()}

    gvkey_rows = []
    for (country_id, variant), running in sorted(stats.items()):
        if running.n == 0:
            continue
        code = id_to_country[country_id]
        gvkey_rows.append(
            {
                "country_code": code,
                "country_slug": CODE_TO_COUNTRY_SLUG.get(code.lower(), "").replace("-", " "),
                "metric": "risk",
                "variant": variant,
                "level": "gvkey-quarter",
                "dta_value": "CountryRisk",
                "reproduced_value": VARIANTS[variant].description,
                "n_pairs": running.n,
                "n_dta_country_rows": dta_rows_by_country.get(country_id, 0),
                "n_reproduced_observed_gvkey_quarters": observed_counts.get(country_id, 0),
                "n_reproduced_filled_gvkey_quarters": filled_counts.get(country_id, 0),
                "reproduced_file": reproduced_file_label(files[code]),
                "pearson": running.pearson(),
            }
        )

    quarter_stats: dict[tuple[int, str], RunningStats] = defaultdict(RunningStats)
    quarter_counts: dict[tuple[int, str], list[int]] = defaultdict(list)
    for (country_id, quarter, variant), bucket in quarter_acc.items():
        count = bucket.n
        if count <= 0:
            continue
        dta_mean = bucket.dta_sum / count
        reproduced_mean = bucket.reproduced_sum / count
        quarter_stats[(country_id, variant)].add_arrays(
            pd.Series([dta_mean], dtype="float64"),
            pd.Series([reproduced_mean], dtype="float64"),
        )
        quarter_counts[(country_id, variant)].append(quarter)

    quarter_rows = []
    for (country_id, variant), running in sorted(quarter_stats.items()):
        code = id_to_country[country_id]
        quarters = sorted(quarter_counts[(country_id, variant)])
        quarter_rows.append(
            {
                "country_code": code,
                "country_slug": CODE_TO_COUNTRY_SLUG.get(code.lower(), "").replace("-", " "),
                "metric": "risk",
                "variant": variant,
                "level": "quarter",
                "dta_value": "mean CountryRisk across matched gvkey-quarters",
                "reproduced_value": f"quarter mean of {VARIANTS[variant].description}",
                "n_pairs": running.n,
                "matched_gvkey_quarters": stats[(country_id, variant)].n,
                "first_quarter": quarter_label(quarters[0]) if quarters else "",
                "last_quarter": quarter_label(quarters[-1]) if quarters else "",
                "reproduced_file": reproduced_file_label(files[code]),
                "pearson": running.pearson(),
            }
        )

    return pd.DataFrame(gvkey_rows), pd.DataFrame(quarter_rows)


def write_csv(path: Path, rows: pd.DataFrame, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = rows.reindex(columns=fieldnames)
    rows.to_csv(path, index=False, float_format="%.15g")


def write_manifest(
    path: Path,
    *,
    dta_file: Path,
    dta_rows: int,
    reproduced_files: dict[str, Path],
    reproduced_row_counts: dict[int, int],
    country_ids: dict[str, int],
    gvkey_crosswalk: GvkeyCrosswalk | None = None,
) -> None:
    rows = [
        {
            "role": "paper_dta",
            "country_code": "",
            "path": str(dta_file),
            "source_layout": "stata",
            "dataset_date": "",
            "series_version": "",
            "series_id": "",
            "compression": "none",
            "bytes": dta_file.stat().st_size,
            "rows": dta_rows,
            "sha256": file_sha256(dta_file),
        }
    ]
    for code, reproduced_file in sorted(reproduced_files.items()):
        country_id = country_ids[code]
        metadata = reproduced_file_metadata(reproduced_file)
        if metadata is None:
            raise ValueError(f"Could not determine reproduced-file metadata for {reproduced_file}")
        rows.append(
            {
                "role": "reproduced_csv",
                "country_code": code,
                "path": str(reproduced_file),
                "source_layout": metadata.source_layout,
                "dataset_date": metadata.dataset_date,
                "series_version": metadata.series_version,
                "series_id": metadata.series_id,
                "compression": csv_compression(reproduced_file) or "none",
                "bytes": reproduced_file.stat().st_size,
                "rows": reproduced_row_counts.get(country_id, ""),
                "sha256": file_sha256(reproduced_file),
            }
        )
    if gvkey_crosswalk is not None:
        crosswalk_file = gvkey_crosswalk.path
        rows.append(
            {
                "role": "gvkey_crosswalk",
                "country_code": "",
                "path": str(crosswalk_file),
                "source_layout": "",
                "dataset_date": dataset_date(crosswalk_file),
                "series_version": "",
                "series_id": "",
                "compression": csv_compression(crosswalk_file) or "none",
                "bytes": crosswalk_file.stat().st_size,
                "rows": gvkey_crosswalk.rows,
                "sha256": file_sha256(crosswalk_file),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).reindex(columns=MANIFEST_FIELDS).to_csv(path, index=False)
