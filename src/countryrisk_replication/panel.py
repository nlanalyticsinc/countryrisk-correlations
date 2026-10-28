"""Load and normalize DTA and reproduced firm-quarter panels."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd

from countryrisk_replication.discovery import CALL_ID_COLUMN, GVKEY_COLUMN
from countryrisk_replication.utils import (
    ProgressLogger,
    csv_columns,
    csv_compression,
    default_logger,
    elapsed,
)

SCORE_SCALE = 100000.0
QUARTER_DTYPE = "int32"
CROSSWALK_GVKEY_COLUMN = "gvkey_compustat"
MISSING_GVKEY_VALUES = {"", ".", "na", "n/a", "nan", "null", "none", "<na>"}


@dataclass(frozen=True)
class ReproducedPanelResult:
    panel: pd.DataFrame
    observed_counts: dict[int, int]
    filled_counts: dict[int, int]
    row_counts: dict[int, int]


@dataclass(frozen=True)
class GvkeyCrosswalk:
    path: Path
    gvkeys: pd.Series  # Nullable GVKEY by nonblank earningscallID, including unmapped calls.
    rows: int


@dataclass(frozen=True)
class DtaPanelResult:
    panel: pd.DataFrame
    rows_by_country: dict[int, int]
    total_rows: int
    quarter_start: int
    quarter_end: int


def normalize_gvkey_series(
    series: pd.Series,
    *,
    source: Path | None = None,
    column: str = GVKEY_COLUMN,
    first_data_row: int = 2,
) -> pd.Series:
    text = series.astype("string").str.strip()
    text = text.mask(text.str.lower().isin(MISSING_GVKEY_VALUES))
    values = pd.to_numeric(text.str.replace(r"\.0+$", "", regex=True), errors="coerce")
    invalid = text.notna() & (
        ~text.str.fullmatch(r"[0-9]+(?:\.0+)?").fillna(False) | values.isna() | values.ge(2**63)
    )
    if invalid.any():
        index = invalid[invalid].index[0]
        location = f"{source}: row {index + first_data_row}: " if source is not None else ""
        raise ValueError(
            f"{location}invalid {column} {series.loc[index]!r}; expected a nonnegative integer GVKEY "
            "within the signed 64-bit range"
        )
    return values.astype("Int64")


def normalize_call_id_series(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values.eq(""))


def load_gvkey_crosswalk(path: Path) -> GvkeyCrosswalk:
    """Read a measure's gvkeys.csv, which maps earningscallID to gvkey_compustat."""
    missing = {CALL_ID_COLUMN, CROSSWALK_GVKEY_COLUMN}.difference(csv_columns(path))
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
    frame = pd.read_csv(
        path,
        usecols=[CALL_ID_COLUMN, CROSSWALK_GVKEY_COLUMN],
        dtype=str,
        keep_default_na=False,
        compression=csv_compression(path),
    )
    rows = len(frame)
    frame[CALL_ID_COLUMN] = normalize_call_id_series(frame[CALL_ID_COLUMN])
    frame = frame.dropna(subset=[CALL_ID_COLUMN])
    pairs = pd.DataFrame(
        {
            "call_id": frame[CALL_ID_COLUMN],
            "gvkey_num": normalize_gvkey_series(
                frame[CROSSWALK_GVKEY_COLUMN], source=path, column=CROSSWALK_GVKEY_COLUMN
            ),
        }
    )
    known = pairs.dropna(subset=["gvkey_num"]).drop_duplicates()
    conflicting = known.loc[known["call_id"].duplicated(), "call_id"]
    if not conflicting.empty:
        examples = ", ".join(conflicting.unique()[:3])
        raise ValueError(f"{path} maps earningscallID values to more than one gvkey: {examples}")
    # Retain membership for calls without a GVKEY; a nonmissing duplicate takes precedence.
    gvkeys = known.set_index("call_id")["gvkey_num"].reindex(pairs["call_id"].drop_duplicates())
    return GvkeyCrosswalk(path=path, gvkeys=gvkeys, rows=rows)


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
        chunk["gvkey_num"] = normalize_gvkey_series(chunk["gvkey"], source=dta_file, first_data_row=1)
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
    keys = ["country_id", "gvkey_num", "quarter_code"]
    duplicates = panel.duplicated(keys, keep=False)
    if duplicates.any():
        examples = panel.loc[duplicates, keys].drop_duplicates().head(3).to_dict("records")
        raise ValueError(f"{dta_file} contains duplicate original firm-country-quarter rows: {examples}")
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
    gvkey_crosswalk: GvkeyCrosswalk | None = None,
) -> ReproducedPanelResult:
    """Read each country's firm-level file into gvkey-quarter means.

    Files without a gvkey column take it from ``gvkey_crosswalk`` by earningscallID.
    """
    panels: list[pd.DataFrame] = []
    observed_counts: dict[int, int] = {}
    filled_counts: dict[int, int] = {}
    reproduced_row_counts: dict[int, int] = {}

    for index, (code, path) in enumerate(sorted(files.items()), start=1):
        start = perf_counter()
        country_parts: list[pd.DataFrame] = []
        rows_read = 0
        start_time_parse_failures = 0
        invalid_score_rows = 0
        has_gvkey = GVKEY_COLUMN in csv_columns(path)
        if not has_gvkey and gvkey_crosswalk is None:
            raise ValueError(f"{path} has no {GVKEY_COLUMN} column and no GVKEY crosswalk was given.")
        crosswalk = None if has_gvkey else gvkey_crosswalk
        key_column = GVKEY_COLUMN if crosswalk is None else CALL_ID_COLUMN
        rows_without_gvkey = 0
        rows_with_call_id = 0
        crosswalk_matches = 0

        for chunk in pd.read_csv(
            path,
            usecols=[key_column, "start_time", "risk", "nr_of_words"],
            dtype={key_column: str},
            keep_default_na=False,
            # Infer each chunk's dtypes in one pass. A blank score leaves one low-memory block of
            # text among numeric ones, and pandas 3 then fails while building its mixed-type
            # warning under usecols. pd.to_numeric below turns the blank into a skipped row.
            low_memory=False,
            chunksize=chunk_size,
            compression=csv_compression(path),
        ):
            rows_read += len(chunk)
            if crosswalk is None:
                gvkey = normalize_gvkey_series(chunk[GVKEY_COLUMN], source=path)
            else:
                call_ids = normalize_call_id_series(chunk[CALL_ID_COLUMN])
                rows_with_call_id += int(call_ids.notna().sum())
                crosswalk_matches += int(call_ids.isin(crosswalk.gvkeys.index).sum())
                gvkey = call_ids.map(crosswalk.gvkeys).astype("Int64")
                rows_without_gvkey += int(gvkey.isna().sum())
            quarter = quarter_code_from_date_like(chunk["start_time"])
            start_time_parse_failures += int((chunk["start_time"].notna() & quarter.isna()).sum())
            numeric = chunk[["risk", "nr_of_words"]].apply(pd.to_numeric, errors="coerce")
            words = numeric["nr_of_words"]
            usable_score = numeric.abs().lt(float("inf")).all(axis=1) & words.gt(0)
            invalid_score_rows += int((~usable_score).sum())
            valid = (
                gvkey.notna() & quarter.notna() & quarter.between(quarter_start, quarter_end) & usable_score
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

        reproduced_row_counts[country_ids[code]] = rows_read
        if crosswalk is not None and rows_with_call_id and not crosswalk_matches:
            raise ValueError(
                f"No earningscallID in {path} is present in {crosswalk.path}; "
                "use the crosswalk that came with the firm-level files."
            )
        gvkey_note = (
            f", {rows_without_gvkey:,} calls without a crosswalk GVKEY" if crosswalk is not None else ""
        )
        score_note = f", {invalid_score_rows:,} calls with unusable scores"

        if not country_parts:
            if logger is not None:
                logger(
                    f"[rep {index}/{len(files)}] {code}: no usable rows, "
                    f"{start_time_parse_failures:,} bad start_time values{gvkey_note}{score_note} "
                    f"({elapsed(start)})"
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
                f"{len(country_filled):,} filled gvkey-quarters, {added:,} added"
                f"{parse_note}{gvkey_note}{score_note} "
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
