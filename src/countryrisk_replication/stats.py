"""Streaming correlation statistics for matched panels."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

import pandas as pd

from countryrisk_replication.utils import ProgressLogger, default_logger, elapsed


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


@dataclass(slots=True)
class QuarterSums:
    dta_sum: float = 0.0
    reproduced_sum: float = 0.0
    n: int = 0


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
        valid = (abs(xv_all) < math.inf) & (abs(yv_all) < math.inf)
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


@dataclass(frozen=True)
class CorrelationResult:
    stats: dict[tuple[int, str], RunningStats]
    quarter_acc: dict[tuple[int, int, str], QuarterSums]


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
