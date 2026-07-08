import numpy as np
import pandas as pd
import pytest

from countryrisk_replication.correlation import RunningStats


def test_running_stats_matches_numpy_corrcoef() -> None:
    rng = np.random.default_rng(20260708)
    x = rng.normal(size=1_000)
    y = 0.7 * x + rng.normal(scale=0.3, size=1_000)
    x[::17] = np.nan
    y[::29] = np.nan

    stats = RunningStats()
    stats.add_arrays(pd.Series(x), pd.Series(y))
    valid = ~(np.isnan(x) | np.isnan(y))

    assert stats.n == int(valid.sum())
    assert stats.pearson() == pytest.approx(float(np.corrcoef(x[valid], y[valid])[0, 1]))


def test_running_stats_is_equivalent_across_chunks() -> None:
    x = pd.Series([1.0, 2.0, 3.0, None, 5.0, 6.0])
    y = pd.Series([2.0, 4.0, 9.0, 1.0, None, 12.0])

    one_batch = RunningStats()
    one_batch.add_arrays(x, y)

    chunked = RunningStats()
    chunked.add_arrays(x.iloc[:3], y.iloc[:3])
    chunked.add_arrays(x.iloc[3:], y.iloc[3:])

    assert chunked.n == one_batch.n
    assert chunked.pearson() == pytest.approx(one_batch.pearson())


def test_running_stats_is_stable_with_large_offsets() -> None:
    rng = np.random.default_rng(20260708)
    x = 1_000_000 + rng.normal(scale=0.5, size=315_000)
    y = x + rng.normal(scale=0.5, size=315_000)

    one_batch = RunningStats()
    one_batch.add_arrays(pd.Series(x), pd.Series(y))

    chunked = RunningStats()
    for start in range(0, len(x), 10_000):
        chunked.add_arrays(pd.Series(x[start : start + 10_000]), pd.Series(y[start : start + 10_000]))

    expected = float(np.corrcoef(x, y)[0, 1])

    assert one_batch.pearson() == pytest.approx(expected, abs=1e-12)
    assert chunked.pearson() == pytest.approx(expected, abs=1e-12)


def test_running_stats_returns_none_for_insufficient_or_constant_data() -> None:
    single = RunningStats()
    single.add_arrays(pd.Series([1.0]), pd.Series([2.0]))

    constant = RunningStats()
    constant.add_arrays(pd.Series([1.0, 1.0, 1.0]), pd.Series([2.0, 3.0, 4.0]))

    assert single.pearson() is None
    assert constant.pearson() is None
