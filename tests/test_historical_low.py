"""历史低点策略单元测试（无需数据库）"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
from analysis.strategies.historical_low import HistoricalLowStrategy


def _make_df(lows, closes=None):
    n = len(lows)
    closes = closes if closes is not None else lows
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": closes,
        "high": [max(l, c) * 1.01 for l, c in zip(lows, closes)],
        "low": lows,
        "close": closes,
        "volume": [1_000_000] * n,
    })


def test_new_historical_low():
    lows = [10.0] * 150 + [9.0]  # 最后一天创新低
    closes = [10.2] * 150 + [9.1]
    s = HistoricalLowStrategy(tolerance_pct=1.0, min_bars=120)
    result = s.analyze(_make_df(lows, closes))
    assert result.triggered
    assert result.details["is_new_low"] is True
    assert result.details["pattern"] == "创历史新低"
    assert result.score == 1.0


def test_near_historical_low():
    lows = [10.0] * 150 + [10.05]  # 距低点 0.5%
    closes = [10.2] * 150 + [10.08]
    s = HistoricalLowStrategy(tolerance_pct=1.0, min_bars=120)
    result = s.analyze(_make_df(lows, closes))
    assert result.triggered
    assert result.details["is_new_low"] is False
    assert result.details["pattern"] == "逼近历史低点"
    assert result.details["dist_pct"] <= 1.0


def test_not_near_low():
    lows = [10.0] * 150 + [12.0]
    closes = [10.2] * 150 + [12.1]
    s = HistoricalLowStrategy(tolerance_pct=1.0, min_bars=120)
    result = s.analyze(_make_df(lows, closes))
    assert not result.triggered


def test_insufficient_data():
    s = HistoricalLowStrategy(min_bars=120)
    result = s.analyze(_make_df([10.0] * 50))
    assert not result.triggered
    assert "数据不足" in result.details["reason"]


def test_watchlist_count():
    from watchlist import WATCHLIST_CODES, get_stock_name
    assert len(WATCHLIST_CODES) == 50
    assert get_stock_name("600519.SS") == "贵州茅台"
    assert get_stock_name("300750.SZ") == "宁德时代"
    assert len(set(WATCHLIST_CODES)) == 50


if __name__ == "__main__":
    test_watchlist_count()
    test_new_historical_low()
    test_near_historical_low()
    test_not_near_low()
    test_insufficient_data()
    print("All tests passed.")
