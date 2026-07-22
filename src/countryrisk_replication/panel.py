"""Load and normalize DTA and reproduced firm-quarter panels."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd

from countryrisk_replication.utils import ProgressLogger, default_logger, elapsed

SCORE_SCALE = 100000.0
QUARTER_DTYPE = "int32"


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


def normalize_gvkey_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.astype("Int64")


def quarter_code_from_date_like(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        quarter = ((series.dt.month - 1) // 3) + 1
        return (series.dt.year * 4 + quarter).astype("Int64")

    values = series.astype("string").str.strip()
    parts = values.str.extract(
        r"^(?:(?P<year_sep>\d{4,})[-/](?P<month_sep>\d{1,2})(?:[-/]\d{1,2})?|"
        r"(?P<year_compact>\d{4})(?P<month_compact>\d{2})(?:\d{2})?)(?:[ T].*)?$"
    )
    year = pd.to_numeric(parts["year_sep"].fillna(parts["year_compact"]), errors="coerce")
    month = pd.to_numeric(parts["month_sep"].fillna(parts["month_compact"]), errors="coerce")
    valid = year.notna() & month.between(1, 12)

    quarter = ((month[valid].astype("int64") - 1) // 3) + 1
    code = year[valid].astype("int64") * 4 + quarter
    result = pd.Series(pd.NA, index=series.index, dtype="Int64")
    result.loc[valid] = code
    return result


def quarter_label(code: int) -> str:
    year = (code - 1) // 4
    quarter = code - year * 4
    return f"{year}Q{quarter}"


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
            valid = (
                gvkey.notna()
                & quarter.notna()
                & quarter.between(quarter_start, quarter_end)
                & words.notna()
                & words.gt(0)
                & numeric["risk"].notna()
            )
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
