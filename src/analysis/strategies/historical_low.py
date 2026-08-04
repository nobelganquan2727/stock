"""
历史低点策略

在近 ~2 年（全部可用历史数据）窗口内，若当日最低价或收盘价
触及 / 逼近历史最低价，则触发提醒。
"""

import pandas as pd
from .base import BaseStrategy, SignalResult


class HistoricalLowStrategy(BaseStrategy):
    """
    历史低点：
    - 历史低点 = 窗口内所有交易日 low 的最小值（含当日）
    - 触发：当日 low 或 close 距离历史低点 ≤ tolerance_pct
    - 若当日创出新低（low == 历史低点），额外加分
    """

    def __init__(self, tolerance_pct: float = 1.0, min_bars: int = 120):
        self.tolerance_pct = tolerance_pct
        self.min_bars = min_bars

    @property
    def name(self) -> str:
        return "历史低点"

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        if data is None or len(data) < self.min_bars:
            return SignalResult(
                False,
                self.name,
                0.0,
                {"reason": f"数据不足{self.min_bars}天"},
            )

        df = data.copy()
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)

        hist_low = float(df["low"].min())
        if hist_low <= 0:
            return SignalResult(False, self.name, 0.0, {"reason": "历史低点无效"})

        last = df.iloc[-1]
        current_low = float(last["low"])
        current_close = float(last["close"])

        # 距历史低点的百分比（用更接近的那个价格）
        dist_by_low = (current_low / hist_low - 1.0) * 100
        dist_by_close = (current_close / hist_low - 1.0) * 100
        best_dist = min(dist_by_low, dist_by_close)

        is_new_low = abs(current_low - hist_low) / hist_low <= 1e-6
        near_low = best_dist <= self.tolerance_pct

        if not (is_new_low or near_low):
            return SignalResult(
                False,
                self.name,
                0.0,
                {
                    "reason": "未触及历史低点",
                    "hist_low": round(hist_low, 3),
                    "current_low": round(current_low, 3),
                    "current_close": round(current_close, 3),
                    "dist_pct": round(best_dist, 2),
                },
            )

        # 越贴近低点分数越高；创出新低给满分
        if is_new_low:
            score = 1.0
            pattern = "创历史新低"
        else:
            # tolerance 内线性映射到 0.70 ~ 0.95
            score = round(0.95 - 0.25 * (best_dist / max(self.tolerance_pct, 1e-6)), 2)
            score = max(0.70, min(0.95, score))
            pattern = "逼近历史低点"

        # 历史低点出现的日期（取最早一次）
        low_idx = df["low"].idxmin()
        hist_low_date = df.loc[low_idx, "date"]
        if hasattr(hist_low_date, "strftime"):
            hist_low_date = hist_low_date.strftime("%Y-%m-%d")
        else:
            hist_low_date = str(hist_low_date)

        lookback_days = len(df)
        return SignalResult(
            True,
            self.name,
            score,
            {
                "pattern": pattern,
                "hist_low": round(hist_low, 3),
                "hist_low_date": hist_low_date,
                "current_low": round(current_low, 3),
                "current_close": round(current_close, 3),
                "dist_pct": round(best_dist, 2),
                "lookback_days": lookback_days,
                "tolerance_pct": self.tolerance_pct,
                "is_new_low": is_new_low,
            },
        )
