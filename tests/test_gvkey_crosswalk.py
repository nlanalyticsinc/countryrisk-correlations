from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.panel import build_reproduced_panel, load_gvkey_crosswalk


def write_crosswalk(
    path: Path, call_ids: list[str], gvkeys: list[str | None], compression: str = "infer"
) -> None:
    pd.DataFrame(
        {
            "earningscallID": call_ids,
            "gvkey_compustat": gvkeys,
            "sic_compustat": ["7372"] * len(call_ids),
            "sic_compustat_description": ["Prepackaged Software"] * len(call_ids),
        }
    ).to_csv(path, index=False, compression=compression)


def test_load_gvkey_crosswalk_normalizes_gvkeys_and_retains_unmapped_calls(tmp_path: Path) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(
        path,
        ["call-1", "call-2", "call-3", "call-3", " call-4 ", "call-5"],
        ["001004", "1004.0", "012345", "012345", "160364", None],
    )

    crosswalk = load_gvkey_crosswalk(path)

    assert crosswalk.gvkeys.dropna().to_dict() == {
        "call-1": 1004,
        "call-2": 1004,
        "call-3": 12345,
        "call-4": 160364,
    }
    assert pd.isna(crosswalk.gvkeys["call-5"])
    assert crosswalk.rows == 6
    assert crosswalk.path == path


def test_load_gvkey_crosswalk_reads_gzip_saved_as_csv(tmp_path: Path) -> None:
    path = tmp_path / "NLA_2026-10-22T000000_countryrisk-argentina-v11_70ca2a2b_gvkeys.csv"
    write_crosswalk(path, ["call-1"], ["001004"], compression="gzip")

    assert path.read_bytes()[:2] == b"\x1f\x8b"
    assert load_gvkey_crosswalk(path).gvkeys.to_dict() == {"call-1": 1004}


def test_load_gvkey_crosswalk_rejects_conflicting_gvkeys(tmp_path: Path) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(path, ["call-1", "call-1"], ["001004", "001005"])

    with pytest.raises(ValueError, match="more than one gvkey: call-1"):
        load_gvkey_crosswalk(path)


def test_load_gvkey_crosswalk_requires_its_columns(tmp_path: Path) -> None:
    path = tmp_path / "gvkeys.csv"
    pd.DataFrame({"earningscallID": ["call-1"], "gvkey": ["001004"]}).to_csv(path, index=False)

    with pytest.raises(ValueError, match="missing required columns: gvkey_compustat"):
        load_gvkey_crosswalk(path)


@pytest.mark.parametrize("value", [None, "", "   ", "NaN", "NULL", "N/A", "NA", "None", "<NA>", "."])
def test_crosswalk_retains_calls_with_missing_gvkeys(tmp_path: Path, value: str | None) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(path, ["call-1"], [value])

    crosswalk = load_gvkey_crosswalk(path)

    assert crosswalk.gvkeys.index.tolist() == ["call-1"]
    assert pd.isna(crosswalk.gvkeys["call-1"])


@pytest.mark.parametrize(
    "value", ["broken", "1004.5", "-1", "inf", "9223372036854775808", "1.0000000000000001"]
)
def test_crosswalk_rejects_invalid_gvkeys_with_file_and_row(tmp_path: Path, value: str) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(path, ["call-1", "call-2"], ["001004", value])

    with pytest.raises(ValueError, match="row 3: invalid gvkey_compustat") as error:
        load_gvkey_crosswalk(path)

    assert str(path) in str(error.value)
    assert repr(value) in str(error.value)


@pytest.mark.parametrize("gvkeys", [[None, "1004", "001004"], ["1004", "001004", None]])
def test_missing_duplicate_does_not_replace_known_gvkey(tmp_path: Path, gvkeys: list[str | None]) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(path, ["call-1"] * 3, gvkeys)

    assert load_gvkey_crosswalk(path).gvkeys.to_dict() == {"call-1": 1004}


def test_blank_call_ids_cannot_contaminate_a_firm_quarter(tmp_path: Path) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(path, ["   ", "", "call-1"], ["001004", "001005", "001004"])
    crosswalk = load_gvkey_crosswalk(path)
    calls = tmp_path / "firmlevel.csv"
    calls.write_text(
        "earningscallID,start_time,risk,nr_of_words\n"
        "   ,2020-01-01,100,1000\n"
        ",2020-01-01,100,1000\n"
        " call-1 ,2020-01-01,1,1000\n"
    )

    result = build_reproduced_panel(
        {"AR": calls}, {"AR": 1}, 1, 8081, 8081, logger=None, gvkey_crosswalk=crosswalk
    )

    assert crosswalk.gvkeys.to_dict() == {"call-1": 1004}
    assert result.panel["rep_observed_risk"].tolist() == [100.0]


@pytest.mark.parametrize("call_id", ["call-ar", "   "])
def test_country_without_usable_gvkeys_does_not_abort_other_countries(tmp_path: Path, call_id: str) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(path, ["call-ar", "call-br"], [None, "001004"])
    files = {}
    for country, identifier in [("AR", call_id), ("BR", "call-br")]:
        calls = tmp_path / f"{country}.csv"
        calls.write_text(f"earningscallID,start_time,risk,nr_of_words\n{identifier},2020-01-01,1,1000\n")
        files[country] = calls
    logs: list[str] = []

    result = build_reproduced_panel(
        files,
        {"AR": 1, "BR": 2},
        1,
        8081,
        8081,
        logger=logs.append,
        gvkey_crosswalk=load_gvkey_crosswalk(path),
    )

    assert result.panel.index.tolist() == [(2, 1004, 8081)]
    assert result.row_counts == {1: 1, 2: 1}
    assert any("AR: no usable rows" in line for line in logs)
