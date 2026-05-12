"""
颈线/支撑位反弹策略 (Support Line Bounce)

逻辑:
  1. 在过去 lookback 天内，找出局部低点作为候选支撑位
  2. 「测试」定义: 最低价在支撑价 ± support_tolerance 范围内，
     或短暂跌破但当日收盘仍在支撑区上方（假跌破）
  3. 支撑位形成后不能被有效跌破
  4. 今日低点再次回踩支撑位，且收盘仍守在支撑区附近
  5. 近 3 天价格收窄，或今日阳线拉回确认

评分基础 0.75，每多一次测试 +0.05，上限 0.95。
"""

import pandas as pd
from typing import List, Dict
from .base import BaseStrategy, SignalResult


class SupportBounceStrategy(BaseStrategy):
    """
    颈线支撑反弹策略

    Parameters
    ----------
    lookback : int
        寻找支撑位的回溯天数，默认 60
    support_tolerance : float
        触碰支撑位的容忍范围，默认 0.03（3%）
    entry_tolerance : float
        入场当天低点回踩支撑位的容忍范围，默认 0.04（4%）
    near_tolerance : float
        弱反弹时收盘价距离支撑位的上限容忍，默认 0.05（5%）
    fake_break_tolerance : float
        假跌破最大幅度，默认 0.02（2%）
    min_tests : int
        支撑位被有效测试的最少次数，默认 2
    min_test_gap : int
        两次测试之间的最小间隔（K 线数），默认 5
    max_support_age : int
        支撑位距今最多 N 根 K 线，默认 60
    min_support_age : int
        支撑位距今最少 N 根 K 线（过近的不算支撑），默认 15
    local_window : int
        判断局部低点的左右窗口大小，默认 5
    support_zone_position : float
        支撑候选必须处于近 lookback 区间价格低位，默认 0.4
    """

    def __init__(
        self,
        lookback: int = 60,
        support_tolerance: float = 0.03,
        entry_tolerance: float = 0.04,
        near_tolerance: float = 0.05,
        fake_break_tolerance: float = 0.02,
        min_tests: int = 2,
        min_test_gap: int = 5,
        max_support_age: int = 60,
        min_support_age: int = 15,
        local_window: int = 5,
        support_zone_position: float = 0.4,
    ):
        self.lookback = lookback
        self.support_tolerance = support_tolerance
        self.entry_tolerance = entry_tolerance
        self.near_tolerance = near_tolerance
        self.fake_break_tolerance = fake_break_tolerance
        self.min_tests = min_tests
        self.min_test_gap = min_test_gap
        self.max_support_age = max_support_age
        self.min_support_age = min_support_age
        self.local_window = local_window
        self.support_zone_position = support_zone_position

    @property
    def name(self) -> str:
        return "支撑位反弹"

    # ── 内部工具 ───────────────────────────────────────────────────────────

    def _is_support_test(
        self,
        row: pd.Series,
        support_price: float,
        tolerance: float = None,
    ) -> bool:
        """判断单根 K 线是否有效测试支撑位"""
        tolerance = self.support_tolerance if tolerance is None else tolerance
        low, close = row["low"], row["close"]
        diff = abs(low - support_price) / support_price
        below = (support_price - low) / support_price  # 正数表示跌破

        is_touch = diff <= tolerance
        is_fake_break = (
            0 < below <= self.fake_break_tolerance
            and close >= support_price * (1 - tolerance / 2)
        )
        return is_touch or is_fake_break

    def _local_lows(self, data: pd.DataFrame, start_i: int, end_i: int) -> List[int]:
        """找回溯区间内的局部低点，避免只盯绝对最低的旧低点。"""
        window = self.local_window
        lows = []
        left = max(window, start_i)
        right = min(len(data) - window - 1, end_i)
        for i in range(left, right + 1):
            if data.iloc[i]["low"] == data.iloc[i - window : i + window + 1]["low"].min():
                lows.append(i)
        return lows

    def _support_candidates(self, data: pd.DataFrame, lb_start: int, cur_i: int) -> List[Dict]:
        """按低位局部低点优先生成候选支撑，避免把高位平台当底部支撑。"""
        recent = data.iloc[lb_start:cur_i]
        low_floor = recent["low"].min()
        high_ceiling = recent["high"].max()
        max_support_price = low_floor + (high_ceiling - low_floor) * self.support_zone_position

        local_low_indices = self._local_lows(data, lb_start, cur_i - 1)
        indices = [
            i for i in local_low_indices
            if data.iloc[i]["low"] <= max_support_price
        ]
        if not indices:
            indices = data.iloc[lb_start:cur_i].nsmallest(8, "low").index.tolist()
        indices = sorted(set(indices), reverse=True)
        return [
            {"idx": i, "date": data.iloc[i]["date"], "low": data.iloc[i]["low"]}
            for i in indices
        ]

    def _count_tests(
        self, data: pd.DataFrame, support_price: float, start_i: int, end_i: int
    ) -> tuple[int, int]:
        """统计支撑测试次数，并返回最后一次测试位置"""
        count = 0
        last_test_i = -999
        for i in range(start_i, end_i + 1):
            row = data.iloc[i]
            if self._is_support_test(row, support_price) and (i - last_test_i) >= self.min_test_gap:
                count += 1
                last_test_i = i
        return count, last_test_i

    def _support_intact(
        self, data: pd.DataFrame, support_price: float, start_i: int, end_i: int
    ) -> bool:
        """支撑形成后若被明显跌破，则该支撑失效。"""
        if end_i < start_i:
            return True

        for i in range(start_i, end_i + 1):
            row = data.iloc[i]
            below = (support_price - row["low"]) / support_price
            if below > self.fake_break_tolerance:
                return False
        return True

    def _is_consolidation(self, data: pd.DataFrame, end_i: int, days: int = 3) -> bool:
        """近 days 根 K 线价格是否收窄（振幅 < 6%）"""
        start_i = max(0, end_i - days + 1)
        seg = data.iloc[start_i : end_i + 1]
        if len(seg) < days:
            return False
        rng = (seg["high"].max() - seg["low"].min()) / seg["close"].mean()
        return rng < 0.06

    # ── 主入口 ────────────────────────────────────────────────────────────

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        no = SignalResult(triggered=False, name=self.name, score=0.0)
        if len(data) < self.lookback + 10:
            return no

        cur_i = len(data) - 1
        cur = data.iloc[cur_i]
        prev = data.iloc[cur_i - 1]
        rebound_confirmed = cur["close"] > cur["open"] and cur["close"] > prev["close"]

        # 盘整或阳线拉回确认，二者满足其一即可。
        is_consolidation = self._is_consolidation(data, cur_i - 1, days=3)
        if not (is_consolidation or rebound_confirmed):
            return no

        lb_start = max(0, cur_i - self.lookback)
        candidates = self._support_candidates(data, lb_start, cur_i)

        for cand in candidates:
            support_price = cand["low"]
            support_date = pd.to_datetime(cand["date"])
            cur_date = pd.to_datetime(cur["date"])

            bars_ago = cur_i - cand["idx"]
            days_ago = (cur_date - support_date).days
            if not (self.min_support_age <= bars_ago <= self.max_support_age):
                continue

            if not self._support_intact(data, support_price, cand["idx"] + 1, cur_i - 1):
                continue

            # 今日必须回踩支撑位，且收盘仍在支撑区附近
            if not self._is_support_test(cur, support_price, tolerance=self.entry_tolerance):
                continue

            price_to_support = (cur["close"] - support_price) / support_price
            max_close_extension = None if rebound_confirmed else self.near_tolerance
            if price_to_support < -self.entry_tolerance / 2:
                continue
            if max_close_extension is not None and price_to_support > max_close_extension:
                continue

            # 历史测试 + 今天这次回踩。若今天已经明显拉离支撑，
            # 必须是一次新的有效测试，避免几天前的入场点反复触发。
            tests, last_test_i = self._count_tests(data, support_price, cand["idx"], cur_i - 1)
            if cur_i - last_test_i >= self.min_test_gap:
                tests += 1
            elif price_to_support > self.near_tolerance:
                continue
            if tests < self.min_tests:
                continue

            score = min(0.75 + (tests - 1) * 0.05, 0.95)
            return SignalResult(
                triggered=True,
                name=self.name,
                score=score,
                details={
                    "support_price": round(support_price, 2),
                    "support_date": str(support_date)[:10],
                    "test_count": tests,
                    "bars_ago": bars_ago,
                    "days_ago": days_ago,
                    "current_low": round(cur["low"], 2),
                    "low_to_support_pct": round((cur["low"] - support_price) / support_price * 100, 2),
                    "price_to_support_pct": round(price_to_support * 100, 2),
                    "consolidation": is_consolidation,
                    "rebound_confirmed": rebound_confirmed,
                },
            )

        return no
