"""
头肩底形态策略 (Inverse Head and Shoulders)

识别条件:
  1. 三个依次排列的局部低点: 左肩（L）、头（H，最低）、右肩（R）
  2. 头必须是三者中最低的点（L > H < R）
  3. 两肩价格相近，高度差 <= shoulder_diff
  4. 颈线由头两侧各自的局部高点决定（取两侧最高点的均值）
  5. 当前收盘价接近或突破颈线（允许 price_tolerance 误差）
  6. 右肩必须是近期形成，避免把已经涨上去的旧形态继续当作今日入场

评分: 已突破颈线 → 0.95，仅接近颈线 → 0.88
"""

import pandas as pd
from typing import List
from .base import BaseStrategy, SignalResult


class HSBottomStrategy(BaseStrategy):
    """
    头肩底形态策略

    Parameters
    ----------
    max_width : int
        整个形态最大宽度（K 线数），默认 70
    price_tolerance : float
        接近颈线但未突破的容忍范围，默认 0.02（2%）
    shoulder_diff : float
        两肩高度差最大比例，默认 0.06（6%）
    local_window : int
        判断局部极值的左右窗口大小，默认 3
    max_entry_age : int
        右肩距今天最多 K 线根数，默认 5
    max_entry_extension : float
        当前收盘价相对右肩低点的最大涨幅，默认 0.08（8%）
    """

    def __init__(
        self,
        max_width: int = 70,
        price_tolerance: float = 0.02,
        shoulder_diff: float = 0.06,
        local_window: int = 3,
        max_entry_age: int = 5,
        max_entry_extension: float = 0.08,
    ):
        self.max_width = max_width
        self.price_tolerance = price_tolerance
        self.shoulder_diff = shoulder_diff
        self.local_window = local_window
        self.max_entry_age = max_entry_age
        self.max_entry_extension = max_entry_extension

    @property
    def name(self) -> str:
        return "头肩底"

    # ── 工具函数 ───────────────────────────────────────────────────────────

    def _local_lows(self, df: pd.DataFrame) -> List[int]:
        w = self.local_window
        result = []
        for i in range(w, len(df) - w):
            if df.iloc[i]["low"] == df.iloc[i - w : i + w + 1]["low"].min():
                result.append(i)
        return result

    def _local_highs(self, df: pd.DataFrame) -> List[int]:
        w = self.local_window
        result = []
        for i in range(w, len(df) - w):
            if df.iloc[i]["high"] == df.iloc[i - w : i + w + 1]["high"].max():
                result.append(i)
        return result

    # ── 主入口 ────────────────────────────────────────────────────────────

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        no = SignalResult(triggered=False, name=self.name, score=0.0)
        if len(data) < 70:
            return no

        lows = self._local_lows(data)
        highs = self._local_highs(data)
        if len(lows) < 3 or len(highs) < 2:
            return no

        current_close = data.iloc[-1]["close"]

        for i in range(len(lows) - 2):
            l_idx, h_idx, r_idx = lows[i], lows[i + 1], lows[i + 2]

            if not (l_idx < h_idx < r_idx):
                continue
            if r_idx - l_idx > self.max_width:
                continue
            bars_since_right = len(data) - 1 - r_idx
            if bars_since_right > self.max_entry_age:
                continue

            l_price = data.iloc[l_idx]["low"]
            h_price = data.iloc[h_idx]["low"]   # 头（最低点）
            r_price = data.iloc[r_idx]["low"]
            if current_close > r_price * (1 + self.max_entry_extension):
                continue

            # 头必须是最低点
            if not (h_price < l_price and h_price < r_price):
                continue

            # 两肩高度相近
            if abs(l_price - r_price) / l_price > self.shoulder_diff:
                continue

            # 颈线: 两侧各自区间内最高点的均值
            left_highs = [h for h in highs if l_idx < h < h_idx]
            right_highs = [h for h in highs if h_idx < h < r_idx]
            if not left_highs or not right_highs:
                continue

            left_neck = max(data.iloc[h]["high"] for h in left_highs)
            right_neck = max(data.iloc[h]["high"] for h in right_highs)
            neckline = (left_neck + right_neck) / 2

            # 当前收盘接近或突破颈线
            if current_close >= neckline * (1 - self.price_tolerance):
                breakout_pct = (current_close - neckline) / neckline
                score = 0.95 if breakout_pct > 0 else 0.88
                return SignalResult(
                    triggered=True,
                    name=self.name,
                    score=score,
                    details={
                        "left_shoulder": round(l_price, 2),
                        "head": round(h_price, 2),
                        "right_shoulder": round(r_price, 2),
                        "left_neckline": round(left_neck, 2),
                        "right_neckline": round(right_neck, 2),
                        "neckline": round(neckline, 2),
                        "shoulder_diff_pct": round(abs(l_price - r_price) / l_price * 100, 2),
                        "width_bars": r_idx - l_idx,
                        "bars_since_right_shoulder": bars_since_right,
                        "entry_extension_pct": round((current_close - r_price) / r_price * 100, 2),
                        "breakout_pct": round(breakout_pct * 100, 2),
                    },
                )

        return no
