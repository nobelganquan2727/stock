"""
W 底形态策略 (Double Bottom / W-Bottom)

识别条件:
  1. 找出两个价格相近的局部低点（左底、右底），价差 <= price_tolerance
  2. 两底间距在 [min_width, max_width] K 线根数之间
  3. 两底之间有一个局部高点作为颈线
  4. 底部到颈线的深度 >= min_depth
  5. 当前收盘价接近或突破颈线（允许 breakout_tolerance 的误差）
  6. 右底必须是近期形成，且当前价不能离底部过远，避免追几天前的信号

评分: 已突破颈线 → 0.95，仅接近颈线 → 0.85
"""

import pandas as pd
from typing import List
from .base import BaseStrategy, SignalResult


class WBottomStrategy(BaseStrategy):
    """
    W 底形态策略

    Parameters
    ----------
    price_tolerance : float
        两底价格差容忍比例，默认 0.03（3%）
    min_width : int
        两底最小间隔 K 线数，默认 10
    max_width : int
        两底最大间隔 K 线数，默认 50
    min_depth : float
        底部到颈线最小深度比例，默认 0.05（5%）
    breakout_tolerance : float
        接近颈线但未突破的容忍范围，默认 0.02（2%）
    local_window : int
        判断局部极值的左右窗口大小，默认 3
    max_entry_age : int
        右底距今天最多 K 线根数，默认 5
    max_entry_extension : float
        当前收盘价相对右底的最大涨幅，默认 0.08（8%）
    """

    def __init__(
        self,
        price_tolerance: float = 0.03,
        min_width: int = 10,
        max_width: int = 50,
        min_depth: float = 0.05,
        breakout_tolerance: float = 0.02,
        local_window: int = 3,
        max_entry_age: int = 5,
        max_entry_extension: float = 0.08,
    ):
        self.price_tolerance = price_tolerance
        self.min_width = min_width
        self.max_width = max_width
        self.min_depth = min_depth
        self.breakout_tolerance = breakout_tolerance
        self.local_window = local_window
        self.max_entry_age = max_entry_age
        self.max_entry_extension = max_entry_extension

    @property
    def name(self) -> str:
        return "W底"

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
        if len(data) < 50:
            return no

        lows = self._local_lows(data)
        highs = self._local_highs(data)
        if len(lows) < 2 or len(highs) < 1:
            return no

        current_close = data.iloc[-1]["close"]

        # 从最近的低点向前搜索，找最新的 W 底
        for i in range(len(lows) - 1, 0, -1):
            r_idx = lows[i]
            r_price = data.iloc[r_idx]["low"]
            bars_since_right = len(data) - 1 - r_idx
            if bars_since_right > self.max_entry_age:
                continue
            if current_close > r_price * (1 + self.max_entry_extension):
                continue

            for j in range(i - 1, max(i - 8, -1), -1):
                l_idx = lows[j]
                l_price = data.iloc[l_idx]["low"]

                width = r_idx - l_idx
                if not (self.min_width <= width <= self.max_width):
                    continue

                # 两底价格相近
                if abs(r_price - l_price) / l_price > self.price_tolerance:
                    continue

                # 颈线 = 两底之间最高的局部高点
                mid_highs = [h for h in highs if l_idx < h < r_idx]
                if not mid_highs:
                    continue
                neck_idx = max(mid_highs, key=lambda h: data.iloc[h]["high"])
                neckline = data.iloc[neck_idx]["high"]

                # 深度检查
                bottom = min(l_price, r_price)
                depth = (neckline - bottom) / bottom
                if depth < self.min_depth:
                    continue

                # 当前收盘接近或突破颈线
                if current_close >= neckline * (1 - self.breakout_tolerance):
                    breakout_pct = (current_close - neckline) / neckline
                    score = 0.95 if breakout_pct > 0 else 0.85
                    return SignalResult(
                        triggered=True,
                        name=self.name,
                        score=score,
                        details={
                            "left_bottom": round(l_price, 2),
                            "right_bottom": round(r_price, 2),
                            "neckline": round(neckline, 2),
                            "depth_pct": round(depth * 100, 2),
                            "width_bars": width,
                            "bars_since_right_bottom": bars_since_right,
                            "entry_extension_pct": round((current_close - r_price) / r_price * 100, 2),
                            "breakout_pct": round(breakout_pct * 100, 2),
                        },
                    )

        return no
