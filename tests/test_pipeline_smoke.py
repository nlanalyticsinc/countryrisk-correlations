from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.pipeline import RunConfig, run

CALLS = pd.DataFrame(
    {
        "earningscallID": ["call-1", "call-2", "call-3", "call-4", "call-5"],
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
)
# Firm-level files downloaded since October 2026 have no gvkey column; the measure's
# gvkeys.csv crosswalk maps earningscallID to a zero-padded gvkey_compustat.
CROSSWALK = pd.DataFrame(
    {
        "earningscallID": CALLS["earningscallID"],
        "gvkey_compustat": ["000001", "000001", "000002", "000002", "000001"],
        "sic_compustat": ["7372"] * 5,
        "sic_compustat_description": ["Prepackaged Software"] * 5,
    }
)
LAYOUTS = ["legacy_flat", "dataset_bundle", "dataset_bundle_crosswalk", "series_page_gzip"]
CROSSWALK_LAYOUTS = {"dataset_bundle_crosswalk", "series_page_gzip"}
SERIES_DIR = "01-countryrisk-argentina-v11-70ca2a2b"
SERIES_PAGE_PREFIX = "NLA_2026-10-22T000000_countryrisk-argentina-v11_70ca2a2b"


def write_synthetic_inputs(
    tmp_path: Path, layout: str, crosswalk: pd.DataFrame = CROSSWALK
) -> tuple[Path, Path, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dta_file = tmp_path / "FirmCountryQuarter_withexposure.dta"
    crosswalk_file = None
    compression = "infer"
    if layout == "legacy_flat":
        reproduced_dir = tmp_path / "reproduced"
        reproduced_file = (
            reproduced_dir / "NLA_2026-07-08T000000_countryrisk-argentina-v10_fixture_firmlevel.csv"
        )
        reproduced_label = reproduced_file.name
    elif layout == "dataset_bundle":
        reproduced_dir = tmp_path / "nla_country-risk_dataset_2026-06-30"
        reproduced_file = reproduced_dir / "series" / SERIES_DIR / "firmlevel.csv.gz"
        reproduced_label = f"{SERIES_DIR}/firmlevel.csv.gz"
    elif layout == "dataset_bundle_crosswalk":
        # The dataset ZIP since 22 October 2026, with gvkeys.csv.gz at its root.
        reproduced_dir = tmp_path / "nla_country-risk_dataset_2026-10-22"
        reproduced_file = reproduced_dir / "series" / SERIES_DIR / "firmlevel.csv.gz"
        reproduced_label = f"{SERIES_DIR}/firmlevel.csv.gz"
        crosswalk_file = reproduced_dir / "gvkeys.csv.gz"
    elif layout == "series_page_gzip":
        # Series-page downloads can hold gzip bytes under a plain .csv name.
        reproduced_dir = tmp_path / "reproduced"
        reproduced_file = reproduced_dir / f"{SERIES_PAGE_PREFIX}_firmlevel.csv"
        reproduced_label = reproduced_file.name
        crosswalk_file = reproduced_dir / f"{SERIES_PAGE_PREFIX}_gvkeys.csv"
        compression = "gzip"
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

    if crosswalk_file is None:
        panel = CALLS.drop(columns="earningscallID")
    else:
        panel = CALLS.drop(columns="gvkey")
        crosswalk.to_csv(crosswalk_file, index=False, compression=compression)
    panel.to_csv(reproduced_file, index=False, compression=compression)

    source_layout = "dataset_bundle" if layout.startswith("dataset_bundle") else "legacy_flat"
    return dta_file, reproduced_dir, reproduced_label, source_layout


def synthetic_config(
    dta_file: Path, reproduced_dir: Path, out_dir: Path, gvkeys_file: Path | None = None
) -> RunConfig:
    return RunConfig(
        dta_file=dta_file,
        reproduced_dir=reproduced_dir,
        out_dir=out_dir,
        countries={"AR"},
        csv_chunk_size=2,
        dta_chunk_size=2,
        gvkeys_file=gvkeys_file,
    )


@pytest.mark.parametrize("layout", LAYOUTS)
def test_synthetic_pipeline_smoke_run(tmp_path: Path, layout: str) -> None:
    dta_file, reproduced_dir, reproduced_label, source_layout = write_synthetic_inputs(tmp_path, layout)
    logs: list[str] = []

    result = run(synthetic_config(dta_file, reproduced_dir, tmp_path / "correlations"), logger=logs.append)

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
    roles = ["paper_dta", "reproduced_csv"]
    if layout in CROSSWALK_LAYOUTS:
        roles.append("gvkey_crosswalk")
    assert manifest["role"].tolist() == roles
    assert manifest["source_layout"].tolist()[:2] == ["stata", source_layout]
    assert gvkey_rows["reproduced_file"].unique().tolist() == [reproduced_label]
    assert quarter_rows["reproduced_file"].unique().tolist() == [reproduced_label]
    if source_layout == "dataset_bundle":
        assert manifest.loc[1, "dataset_date"] == reproduced_dir.name.removeprefix(
            "nla_country-risk_dataset_"
        )
        assert manifest.loc[1, "series_version"] == 11
        assert manifest.loc[1, "series_id"] == "70ca2a2b"
    assert manifest.loc[1, "compression"] == ("none" if layout == "legacy_flat" else "gzip")
    if layout in CROSSWALK_LAYOUTS:
        assert manifest.loc[2, "compression"] == "gzip"
        assert manifest.loc[2, "rows"] == len(CROSSWALK)
        assert any("0 calls without a crosswalk GVKEY" in line for line in logs)
    assert any("1 bad start_time values" in line for line in logs)


def test_all_layouts_produce_identical_statistics(tmp_path: Path) -> None:
    results = []
    for layout in LAYOUTS:
        dta_file, reproduced_dir, _, _ = write_synthetic_inputs(tmp_path / layout, layout)
        result = run(
            synthetic_config(dta_file, reproduced_dir, tmp_path / f"correlations-{layout}"),
            logger=None,
        )
        results.append(
            (
                result.gvkey_quarter_rows.drop(columns="reproduced_file"),
                result.quarter_rows.drop(columns="reproduced_file"),
            )
        )

    for gvkey_rows, quarter_rows in results[1:]:
        pd.testing.assert_frame_equal(results[0][0], gvkey_rows)
        pd.testing.assert_frame_equal(results[0][1], quarter_rows)


def test_calls_missing_from_crosswalk_drop_out(tmp_path: Path) -> None:
    crosswalk = CROSSWALK[CROSSWALK["gvkey_compustat"] != "000002"]
    dta_file, reproduced_dir, _, _ = write_synthetic_inputs(tmp_path, "dataset_bundle_crosswalk", crosswalk)
    logs: list[str] = []

    result = run(synthetic_config(dta_file, reproduced_dir, tmp_path / "correlations"), logger=logs.append)

    assert result.gvkey_quarter_rows["n_pairs"].tolist() == [2, 2]
    assert any("2 calls without a crosswalk GVKEY" in line for line in logs)


def test_crosswalk_from_another_download_is_rejected(tmp_path: Path) -> None:
    crosswalk = CROSSWALK.assign(earningscallID="other-" + CROSSWALK["earningscallID"])
    dta_file, reproduced_dir, _, _ = write_synthetic_inputs(tmp_path, "dataset_bundle_crosswalk", crosswalk)

    with pytest.raises(ValueError, match="No earningscallID in .* has a GVKEY"):
        run(synthetic_config(dta_file, reproduced_dir, tmp_path / "correlations"), logger=None)


def test_missing_crosswalk_fails_before_reading_the_dta(tmp_path: Path) -> None:
    dta_file, reproduced_dir, _, _ = write_synthetic_inputs(tmp_path, "dataset_bundle_crosswalk")
    (reproduced_dir / "gvkeys.csv.gz").unlink()
    dta_file.unlink()

    with pytest.raises(FileNotFoundError, match="No GVKEY crosswalk found"):
        run(synthetic_config(dta_file, reproduced_dir, tmp_path / "correlations"), logger=None)


def test_gvkeys_file_overrides_discovery(tmp_path: Path) -> None:
    dta_file, reproduced_dir, _, _ = write_synthetic_inputs(tmp_path, "dataset_bundle_crosswalk")
    gvkeys_file = tmp_path / "elsewhere" / "gvkeys.csv.gz"
    gvkeys_file.parent.mkdir()
    (reproduced_dir / "gvkeys.csv.gz").rename(gvkeys_file)

    result = run(
        synthetic_config(dta_file, reproduced_dir, tmp_path / "correlations", gvkeys_file=gvkeys_file),
        logger=None,
    )

    assert result.gvkey_quarter_rows["n_pairs"].tolist() == [4, 4]
