import pandas as pd

from countryrisk_replication.panel import stata_internal_carry_forward


def panel(rows: list[tuple[int, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country_id": 1,
                "gvkey_num": gvkey,
                "quarter_code": quarter,
                "rep_observed_risk": value,
            }
            for gvkey, quarter, value in rows
        ]
    )


def quarter_values(filled: pd.DataFrame) -> dict[int, float]:
    return dict(zip(filled["quarter_code"], filled["rep_filled_risk"], strict=True))


def test_internal_gap_up_to_four_quarters_is_fully_filled() -> None:
    filled = stata_internal_carry_forward(
        panel([(10, 100, 1.0), (10, 105, 5.0)]),
        quarter_start=100,
        quarter_end=105,
    )

    assert quarter_values(filled) == {
        100: 1.0,
        101: 1.0,
        102: 1.0,
        103: 1.0,
        104: 1.0,
        105: 5.0,
    }


def test_internal_gap_longer_than_four_quarters_is_truncated() -> None:
    filled = stata_internal_carry_forward(
        panel([(10, 200, 2.0), (10, 206, 6.0)]),
        quarter_start=200,
        quarter_end=206,
    )

    assert quarter_values(filled) == {
        200: 2.0,
        201: 2.0,
        202: 2.0,
        203: 2.0,
        204: 2.0,
        206: 6.0,
    }


def test_leading_and_trailing_gaps_are_not_filled() -> None:
    filled = stata_internal_carry_forward(
        panel([(10, 303, 3.0), (10, 306, 6.0)]),
        quarter_start=300,
        quarter_end=308,
    )

    assert quarter_values(filled) == {
        303: 3.0,
        304: 3.0,
        305: 3.0,
        306: 6.0,
    }


def test_single_observation_does_not_create_carried_rows() -> None:
    filled = stata_internal_carry_forward(
        panel([(10, 400, 4.0)]),
        quarter_start=398,
        quarter_end=405,
    )

    assert quarter_values(filled) == {400: 4.0}
