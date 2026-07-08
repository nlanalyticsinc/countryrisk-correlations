import pandas as pd

from countryrisk_replication.correlation import (
    quarter_code_from_datetime,
    quarter_code_from_string,
    quarter_label,
)


def test_quarter_code_from_string_labels_realistic_timestamps() -> None:
    timestamps = pd.Series(
        [
            "2020-01-15 13:30:00.000000000Z",
            "2020-03-31",
            "2020-04-01",
            "2020-12-31",
        ]
    )

    labels = [quarter_label(int(code)) for code in quarter_code_from_string(timestamps)]

    assert labels == ["2020Q1", "2020Q1", "2020Q2", "2020Q4"]


def test_quarter_code_from_datetime_labels() -> None:
    dates = pd.Series(pd.to_datetime(["2003-01-01", "2003-06-30", "2020-12-31"]))

    labels = [quarter_label(int(code)) for code in quarter_code_from_datetime(dates)]

    assert labels == ["2003Q1", "2003Q2", "2020Q4"]


def test_quarter_code_from_string_coerces_bad_values() -> None:
    codes = quarter_code_from_string(pd.Series(["bad", None, "2020-13-01"]))

    assert codes.isna().tolist() == [True, True, True]
