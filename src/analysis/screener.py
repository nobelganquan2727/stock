"""
综合选股扫描器

从数据库读取所有股票数据，逐一运行所有策略，
按满足策略数量 + 总分排序，输出 top N。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy import text

from db import get_engine
from analysis.strategies import (
    MAStrategy,
    ReversalCandleStrategy,
    WBottomStrategy,
    HSBottomStrategy,
    SupportBounceStrategy,
)
from analysis.strategies.base import SignalResult


LOOKBACK_DAYS = 120


@dataclass
class StockSignal:
    code: str
    date: str
    price: float
    signals: List[SignalResult] = field(default_factory=list)

    @property
    def strategy_count(self) -> int:
        return len(self.signals)

    @property
    def total_score(self) -> float:
        return sum(s.score for s in self.signals)

    @property
    def strategy_names(self) -> List[str]:
        return [s.name for s in self.signals]


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_all_codes(engine, exclude_etf: bool = True) -> List[str]:
    with engine.connect() as conn:
        if exclude_etf:
            rows = conn.execute(text(
                "SELECT DISTINCT code FROM daily_stock_data "
                "WHERE code NOT LIKE '51%.SS' AND code NOT LIKE '15%.SZ' "
                "AND code NOT LIKE '56%.SS' AND code NOT LIKE '16%.SZ'"
            ))
        else:
            rows = conn.execute(text("SELECT DISTINCT code FROM daily_stock_data"))
        return [r[0] for r in rows]


def get_stock_data(engine, code: str, n: int = LOOKBACK_DAYS) -> pd.DataFrame:
    q = text("""
        SELECT date, open, high, low, close, volume
        FROM daily_stock_data
        WHERE code = :code
        ORDER BY date DESC
        LIMIT :n
    """)
    df = pd.read_sql(q, engine, params={"code": code, "n": n})
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


# ── Screener ─────────────────────────────────────────────────────────────────

STRATEGIES = [
    MAStrategy(),
    ReversalCandleStrategy(),
    WBottomStrategy(),
    HSBottomStrategy(),
    SupportBounceStrategy(),
]


def analyze_stock(data: pd.DataFrame, code: str) -> Optional[StockSignal]:
    if len(data) < 70:
        return None

    last = data.iloc[-1]
    signal = StockSignal(
        code=code,
        date=last["date"].strftime("%Y-%m-%d"),
        price=round(last["close"], 2),
    )

    for strategy in STRATEGIES:
        try:
            result = strategy.analyze(data)
            if result.triggered:
                signal.signals.append(result)
        except Exception:
            continue

    return signal if signal.signals else None


def run_screener(
    engine=None,
    top_n: int = 50,
    exclude_etf: bool = True,
    min_strategies: int = 1,
) -> List[StockSignal]:
    if engine is None:
        engine = get_engine()

    codes = get_all_codes(engine, exclude_etf=exclude_etf)

    print(f"\n{'='*70}")
    print(f"  多策略综合选股扫描")
    print(f"  策略: {' | '.join(s.name for s in STRATEGIES)}")
    print(f"  扫描: {len(codes)} 只{'股票' if exclude_etf else '标的'}")
    print(f"{'='*70}\n")

    results: List[StockSignal] = []

    for i, code in enumerate(codes, 1):
        try:
            data = get_stock_data(engine, code)
            sig = analyze_stock(data, code)
            if sig and sig.strategy_count >= min_strategies:
                results.append(sig)
        except Exception:
            pass

        if i % 100 == 0:
            print(f"  ... {i}/{len(codes)}  发现 {len(results)} 个信号")

    results.sort(key=lambda x: (x.strategy_count, x.total_score), reverse=True)
    print(f"\n✅ 共发现 {len(results)} 个信号，返回前 {min(top_n, len(results))} 个\n")
    return results[:top_n]


def print_results(results: List[StockSignal], top_n: int = 30) -> None:
    if not results:
        print("❌ 未找到任何信号。")
        return

    print(f"\n{'='*70}")
    print(f"  选股结果 (前 {min(top_n, len(results))} 名)")
    print(f"{'='*70}\n")

    for rank, r in enumerate(results[:top_n], 1):
        stars = "⭐" * r.strategy_count
        print(f"#{rank:<3} {r.code:<14} ¥{r.price:<8.2f}  {stars} ({r.strategy_count} 策略)")
        print(f"      {' | '.join(r.strategy_names)}")
        for sig in r.signals:
            d = sig.details
            if "pattern" in d:
                print(f"      → {d['pattern']}  趋势={d.get('trend','')}  MA5/20={d.get('dist_pct','')}%")
            elif "engulfing" in d:
                print(f"      → 连跌 {d.get('down_days')}天 {d.get('total_decline_pct')}%  量比×{d.get('volume_ratio')}")
            elif "neckline" in d:
                print(f"      → 颈线={d.get('neckline')}  深度={d.get('depth_pct','')}%  突破={d.get('breakout_pct','')}%")
            elif "support_price" in d:
                print(f"      → 支撑={d.get('support_price')}  测试{d.get('test_count')}次  距今{d.get('days_ago')}天")
        print()


def save_results(results: List[StockSignal], output_dir: str = ".") -> str:
    if not results:
        return ""
    today = datetime.now().strftime("%Y%m%d")
    rows = []
    for i, r in enumerate(results):
        rows.append({
            "rank": i + 1,
            "code": r.code,
            "date": r.date,
            "price": r.price,
            "strategy_count": r.strategy_count,
            "strategies": " | ".join(r.strategy_names),
            "total_score": round(r.total_score, 2),
        })
    path = os.path.join(output_dir, f"stock_picks_{today}.csv")
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"💾 结果已保存: {path}")
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="多策略综合选股")
    parser.add_argument("--min-strategies", type=int, default=1, help="最少满足策略数")
    parser.add_argument("--top", type=int, default=30, help="显示前 N 个")
    parser.add_argument("--include-etf", action="store_true", help="包含 ETF")
    args = parser.parse_args()

    engine = get_engine()
    results = run_screener(
        engine=engine,
        top_n=args.top,
        exclude_etf=not args.include_etf,
        min_strategies=args.min_strategies,
    )
    print_results(results, top_n=args.top)
    save_results(results)
