from pathlib import Path

from countryrisk_replication.pipeline import default_reproduced_dir, latest_nla_dataset_dir


def test_latest_nla_dataset_dir_uses_most_recent_valid_calendar_date(tmp_path: Path) -> None:
    older = tmp_path / "nla_country-risk_dataset_2025-12-31"
    newest = tmp_path / "nla_country-risk_dataset_2026-06-30"
    older.mkdir()
    newest.mkdir()
    (tmp_path / "nla_country-risk_dataset_2026-13-01").mkdir()
    (tmp_path / "nla_country-risk_dataset_latest").mkdir()
    (tmp_path / "nla_country-risk_dataset_2027-01-01").write_text("not a directory")

    assert latest_nla_dataset_dir(tmp_path) == newest
    assert default_reproduced_dir(tmp_path) == newest


def test_default_reproduced_dir_falls_back_to_legacy_layout(tmp_path: Path) -> None:
    assert latest_nla_dataset_dir(tmp_path) is None
    assert default_reproduced_dir(tmp_path) == tmp_path / "reproduced_v1.0"
