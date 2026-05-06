"""
均线策略 (Moving Average Strategy)

4种入场形态（仅使用 MA5 / MA20）:
  1. 上升趋势回踩  — 上升趋势中 MA5 回踩 MA20 附近，当日收盘回升
  2. 跌穿回归      — 上升趋势中 MA5 小幅跌穿 MA20，当日开始收复
  3. 金叉反转      — 下降趋势中 MA5 由下而上穿越 MA20
  4. 超卖反弹      — 下降/横盘趋势中 MA5 大幅低于 MA20，价格企稳反弹

趋势判断: 取近 20 天 MA60 的斜率，>1.5% 为上升，<-1.5% 为下降，其余横盘。
"""

import pandas as pd
from .base import BaseStrategy, SignalResult


class MAStrategy(BaseStrategy):
    """
    均线策略

    Parameters
    ----------
    ma_short : int
        短期均线周期，默认 5
    ma_long : int
        长期均线周期，默认 20
    trend_window : int
        趋势判断用的长期均线周期，默认 60
    oversold_threshold : float
        超卖阈值：MA5 低于 MA20 的比例，默认 -0.08（即 -8%）
    """

    def __init__(
        self,
        ma_short: int = 5,
        ma_long: int = 20,
        trend_window: int = 60,
        oversold_threshold: float = -0.08,
    ):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.trend_window = trend_window
        self.oversold_threshold = oversold_threshold

    @property
    def name(self) -> str:
        return "MA均线"

    # ── 内部工具 ──────────────────────────────────────────────────────────

    def _add_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ma5"] = df["close"].rolling(self.ma_short).mean()
        df["ma20"] = df["close"].rolling(self.ma_long).mean()
        df["ma60"] = df["close"].rolling(self.trend_window).mean()
        return df

    def _trend(self, df: pd.DataFrame) -> str:
        """根据近 20 天 MA60 斜率判断趋势"""
        recent = df.iloc[-20:]
        if recent["ma60"].isna().any():
            return "unknown"
        slope = (recent["ma60"].iloc[-1] - recent["ma60"].iloc[0]) / recent["ma60"].iloc[0]
        if slope > 0.015:
            return "up"
        if slope < -0.015:
            return "down"
        return "sideways"

    # ── 主入口 ────────────────────────────────────────────────────────────

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        no = SignalResult(triggered=False, name=self.name, score=0.0)
        if len(data) < self.trend_window:
            return no

        df = self._add_ma(data)
        trend = self._trend(df)

        cur, prev = df.iloc[-1], df.iloc[-2]
        ma5, ma20, close = cur["ma5"], cur["ma20"], cur["close"]

        if pd.isna(ma5) or pd.isna(ma20) or ma20 == 0:
            return no

        dist = (ma5 - ma20) / ma20
        prev_dist = (prev["ma5"] - prev["ma20"]) / prev["ma20"] if prev["ma20"] else 0

        base_details = {
            "trend": trend,
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "dist_pct": round(dist * 100, 2),
            "close": round(close, 2),
        }

        # ── 形态 1: 上升趋势回踩 ─────────────────────────────────────────
        # 趋势向上，近 5 天内 MA5 曾触碰 MA20，今日收盘高于昨日
        if trend == "up" and -0.02 <= dist <= 0.015:
            recent5_dist = ((df["ma5"] - df["ma20"]) / df["ma20"]).iloc[-5:]
            if recent5_dist.dropna().min() < 0.005 and close > prev["close"] * 1.005:
                return SignalResult(
                    triggered=True, name="MA回踩反弹", score=0.85,
                    details={**base_details, "pattern": "上升趋势回踩"},
                )

        # ── 形态 2: 跌穿回归 ─────────────────────────────────────────────
        # 上升趋势中 MA5 小幅跌穿 MA20，当日开始收复（dist 改善）
        if trend == "up" and -0.04 <= dist < -0.005 and prev_dist < dist and close > prev["close"]:
            return SignalResult(
                triggered=True, name="MA跌穿回归", score=0.80,
                details={**base_details, "pattern": "跌穿回归"},
            )

        # ── 形态 3: 金叉反转 ─────────────────────────────────────────────
        # 下降趋势中 MA5 从下方穿越 MA20，收盘站上 MA5
        if trend == "down" and prev_dist < 0 < dist and close > ma5 and close > prev["close"]:
            return SignalResult(
                triggered=True, name="MA金叉反转", score=0.90,
                details={**base_details, "pattern": "金叉反转"},
            )

        # ── 形态 4: 超卖反弹 ─────────────────────────────────────────────
        # 下降/横盘趋势中 MA5 大幅低于 MA20，近 5 天低点企稳后价格回升
        if trend in ("down", "sideways") and dist <= self.oversold_threshold:
            recent_low = df.iloc[-5:]["low"].min()
            if close > recent_low * 1.015:
                return SignalResult(
                    triggered=True, name="MA超卖反弹", score=0.75,
                    details={**base_details, "pattern": "超卖反弹"},
                )

        return no
