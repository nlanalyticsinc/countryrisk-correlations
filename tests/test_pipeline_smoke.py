from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.correlation import RunConfig, run


def write_synthetic_inputs(tmp_path: Path) -> tuple[Path, Path]:
    dta_file = tmp_path / "FirmCountryQuarter_withexposure.dta"
    reproduced_dir = tmp_path / "reproduced"
    reproduced_dir.mkdir()

    pd.DataFrame(
        {
            "gvkey": [1, 1, 2, 2],
            "country_iso2": ["AR", "AR", "AR", "AR"],
            "dateQ": pd.to_datetime(["2020-01-15", "2020-04-15", "2020-01-15", "2020-04-15"]),
            "CountryRisk": [10.0, 20.0, 30.0, 50.0],
        }
    ).to_stata(dta_file, write_index=False, version=118)

    pd.DataFrame(
        {
            "gvkey": [1, 1, 2, 2, 1],
            "start_time": [
                "2020-01-20 13:30:00.000000000Z",
                "2020-04-20 13:30:00.000000000Z",
                "2020-01-20 13:30:00.000000000Z",
                "2020-04-20 13:30:00.000000000Z",
                "not-a-date",
            ],
            "risk": [0.1, 0.2, 0.3, 0.5, 0.9],
            "nr_of_words": [1000, 1000, 1000, 1000, 1000],
        }
    ).to_csv(
        reproduced_dir / "NLA_2026-07-08T000000_countryrisk-argentina-v10_fixture_firmlevel.csv",
        index=False,
    )

    return dta_file, reproduced_dir


def test_synthetic_pipeline_smoke_run(tmp_path: Path) -> None:
    dta_file, reproduced_dir = write_synthetic_inputs(tmp_path)
    out_dir = tmp_path / "correlations"
    logs: list[str] = []

    result = run(
        RunConfig(
            dta_file=dta_file,
            reproduced_dir=reproduced_dir,
            out_dir=out_dir,
            countries={"AR"},
            csv_chunk_size=2,
            dta_chunk_size=2,
        ),
        logger=logs.append,
    )

    assert result.countries == ("AR",)
    assert result.gvkey_quarter_path.exists()
    assert result.quarter_path.exists()
    assert result.manifest_path.exists()

    gvkey_rows = pd.read_csv(result.gvkey_quarter_path)
    quarter_rows = pd.read_csv(result.quarter_path)
    manifest = pd.read_csv(result.manifest_path)

    assert set(gvkey_rows["variant"]) == {"observed", "filled"}
    assert set(quarter_rows["variant"]) == {"observed", "filled"}
    assert gvkey_rows["n_pairs"].tolist() == [4, 4]
    assert quarter_rows["n_pairs"].tolist() == [2, 2]
    assert quarter_rows["matched_gvkey_quarters"].tolist() == [4, 4]
    assert gvkey_rows["pearson"].tolist() == pytest.approx([1.0, 1.0])
    assert quarter_rows["pearson"].tolist() == pytest.approx([1.0, 1.0])
    assert manifest["role"].tolist() == ["paper_dta", "reproduced_csv"]
    assert any("1 bad start_time values" in line for line in logs)
