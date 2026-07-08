from pathlib import Path

from countryrisk_replication.correlation import country_code_from_reproduced_file


def test_country_code_from_reproduced_file_parses_known_slug() -> None:
    path = Path("NLA_2026-07-08T113126_countryrisk-argentina-v10_70ca2a2b_firmlevel.csv")

    assert country_code_from_reproduced_file(path) == "AR"


def test_country_code_from_reproduced_file_rejects_malformed_name() -> None:
    path = Path("countryrisk-argentina.csv")

    assert country_code_from_reproduced_file(path) is None


def test_country_code_from_reproduced_file_rejects_unknown_slug() -> None:
    path = Path("NLA_2026-07-08T113126_countryrisk-atlantis-v10_70ca2a2b_firmlevel.csv")

    assert country_code_from_reproduced_file(path) is None
