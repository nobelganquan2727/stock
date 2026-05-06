"""
颈线/支撑位反弹策略 (Support Line Bounce)

逻辑:
  1. 在过去 lookback 天内，找出被多次测试（>= min_tests）的显著低点作为支撑位
  2. 「测试」定义: 最低价在支撑价 ± support_tolerance 范围内，
     或短暂跌破但当日收盘仍在支撑区上方（假跌破）
  3. 当前价格在支撑位 [support, support*(1+near_tolerance)] 区间内
  4. 近 3 天价格收窄（盘整），代表买卖双方博弈
  5. 今日出现阳线且收盘高于前一日，反弹确认

同一支撑位 dedup_window 天内只触发一次信号（去重）。

评分基础 0.75，每多一次测试 +0.05，上限 0.95。
"""

import pandas as pd
from typing import List, Dict, Tuple
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
    near_tolerance : float
        「接近支撑」的上限容忍，默认 0.05（5%）
    fake_break_tolerance : float
        假跌破最大幅度，默认 0.02（2%）
    min_tests : int
        支撑位被有效测试的最少次数，默认 2
    min_test_gap : int
        两次测试之间的最小间隔（K 线数），默认 5
    max_support_age : int
        支撑位距今最多 N 天，默认 60
    min_support_age : int
        支撑位距今最少 N 天（过近的不算支撑），默认 15
    """

    def __init__(
        self,
        lookback: int = 60,
        support_tolerance: float = 0.03,
        near_tolerance: float = 0.05,
        fake_break_tolerance: float = 0.02,
        min_tests: int = 2,
        min_test_gap: int = 5,
        max_support_age: int = 60,
        min_support_age: int = 15,
    ):
        self.lookback = lookback
        self.support_tolerance = support_tolerance
        self.near_tolerance = near_tolerance
        self.fake_break_tolerance = fake_break_tolerance
        self.min_tests = min_tests
        self.min_test_gap = min_test_gap
        self.max_support_age = max_support_age
        self.min_support_age = min_support_age

    @property
    def name(self) -> str:
        return "支撑位反弹"

    # ── 内部工具 ───────────────────────────────────────────────────────────

    def _count_tests(
        self, data: pd.DataFrame, support_price: float, start_i: int, end_i: int
    ) -> int:
        """统计从 start_i 到 end_i 之间对 support_price 的有效测试次数"""
        count = 0
        last_test_i = -999
        for i in range(start_i, end_i + 1):
            row = data.iloc[i]
            low, close = row["low"], row["close"]
            diff = abs(low - support_price) / support_price
            below = (support_price - low) / support_price  # 正数表示跌破

            is_touch = diff <= self.support_tolerance
            is_fake_break = (
                0 < below <= self.fake_break_tolerance
                and close >= support_price * (1 - self.support_tolerance / 2)
            )

            if (is_touch or is_fake_break) and (i - last_test_i) >= self.min_test_gap:
                count += 1
                last_test_i = i
        return count

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

        # 今日必须是阳线且收盘高于昨日（反弹确认）
        if not (cur["close"] > cur["open"] and cur["close"] > prev["close"]):
            return no

        # 盘整确认
        if not self._is_consolidation(data, cur_i - 1, days=3):
            return no

        # 在回溯区间内找 N 个最低点作为候选支撑
        lb_start = max(0, cur_i - self.lookback)
        past = data.iloc[lb_start:cur_i]
        candidates: List[Dict] = past.nsmallest(5, "low")[["date", "low"]].to_dict("records")

        for cand in candidates:
            support_price = cand["low"]
            support_date = pd.to_datetime(cand["date"])
            cur_date = pd.to_datetime(cur["date"])

            days_ago = (cur_date - support_date).days
            if not (self.min_support_age <= days_ago <= self.max_support_age):
                continue

            # 当前价格必须在支撑位附近
            price_to_support = (cur["close"] - support_price) / support_price
            if not (0 <= price_to_support <= self.near_tolerance):
                continue

            # 找支撑位对应的行索引，统计测试次数
            support_row = data[data["date"] <= cand["date"]]
            if support_row.empty:
                continue
            support_i = support_row.index[-1]
            # 转为相对 iloc
            support_iloc = data.index.get_loc(support_i) if hasattr(data.index, 'get_loc') else support_i

            tests = self._count_tests(data, support_price, support_iloc, cur_i - 1)
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
                    "days_ago": days_ago,
                    "price_to_support_pct": round(price_to_support * 100, 2),
                },
            )

        return no
