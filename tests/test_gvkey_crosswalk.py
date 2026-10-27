from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.panel import load_gvkey_crosswalk


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


def test_load_gvkey_crosswalk_normalizes_gvkeys_and_skips_blanks(tmp_path: Path) -> None:
    path = tmp_path / "gvkeys.csv"
    write_crosswalk(
        path,
        ["call-1", "call-2", "call-3", "call-3", " call-4 ", "call-5"],
        ["001004", "1004.0", "012345", "012345", "160364", None],
    )

    crosswalk = load_gvkey_crosswalk(path)

    assert crosswalk.gvkeys.to_dict() == {"call-1": 1004, "call-2": 1004, "call-3": 12345, "call-4": 160364}
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
