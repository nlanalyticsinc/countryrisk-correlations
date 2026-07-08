import pandas as pd

from countryrisk_replication.panel import quarter_code_from_date_like, quarter_label


def test_quarter_code_from_date_like_labels_realistic_timestamps() -> None:
    values = pd.Series(
        [
            "2020-01-15 13:30:00.000000000Z",
            "2020-03-31",
            "2020-04-01",
            "2020-12-31",
            "2020/01/15",
            "20200115",
        ]
    )

    labels = [quarter_label(int(code)) for code in quarter_code_from_date_like(values)]

    assert labels == ["2020Q1", "2020Q1", "2020Q2", "2020Q4", "2020Q1", "2020Q1"]


def test_quarter_code_from_date_like_handles_datetimes() -> None:
    dates = pd.Series(pd.to_datetime(["2003-01-01", "2003-06-30", "2020-12-31"]))

    labels = [quarter_label(int(code)) for code in quarter_code_from_date_like(dates)]

    assert labels == ["2003Q1", "2003Q2", "2020Q4"]


def test_quarter_code_from_date_like_does_not_wrap_large_years() -> None:
    code = int(quarter_code_from_date_like(pd.Series(["9000-01-01"])).iloc[0])

    assert code == 36001
    assert quarter_label(code) == "9000Q1"


def test_quarter_code_from_date_like_coerces_bad_and_ambiguous_values() -> None:
    codes = quarter_code_from_date_like(pd.Series(["bad", None, "2020-13-01", "01/15/2020"]))

    assert codes.isna().tolist() == [True, True, True, True]
