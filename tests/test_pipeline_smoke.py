from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.pipeline import RunConfig, run


def write_synthetic_inputs(tmp_path: Path, layout: str) -> tuple[Path, Path, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dta_file = tmp_path / "FirmCountryQuarter_withexposure.dta"
    if layout == "legacy_flat":
        reproduced_dir = tmp_path / "reproduced"
        reproduced_file = (
            reproduced_dir / "NLA_2026-07-08T000000_countryrisk-argentina-v10_fixture_firmlevel.csv"
        )
        reproduced_label = reproduced_file.name
    elif layout == "dataset_bundle":
        reproduced_dir = tmp_path / "nla_country-risk_dataset_2026-06-30"
        reproduced_file = (
            reproduced_dir / "series" / "01-countryrisk-argentina-v11-70ca2a2b" / "firmlevel.csv.gz"
        )
        reproduced_label = "01-countryrisk-argentina-v11-70ca2a2b/firmlevel.csv.gz"
    else:
        raise ValueError(f"Unknown layout: {layout}")
    reproduced_file.parent.mkdir(parents=True)

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
    ).to_csv(reproduced_file, index=False, compression="infer")

    return dta_file, reproduced_dir, reproduced_label, layout


@pytest.mark.parametrize("layout", ["legacy_flat", "dataset_bundle"])
def test_synthetic_pipeline_smoke_run(tmp_path: Path, layout: str) -> None:
    dta_file, reproduced_dir, reproduced_label, source_layout = write_synthetic_inputs(tmp_path, layout)
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
    assert manifest["source_layout"].tolist() == ["stata", source_layout]
    assert gvkey_rows["reproduced_file"].unique().tolist() == [reproduced_label]
    assert quarter_rows["reproduced_file"].unique().tolist() == [reproduced_label]
    if layout == "dataset_bundle":
        assert manifest.loc[1, "dataset_date"] == "2026-06-30"
        assert manifest.loc[1, "series_version"] == 11
        assert manifest.loc[1, "series_id"] == "70ca2a2b"
        assert manifest.loc[1, "compression"] == "gzip"
    assert any("1 bad start_time values" in line for line in logs)


def test_legacy_and_bundle_layouts_produce_identical_statistics(tmp_path: Path) -> None:
    results = []
    for layout in ("legacy_flat", "dataset_bundle"):
        dta_file, reproduced_dir, _, _ = write_synthetic_inputs(tmp_path / layout, layout)
        result = run(
            RunConfig(
                dta_file=dta_file,
                reproduced_dir=reproduced_dir,
                out_dir=tmp_path / f"correlations-{layout}",
                countries={"AR"},
                csv_chunk_size=2,
                dta_chunk_size=2,
            ),
            logger=None,
        )
        results.append(
            (
                result.gvkey_quarter_rows.drop(columns="reproduced_file"),
                result.quarter_rows.drop(columns="reproduced_file"),
            )
        )

    pd.testing.assert_frame_equal(results[0][0], results[1][0])
    pd.testing.assert_frame_equal(results[0][1], results[1][1])
