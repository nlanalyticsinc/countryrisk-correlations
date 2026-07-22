from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.discovery import (
    country_code_from_reproduced_file,
    discover_reproduced_files,
    reproduced_file_label,
    reproduced_file_metadata,
)


def write_firmlevel(path: Path, *, include_words: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, list[object]] = {
        "gvkey": [1],
        "start_time": ["2020-01-20 13:30:00.000000000Z"],
        "risk": [0.1],
    }
    if include_words:
        data["nr_of_words"] = [1000]
    pd.DataFrame(data).to_csv(path, index=False, compression="infer")


def test_country_code_from_reproduced_file_parses_known_slug() -> None:
    path = Path("NLA_2026-07-08T113126_countryrisk-argentina-v10_70ca2a2b_firmlevel.csv")

    assert country_code_from_reproduced_file(path) == "AR"


def test_country_code_from_packaged_file_parses_parent_series_directory() -> None:
    path = Path(
        "nla_country-risk_dataset_2026-06-30/series/"
        "01-countryrisk-argentina-v11-70ca2a2b/firmlevel.csv.gz"
    )

    assert country_code_from_reproduced_file(path) == "AR"
    assert reproduced_file_label(path) == (
        "01-countryrisk-argentina-v11-70ca2a2b/firmlevel.csv.gz"
    )
    metadata = reproduced_file_metadata(path)
    assert metadata is not None
    assert metadata.source_layout == "dataset_bundle"
    assert metadata.dataset_date == "2026-06-30"
    assert metadata.series_version == "11"
    assert metadata.series_id == "70ca2a2b"
    assert metadata.compression == "gzip"


def test_country_code_from_reproduced_file_rejects_malformed_name() -> None:
    path = Path("countryrisk-argentina.csv")

    assert country_code_from_reproduced_file(path) is None


def test_country_code_from_reproduced_file_rejects_unknown_slug() -> None:
    path = Path("NLA_2026-07-08T113126_countryrisk-atlantis-v10_70ca2a2b_firmlevel.csv")

    assert country_code_from_reproduced_file(path) is None


@pytest.mark.parametrize("root_kind", ["dataset", "series", "single-series"])
def test_discover_packaged_firmlevel_and_ignore_timeseries(tmp_path: Path, root_kind: str) -> None:
    dataset_root = tmp_path / "nla_country-risk_dataset_2026-06-30"
    series_root = dataset_root / "series"
    country_root = series_root / "01-countryrisk-argentina-v11-70ca2a2b"
    firmlevel = country_root / "firmlevel.csv.gz"
    write_firmlevel(firmlevel)
    pd.DataFrame({"date": ["2020-03-31"], "risk": [1.0]}).to_csv(
        country_root / "timeseries.csv.gz",
        index=False,
        compression="gzip",
    )
    roots = {
        "dataset": dataset_root,
        "series": series_root,
        "single-series": country_root,
    }

    assert discover_reproduced_files(roots[root_kind], None, logger=None) == {"AR": firmlevel}


def test_discovery_rejects_duplicate_country_across_layouts(tmp_path: Path) -> None:
    write_firmlevel(
        tmp_path / "NLA_2026-07-08T000000_countryrisk-argentina-v10_fixture_firmlevel.csv"
    )
    write_firmlevel(
        tmp_path
        / "series"
        / "01-countryrisk-argentina-v11-70ca2a2b"
        / "firmlevel.csv.gz"
    )

    with pytest.raises(ValueError, match="Multiple reproduced firmlevel CSVs found for AR"):
        discover_reproduced_files(tmp_path, None, logger=None)


def test_discovery_rejects_missing_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "NLA_2026-07-08T000000_countryrisk-argentina-v10_fixture_firmlevel.csv"
    write_firmlevel(path, include_words=False)

    with pytest.raises(ValueError, match="missing required columns: nr_of_words"):
        discover_reproduced_files(tmp_path, None, logger=None)


def test_discovery_reports_requested_countries_not_found(tmp_path: Path) -> None:
    write_firmlevel(
        tmp_path / "NLA_2026-07-08T000000_countryrisk-argentina-v10_fixture_firmlevel.csv"
    )

    with pytest.raises(FileNotFoundError, match="No usable country-risk firmlevel CSV found for: CL"):
        discover_reproduced_files(tmp_path, {"AR", "CL"}, logger=None)
