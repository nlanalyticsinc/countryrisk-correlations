"""Discover and validate reproduced country-risk CSV files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from countryrisk_replication.utils import ProgressLogger, csv_columns, default_logger

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

REQUIRED_FIRMLEVEL_COLUMNS = {"start_time", "risk", "nr_of_words"}
# Firm-level files carry gvkey, or earningscallID for the join to the measure's
# gvkeys.csv crosswalk (gvkey_compustat).
GVKEY_COLUMN = "gvkey"
CALL_ID_COLUMN = "earningscallID"
# The dataset ZIP holds one gvkeys.csv(.gz) at its root, next to series/;
# a series page offers the same crosswalk as NLA_*_gvkeys.csv.
GVKEY_CROSSWALK_PATTERNS = ("gvkeys.csv", "gvkeys.csv.gz", "*_gvkeys.csv", "*_gvkeys.csv.gz")
LEGACY_FILE_PATTERN = re.compile(
    r"_countryrisk-(?P<slug>.+?)-v(?P<version>[^_]+)_"
    r"(?P<series_id>[^_]+)_firmlevel\.csv(?:\.gz)?$"
)
BUNDLE_SERIES_PATTERN = re.compile(r"^\d+-countryrisk-(?P<slug>.+)-v(?P<version>[^-]+)-(?P<series_id>[^-]+)$")
DATASET_DIRECTORY_PATTERN = re.compile(r"^nla_country-risk_dataset_(?P<date>\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True)
class ReproducedFileMetadata:
    country_code: str
    country_slug: str
    source_layout: str
    series_version: str
    series_id: str
    dataset_date: str


def dataset_date(path: Path) -> str:
    for directory in path.parents:
        match = DATASET_DIRECTORY_PATTERN.fullmatch(directory.name)
        if match:
            return match.group("date")
    return ""


def reproduced_file_metadata(path: Path) -> ReproducedFileMetadata | None:
    legacy_match = LEGACY_FILE_PATTERN.search(path.name)
    if legacy_match:
        match = legacy_match
        source_layout = "legacy_flat"
    elif path.name in {"firmlevel.csv", "firmlevel.csv.gz"}:
        bundle_match = BUNDLE_SERIES_PATTERN.fullmatch(path.parent.name)
        if bundle_match is None:
            return None
        match = bundle_match
        source_layout = "dataset_bundle"
    else:
        return None

    slug = match.group("slug")
    code = COUNTRY_SLUG_TO_CODE.get(slug)
    if code is None:
        return None
    return ReproducedFileMetadata(
        country_code=code.upper(),
        country_slug=slug,
        source_layout=source_layout,
        series_version=match.group("version"),
        series_id=match.group("series_id"),
        dataset_date=dataset_date(path),
    )


def country_code_from_reproduced_file(path: Path) -> str | None:
    metadata = reproduced_file_metadata(path)
    return metadata.country_code if metadata is not None else None


def reproduced_file_label(path: Path) -> str:
    metadata = reproduced_file_metadata(path)
    if metadata is not None and metadata.source_layout == "dataset_bundle":
        return f"{path.parent.name}/{path.name}"
    return path.name


def _candidate_firmlevel_files(reproduced_dir: Path) -> list[Path]:
    patterns = (
        "*_firmlevel.csv",
        "*_firmlevel.csv.gz",
        "firmlevel.csv",
        "firmlevel.csv.gz",
        "*/firmlevel.csv",
        "*/firmlevel.csv.gz",
        "series/*/firmlevel.csv",
        "series/*/firmlevel.csv.gz",
    )
    return sorted({path for pattern in patterns for path in reproduced_dir.glob(pattern)})


def discover_reproduced_files(
    reproduced_dir: Path,
    countries: set[str] | None,
    logger: ProgressLogger | None = default_logger,
) -> dict[str, Path]:
    if not reproduced_dir.exists():
        raise FileNotFoundError(f"Reproduced directory not found: {reproduced_dir}")

    selected: dict[str, Path] = {}
    skipped: list[str] = []
    for path in _candidate_firmlevel_files(reproduced_dir):
        code = country_code_from_reproduced_file(path)
        if code is None:
            skipped.append(path.name)
            continue
        if countries is not None and code not in countries:
            continue

        header = csv_columns(path)
        missing = REQUIRED_FIRMLEVEL_COLUMNS.difference(header)
        if GVKEY_COLUMN not in header and CALL_ID_COLUMN not in header:
            missing.add(f"{GVKEY_COLUMN} or {CALL_ID_COLUMN}")
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
        if code in selected:
            raise ValueError(f"Multiple reproduced firmlevel CSVs found for {code}")
        selected[code] = path

    if logger is not None and skipped:
        logger(f"Skipped {len(skipped)} non-matching files.")
    if countries is not None:
        missing_countries = countries.difference(selected)
        if missing_countries:
            missing_text = ", ".join(sorted(missing_countries))
            raise FileNotFoundError(f"No usable country-risk firmlevel CSV found for: {missing_text}")
    if not selected:
        raise FileNotFoundError(f"No usable country-risk firmlevel CSVs found under {reproduced_dir}")
    return selected


def discover_gvkey_crosswalk(reproduced_dir: Path) -> Path:
    """Find the measure's GVKEY crosswalk in or above the reproduced directory."""
    search_dirs = [reproduced_dir]
    if reproduced_dir.name == "series":
        search_dirs.append(reproduced_dir.parent)
    elif reproduced_dir.parent.name == "series":
        search_dirs.append(reproduced_dir.parent.parent)
    candidates = sorted(
        {
            path
            for directory in search_dirs
            for pattern in GVKEY_CROSSWALK_PATTERNS
            for path in directory.glob(pattern)
        }
    )
    if not candidates:
        raise FileNotFoundError(
            f"No GVKEY crosswalk found for {reproduced_dir}. Firm-level files without a gvkey column need "
            "the measure's gvkeys.csv: it is at the root of the dataset ZIP, and a series page offers it "
            "as NLA_*_gvkeys.csv. Put it next to the firm-level files or pass --gvkeys-file."
        )
    if len(candidates) > 1:
        names = ", ".join(str(path) for path in candidates)
        raise ValueError(f"Multiple GVKEY crosswalks found: {names}. Keep one or pass --gvkeys-file.")
    return candidates[0]
