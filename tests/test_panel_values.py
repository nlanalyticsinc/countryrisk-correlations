from pathlib import Path

import pandas as pd
import pytest

from countryrisk_replication.panel import build_reproduced_panel, load_gvkey_crosswalk


@pytest.mark.parametrize("column", ["risk", "nr_of_words"])
@pytest.mark.parametrize("value", ["", "broken", "inf", "-inf", "NaN"])
def test_mapped_calls_with_unusable_scores_do_not_affect_panel(
    tmp_path: Path, column: str, value: str
) -> None:
    calls = pd.DataFrame(
        {
            "earningscallID": ["good", "bad"],
            "start_time": ["2020-01-01"] * 2,
            "risk": ["1", "99"],
            "nr_of_words": ["1000", "1000"],
        }
    )
    calls.loc[1, column] = value
    path = tmp_path / "calls.csv"
    calls.to_csv(path, index=False)
    crosswalk = tmp_path / "gvkeys.csv"
    crosswalk.write_text("earningscallID,gvkey_compustat\ngood,1004\nbad,1004\n")
    logs: list[str] = []
    result = build_reproduced_panel(
        {"AR": path},
        {"AR": 1},
        1,
        8081,
        8081,
        logger=logs.append,
        gvkey_crosswalk=load_gvkey_crosswalk(crosswalk),
    )
    assert result.panel["rep_observed_risk"].tolist() == [100.0]
    assert any("1 calls with unusable scores" in line for line in logs)


@pytest.mark.parametrize("chunk_size", [1, 100])
def test_country_risk_uses_unweighted_mean_of_call_ratios(tmp_path: Path, chunk_size: int) -> None:
    path = tmp_path / "calls.csv"
    path.write_text("gvkey,start_time,risk,nr_of_words\n1004,2020-01-01,10,1000\n1004,2020-02-01,60,3000\n")
    result = build_reproduced_panel({"AR": path}, {"AR": 1}, chunk_size, 8081, 8081, logger=None)
    # mean(1000, 2000) = 1500; the word-weighted alternative would be 1750.
    assert result.panel["rep_observed_risk"].tolist() == [1500.0]
