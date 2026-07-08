"""Correlate reproduced NLA country-risk scores with the paper DTA panel.

The original paper-based measure is read from
data/original/FirmCountryQuarter_withexposure.dta. The DTA's CountryRisk
variable is already a normalized transcript-rate measure that has been
collapsed and backfilled by the original Stata import pipeline.

The reproduced NLA side uses 100000 * risk / nr_of_words at the call level,
collapses multiple calls in the same gvkey-quarter by a simple mean, and
reports both observed-only and Stata-style filled variants.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd

DTA_FILE = Path("data/original/FirmCountryQuarter_withexposure.dta")
REPRODUCED_DIR = Path("data/reproduced_v1.0")
OUT_DIR = Path("data/correlations")
SCORE_SCALE = 100000.0
QUARTER_DTYPE = "int32"

COUNTRY_SLUG_TO_CODE = {
    "argentina": "ar",
    "australia": "au",
    "belgium": "be",
    "brazil": "br",
    "canada": "ca",
    "chile": "cl",
    "china": "cn",
    "colombia": "co",
    "czech-republic": "cz",
    "egypt": "eg",
    "france": "fr",
    "germany": "de",
    "great-britain": "gb",
    "greece": "gr",
    "hong-kong": "hk",
    "hungary": "hu",
    "india": "in",
    "indonesia": "id",
    "iran": "ir",
    "ireland": "ie",
    "israel": "il",
    "italy": "it",
    "japan": "jp",
    "korea": "kr",
    "malaysia": "my",
    "mexico": "mx",
    "netherlands": "nl",
    "new-zealand": "nz",
    "nigeria": "ng",
    "norway": "no",
    "pakistan": "pk",
    "philippines": "ph",
    "poland": "pl",
    "russia": "ru",
    "saudi-arabia": "sa",
    "singapore": "sg",
    "south-africa": "za",
    "spain": "es",
    "sweden": "se",
    "switzerland": "ch",
    "taiwan": "tw",
    "thailand": "th",
    "turkey": "tr",
    "united-states": "us",
    "united-states-of-america": "us",
    "venezuela": "ve",
}

CODE_TO_COUNTRY_SLUG = {
    code: slug for slug, code in COUNTRY_SLUG_TO_CODE.items() if slug != "united-states-of-america"
}


@dataclass(frozen=True, slots=True)
class VariantConfig:
    column: str
    description: str


VARIANTS = {
    "observed": VariantConfig(
        column="rep_observed_risk",
        description="mean(100000 * risk / nr_of_words)",
    ),
    "filled": VariantConfig(
        column="rep_filled_risk",
        description="Stata-style carry-forward of mean(100000 * risk / nr_of_words)",
    ),
}

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
    "bytes",
    "rows",
    "sha256",
]

ProgressLogger = Callable[[str], None]


def default_logger(message: str) -> None:
    print(message, flush=True)


@dataclass(frozen=True)
class RunConfig:
    dta_file: Path = DTA_FILE
    reproduced_dir: Path = REPRODUCED_DIR
    out_dir: Path = OUT_DIR
    countries: set[str] | None = None
    csv_chunk_size: int = 250_000
    dta_chunk_size: int = 500_000


@dataclass(frozen=True)
class ReproducedPanelResult:
    panel: pd.DataFrame
    observed_counts: dict[int, int]
    filled_counts: dict[int, int]
    row_counts: dict[int, int]


@dataclass(frozen=True)
class DtaPanelResult:
    panel: pd.DataFrame
    rows_by_country: dict[int, int]
    total_rows: int
    quarter_start: int
    quarter_end: int


@dataclass(slots=True)
class QuarterSums:
    dta_sum: float = 0.0
    reproduced_sum: float = 0.0
    n: int = 0


@dataclass(frozen=True)
class CorrelationResult:
    stats: dict[tuple[int, str], RunningStats]
    quarter_acc: dict[tuple[int, int, str], QuarterSums]


@dataclass(frozen=True)
class RunResult:
    gvkey_quarter_rows: pd.DataFrame
    quarter_rows: pd.DataFrame
    gvkey_quarter_path: Path
    quarter_path: Path
    manifest_path: Path
    countries: tuple[str, ...]


@dataclass
class RunningStats:
    n: int = 0
    mean_x: float = 0.0
    mean_y: float = 0.0
    m2_x: float = 0.0
    m2_y: float = 0.0
    c_xy: float = 0.0

    def add_arrays(self, x: pd.Series, y: pd.Series) -> None:
        xv_all = pd.to_numeric(x, errors="coerce").to_numpy(dtype="float64", na_value=math.nan)
        yv_all = pd.to_numeric(y, errors="coerce").to_numpy(dtype="float64", na_value=math.nan)
        valid = ~(pd.isna(xv_all) | pd.isna(yv_all))
        if not valid.any():
            return
        xv = xv_all[valid]
        yv = yv_all[valid]
        batch_n = int(len(xv))
        batch_mean_x = float(xv.mean())
        batch_mean_y = float(yv.mean())
        x_centered = xv - batch_mean_x
        y_centered = yv - batch_mean_y
        batch_m2_x = float((x_centered * x_centered).sum())
        batch_m2_y = float((y_centered * y_centered).sum())
        batch_c_xy = float((x_centered * y_centered).sum())

        if self.n == 0:
            self.n = batch_n
            self.mean_x = batch_mean_x
            self.mean_y = batch_mean_y
            self.m2_x = batch_m2_x
            self.m2_y = batch_m2_y
            self.c_xy = batch_c_xy
            return

        old_n = self.n
        total_n = old_n + batch_n
        weight = old_n * batch_n / total_n
        delta_x = batch_mean_x - self.mean_x
        delta_y = batch_mean_y - self.mean_y

        self.n = total_n
        self.mean_x += delta_x * batch_n / total_n
        self.mean_y += delta_y * batch_n / total_n
        self.m2_x += batch_m2_x + delta_x * delta_x * weight
        self.m2_y += batch_m2_y + delta_y * delta_y * weight
        self.c_xy += batch_c_xy + delta_x * delta_y * weight

    def pearson(self) -> float | None:
        if self.n < 2:
            return None
        if self.m2_x <= 0 or self.m2_y <= 0:
            return None
        return self.c_xy / math.sqrt(self.m2_x * self.m2_y)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
        help=f"Directory containing NLA country-risk *_firmlevel.csv files. Defaults to {REPRODUCED_DIR}.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help=f"Directory for generated correlation CSVs. Defaults to {OUT_DIR}.",
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


def elapsed(start: float) -> str:
    return f"{perf_counter() - start:.1f}s"


def normalize_gvkey_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.astype("Int64")


def quarter_code_from_date_like(series: pd.Series) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")
    quarter = ((dates.dt.month - 1) // 3) + 1
    return (dates.dt.year * 4 + quarter).astype("Int64")


def quarter_label(code: int) -> str:
    year = (code - 1) // 4
    quarter = code - year * 4
    return f"{year}Q{quarter}"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def country_code_from_reproduced_file(path: Path) -> str | None:
    match = re.search(r"_countryrisk-(?P<slug>.+?)-v[^_]+_[^_]+_firmlevel\.csv$", path.name)
    if not match:
        return None
    slug = match.group("slug")
    code = COUNTRY_SLUG_TO_CODE.get(slug)
    if code is None:
        return None
    return code.upper()


def discover_reproduced_files(
    reproduced_dir: Path,
    countries: set[str] | None,
    logger: ProgressLogger | None = default_logger,
) -> dict[str, Path]:
    if not reproduced_dir.exists():
        raise FileNotFoundError(f"Reproduced directory not found: {reproduced_dir}")

    selected: dict[str, Path] = {}
    skipped: list[str] = []
    for path in sorted(reproduced_dir.glob("*.csv")):
        code = country_code_from_reproduced_file(path)
        if code is None:
            skipped.append(path.name)
            continue
        if countries is not None and code not in countries:
            continue

        header = set(pd.read_csv(path, nrows=0).columns)
        required = {"gvkey", "start_time", "risk", "nr_of_words"}
        missing = required.difference(header)
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
        if code in selected:
            raise ValueError(f"Multiple reproduced firmlevel CSVs found for {code}")
        selected[code] = path

    if logger is not None and skipped:
        logger(f"Skipped {len(skipped)} non-matching files.")
    if not selected:
        raise FileNotFoundError(f"No usable country-risk firmlevel CSVs found under {reproduced_dir}")
    return selected


def load_dta_panel(
    dta_file: Path,
    country_ids: dict[str, int],
    chunk_size: int,
    logger: ProgressLogger | None = default_logger,
) -> DtaPanelResult:
    parts: list[pd.DataFrame] = []
    rows_by_country: dict[int, int] = defaultdict(int)
    min_quarter: int | None = None
    max_quarter: int | None = None
    valid_countries = set(country_ids)
    rows_read = 0
    rows_kept = 0
    start = perf_counter()

    for chunk_index, chunk in enumerate(
        pd.read_stata(
            dta_file,
            columns=["gvkey", "country_iso2", "dateQ", "CountryRisk"],
            convert_categoricals=False,
            preserve_dtypes=True,
            chunksize=chunk_size,
        ),
        start=1,
    ):
        rows_read += len(chunk)
        code = chunk["country_iso2"].astype("string").str.upper()
        chunk = chunk[code.isin(valid_countries)].copy()
        if chunk.empty:
            continue
        chunk["country_id"] = code.loc[chunk.index].map(country_ids).astype("Int64")
        chunk["gvkey_num"] = normalize_gvkey_series(chunk["gvkey"])
        chunk["quarter_code"] = quarter_code_from_date_like(chunk["dateQ"])
        chunk["dta_risk"] = pd.to_numeric(chunk["CountryRisk"], errors="coerce")
        chunk = chunk[["country_id", "gvkey_num", "quarter_code", "dta_risk"]].dropna()
        if chunk.empty:
            continue
        chunk["country_id"] = chunk["country_id"].astype("int16")
        chunk["gvkey_num"] = chunk["gvkey_num"].astype("int64")
        chunk["quarter_code"] = chunk["quarter_code"].astype(QUARTER_DTYPE)
        chunk["dta_risk"] = chunk["dta_risk"].astype("float64")

        rows_kept += len(chunk)
        for country_id, count in chunk["country_id"].value_counts().items():
            rows_by_country[int(country_id)] += int(count)

        quarters = chunk["quarter_code"]
        current_min = int(quarters.min())
        current_max = int(quarters.max())
        min_quarter = current_min if min_quarter is None else min(min_quarter, current_min)
        max_quarter = current_max if max_quarter is None else max(max_quarter, current_max)
        parts.append(chunk)

        if logger is not None and chunk_index % 10 == 0:
            logger(f"[dta] chunks={chunk_index}, read={rows_read:,}, kept={rows_kept:,} ({elapsed(start)})")

    if min_quarter is None or max_quarter is None:
        raise RuntimeError("Could not determine the DTA quarter range.")
    panel = pd.concat(parts, ignore_index=True)
    if logger is not None:
        logger(f"[dta] read={rows_read:,}, kept={rows_kept:,} ({elapsed(start)})")
    return DtaPanelResult(
        panel=panel,
        rows_by_country=rows_by_country,
        total_rows=rows_read,
        quarter_start=min_quarter,
        quarter_end=max_quarter,
    )


def stata_internal_carry_forward(
    panel: pd.DataFrame,
    *,
    quarter_start: int,
    quarter_end: int,
) -> pd.DataFrame:
    """Mirror the paper code's short-gap carry-forward semantics.

    The same backfill pattern appears in the public Zenodo replication package
    at countryrisk-main/data/code/stata/firmrisk_import.do
    (https://doi.org/10.5281/zenodo.7783429).
    """
    output_columns = ["country_id", "gvkey_num", "quarter_code", "rep_filled_risk"]
    if panel.empty:
        return pd.DataFrame(columns=output_columns)

    country_id = int(panel["country_id"].iloc[0])
    source = panel[["gvkey_num", "quarter_code", "rep_observed_risk"]].copy()
    source = source.dropna(subset=["gvkey_num", "quarter_code"])
    source = source.groupby(["gvkey_num", "quarter_code"], as_index=False)["rep_observed_risk"].mean()
    source = source[source["quarter_code"].between(quarter_start, quarter_end)]
    if source.empty:
        return pd.DataFrame(columns=output_columns)

    gvkeys = pd.Index(source["gvkey_num"].dropna().unique()).sort_values()
    quarters = pd.Index(range(quarter_start, quarter_end + 1), name="quarter_code")
    grid = pd.MultiIndex.from_product(
        [gvkeys, quarters],
        names=["gvkey_num", "quarter_code"],
    ).to_frame(index=False)
    balanced = grid.merge(source, on=["gvkey_num", "quarter_code"], how="left", validate="1:1")

    anchor_observed = balanced["rep_observed_risk"].notna()
    has_prior_observed = anchor_observed.groupby(balanced["gvkey_num"]).cummax()
    # Reverse cummax marks rows with a future observed anchor, excluding trailing gaps.
    has_future_observed = (
        anchor_observed.iloc[::-1].groupby(balanced["gvkey_num"].iloc[::-1]).cummax().iloc[::-1]
    )
    internal_gap = balanced["rep_observed_risk"].isna() & has_prior_observed & has_future_observed

    # Use original observed anchors so gaps longer than four quarters are truncated, not chained.
    prior_within_limit = pd.Series(False, index=balanced.index)
    grouped_anchor = balanced.groupby("gvkey_num")["rep_observed_risk"]
    for lag in range(1, 5):
        prior_within_limit = prior_within_limit | grouped_anchor.shift(lag).notna()

    eligible = balanced["rep_observed_risk"].isna() & internal_gap & prior_within_limit
    filled_values = balanced.groupby("gvkey_num", group_keys=False)["rep_observed_risk"].ffill()
    balanced.loc[eligible, "rep_observed_risk"] = filled_values.loc[eligible]

    keep = balanced["rep_observed_risk"].notna()
    filled = balanced.loc[keep, ["gvkey_num", "quarter_code", "rep_observed_risk"]].copy()
    filled = filled.rename(columns={"rep_observed_risk": "rep_filled_risk"})
    filled.insert(0, "country_id", country_id)
    return filled[output_columns]


def build_reproduced_panel(
    files: dict[str, Path],
    country_ids: dict[str, int],
    chunk_size: int,
    quarter_start: int,
    quarter_end: int,
    logger: ProgressLogger | None = default_logger,
) -> ReproducedPanelResult:
    panels: list[pd.DataFrame] = []
    observed_counts: dict[int, int] = {}
    filled_counts: dict[int, int] = {}
    reproduced_row_counts: dict[int, int] = {}

    for index, (code, path) in enumerate(sorted(files.items()), start=1):
        start = perf_counter()
        country_parts: list[pd.DataFrame] = []
        rows_read = 0
        start_time_parse_failures = 0

        for chunk in pd.read_csv(
            path,
            usecols=["gvkey", "start_time", "risk", "nr_of_words"],
            chunksize=chunk_size,
        ):
            rows_read += len(chunk)
            gvkey = normalize_gvkey_series(chunk["gvkey"])
            quarter = quarter_code_from_date_like(chunk["start_time"])
            start_time_parse_failures += int((chunk["start_time"].notna() & quarter.isna()).sum())
            numeric = chunk[["risk", "nr_of_words"]].apply(pd.to_numeric, errors="coerce")
            words = numeric["nr_of_words"]
            valid = gvkey.notna() & quarter.notna() & words.notna() & words.gt(0) & numeric["risk"].notna()
            if not valid.any():
                continue

            country_parts.append(
                pd.DataFrame(
                    {
                        "country_id": country_ids[code],
                        "gvkey_num": gvkey[valid].astype("int64"),
                        "quarter_code": quarter[valid].astype(QUARTER_DTYPE),
                        "rep_observed_risk": SCORE_SCALE * numeric.loc[valid, "risk"] / words.loc[valid],
                    }
                )
            )

        if not country_parts:
            if logger is not None:
                logger(
                    f"[rep {index}/{len(files)}] {code}: no usable rows, "
                    f"{start_time_parse_failures:,} bad start_time values ({elapsed(start)})"
                )
            continue

        events = pd.concat(country_parts, ignore_index=True)
        country_observed = events.groupby(
            ["country_id", "gvkey_num", "quarter_code"],
            as_index=False,
            sort=False,
        )["rep_observed_risk"].mean()
        country_observed = country_observed[
            country_observed["quarter_code"].between(quarter_start, quarter_end)
        ]
        country_filled = stata_internal_carry_forward(
            country_observed,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
        )
        country_panel = country_observed.merge(
            country_filled,
            on=["country_id", "gvkey_num", "quarter_code"],
            how="outer",
            validate="1:1",
        )
        panels.append(country_panel)
        observed_counts[country_ids[code]] = len(country_observed)
        filled_counts[country_ids[code]] = len(country_filled)
        reproduced_row_counts[country_ids[code]] = rows_read

        overlapping = country_observed.merge(
            country_filled[["country_id", "gvkey_num", "quarter_code"]],
            on=["country_id", "gvkey_num", "quarter_code"],
            how="inner",
        )
        added = len(country_filled) - len(overlapping)
        parse_note = (
            f", {start_time_parse_failures:,} bad start_time values" if start_time_parse_failures else ""
        )
        if logger is not None:
            logger(
                f"[rep {index}/{len(files)}] {code}: {rows_read:,} rows, "
                f"{len(country_observed):,} observed gvkey-quarters, "
                f"{len(country_filled):,} filled gvkey-quarters, {added:,} added{parse_note} "
                f"({elapsed(start)})"
            )

    if not panels:
        raise RuntimeError("No reproduced panels were built.")
    panel = pd.concat(panels, ignore_index=True)
    panel["country_id"] = panel["country_id"].astype("int16")
    panel["gvkey_num"] = panel["gvkey_num"].astype("int64")
    panel["quarter_code"] = panel["quarter_code"].astype(QUARTER_DTYPE)
    panel = panel.set_index(["country_id", "gvkey_num", "quarter_code"]).sort_index()
    return ReproducedPanelResult(
        panel=panel,
        observed_counts=observed_counts,
        filled_counts=filled_counts,
        row_counts=reproduced_row_counts,
    )


def add_quarter_stats(
    quarter_acc: dict[tuple[int, int, str], QuarterSums],
    merged: pd.DataFrame,
    *,
    variant: str,
    rep_col: str,
) -> None:
    metric_frame = merged[["country_id", "quarter_code", "dta_risk", rep_col]].dropna()
    if metric_frame.empty:
        return
    grouped = metric_frame.groupby(["country_id", "quarter_code"], observed=True)[["dta_risk", rep_col]].agg(
        ["sum", "count"]
    )
    for (country_id, quarter_code), row in grouped.iterrows():
        count = int(row[("dta_risk", "count")])
        if count <= 0:
            continue
        bucket = quarter_acc[(int(country_id), int(quarter_code), variant)]
        bucket.dta_sum += float(row[("dta_risk", "sum")])
        bucket.reproduced_sum += float(row[(rep_col, "sum")])
        bucket.n += count


def correlate_panels(
    dta_panel: pd.DataFrame,
    reproduced_panel: pd.DataFrame,
    chunk_size: int,
    logger: ProgressLogger | None = default_logger,
) -> CorrelationResult:
    stats: dict[tuple[int, str], RunningStats] = defaultdict(RunningStats)
    quarter_acc: dict[tuple[int, int, str], QuarterSums] = defaultdict(QuarterSums)
    matched_rows = 0
    start = perf_counter()

    for chunk_index, offset in enumerate(range(0, len(dta_panel), chunk_size), start=1):
        chunk = dta_panel.iloc[offset : offset + chunk_size]
        merged = chunk.join(
            reproduced_panel,
            on=["country_id", "gvkey_num", "quarter_code"],
            how="inner",
        )
        if merged.empty:
            continue
        matched_rows += len(merged)

        for country_id, country_frame in merged.groupby("country_id", observed=True):
            cid = int(country_id)
            for variant, config in VARIANTS.items():
                stats[(cid, variant)].add_arrays(
                    country_frame["dta_risk"],
                    country_frame[config.column],
                )

        for variant, config in VARIANTS.items():
            add_quarter_stats(quarter_acc, merged, variant=variant, rep_col=config.column)

        if logger is not None and chunk_index % 10 == 0:
            logger(
                f"[join] chunks={chunk_index}, processed={min(offset + chunk_size, len(dta_panel)):,}, "
                f"joined={matched_rows:,} ({elapsed(start)})",
            )

    if logger is not None:
        logger(f"[join] processed={len(dta_panel):,}, joined={matched_rows:,} ({elapsed(start)})")
    return CorrelationResult(
        stats=stats,
        quarter_acc=quarter_acc,
    )


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
                "reproduced_file": files[code].name,
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
                "reproduced_file": files[code].name,
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
) -> None:
    rows = [
        {
            "role": "paper_dta",
            "country_code": "",
            "path": str(dta_file),
            "bytes": dta_file.stat().st_size,
            "rows": dta_rows,
            "sha256": file_sha256(dta_file),
        }
    ]
    for code, reproduced_file in sorted(reproduced_files.items()):
        country_id = country_ids[code]
        rows.append(
            {
                "role": "reproduced_csv",
                "country_code": code,
                "path": str(reproduced_file),
                "bytes": reproduced_file.stat().st_size,
                "rows": reproduced_row_counts.get(country_id, ""),
                "sha256": file_sha256(reproduced_file),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).reindex(columns=MANIFEST_FIELDS).to_csv(path, index=False)


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


def main() -> None:
    args = parse_args()
    config = RunConfig(
        dta_file=args.dta_file,
        reproduced_dir=args.reproduced_dir,
        out_dir=args.out_dir,
        countries=parse_countries(args.countries),
        csv_chunk_size=args.csv_chunk_size,
        dta_chunk_size=args.dta_chunk_size,
    )
    run(config)


if __name__ == "__main__":
    main()
