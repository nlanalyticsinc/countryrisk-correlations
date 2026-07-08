"""Discover and validate reproduced country-risk CSV files."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from countryrisk_replication.utils import ProgressLogger, default_logger

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
