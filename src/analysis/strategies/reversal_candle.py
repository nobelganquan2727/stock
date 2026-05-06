"""
K线反包策略 (Reversal Candle Strategy)

入场条件（全部满足）:
  1. 近 N 天连续下跌（至少 min_down_days 天收阴），累计跌幅 >= min_decline
  2. 下跌过程中成交量逐渐放大（后半段均量 > 前半段均量），代表恐慌抛售加剧
  3. 当日出现阳线吞噬（今收 > 昨开，且今开 < 昨收），代表主力反手
  4. 当日成交量 >= 近 10 天均量 × volume_ratio（巨量确认）

评分加成: 若成交量同时是近 10 天最高 + 量能在下跌中持续放大，得分提升至 0.92。
"""

import pandas as pd
from .base import BaseStrategy, SignalResult


class ReversalCandleStrategy(BaseStrategy):
    """
    K线反包策略

    Parameters
    ----------
    lookback : int
        检测连续下跌的观察窗口（天），默认 5
    min_decline : float
        窗口内累计跌幅下限，默认 0.05（5%）
    min_down_days : int
        窗口内最少下跌天数，默认 3
    volume_ratio : float
        反包当日成交量相对于近 10 天均量的最低倍数，默认 1.8
    """

    def __init__(
        self,
        lookback: int = 5,
        min_decline: float = 0.05,
        min_down_days: int = 3,
        volume_ratio: float = 1.8,
    ):
        self.lookback = lookback
        self.min_decline = min_decline
        self.min_down_days = min_down_days
        self.volume_ratio = volume_ratio

    @property
    def name(self) -> str:
        return "K线反包"

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        no = SignalResult(triggered=False, name=self.name, score=0.0)
        need = self.lookback + 5
        if len(data) < need:
            return no

        today = data.iloc[-1]
        yesterday = data.iloc[-2]

        # ── 1. 检查近 N 天下跌情况（不含今天）────────────────────────────
        window = data.iloc[-(self.lookback + 1):-1]
        daily_ret = window["close"].pct_change().dropna()
        down_days = int((daily_ret < 0).sum())

        if down_days < self.min_down_days:
            return no

        # 累计跌幅
        total_decline = window["close"].iloc[-1] / window["close"].iloc[0] - 1
        if total_decline > -self.min_decline:
            return no

        # ── 2. 量能是否在下跌中放大 ────────────────────────────────────
        mid = len(window) // 2
        vol_early = window["volume"].iloc[:mid].mean()
        vol_late = window["volume"].iloc[mid:].mean()
        volume_expanding = vol_late > vol_early * 1.1

        # ── 3. 今日是否阳线吞噬 ────────────────────────────────────────
        is_bullish = today["close"] > today["open"]
        is_engulfing = (
            today["close"] > yesterday["open"]
            and today["open"] < yesterday["close"]
        )

        # ── 4. 今日成交量是否巨量 ──────────────────────────────────────
        avg_vol = data.iloc[-11:-1]["volume"].mean()
        if avg_vol == 0:
            return no
        vol_ratio_actual = today["volume"] / avg_vol
        vol_surge = vol_ratio_actual >= self.volume_ratio

        details = {
            "down_days": down_days,
            "total_decline_pct": round(total_decline * 100, 2),
            "volume_expanding": volume_expanding,
            "engulfing": is_engulfing,
            "volume_ratio": round(vol_ratio_actual, 2),
        }

        if is_bullish and is_engulfing and vol_surge:
            is_peak_vol = today["volume"] >= data.iloc[-10:]["volume"].max()
            score = 0.92 if (volume_expanding and is_peak_vol) else 0.85
            return SignalResult(triggered=True, name=self.name, score=score, details=details)

        return no
