"""
综合选股扫描器

默认只扫描核心自选池（50 只），主策略为「历史低点」。
从数据库读取近 ~2 年日线，逐一跑策略，按分数排序输出。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor, as_completed

from db import get_engine
from watchlist import get_watchlist_codes, get_stock_name
from analysis.strategies import HistoricalLowStrategy
from analysis.strategies.base import SignalResult


# ~2 年交易日（含缓冲）
LOOKBACK_DAYS = 520


@dataclass
class StockSignal:
    code: str
    date: str
    price: float
    name: str = ""
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
    """当前策略只关心核心自选池；exclude_etf 保留兼容参数。"""
    del engine, exclude_etf
    return get_watchlist_codes()


def get_market_latest_date(engine):
    """获取数据库中最新的交易日，用于过滤数据断档的股票"""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(date) FROM daily_stock_data")).first()
        return pd.to_datetime(row[0]) if row and row[0] else None


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
    HistoricalLowStrategy(tolerance_pct=1.0, min_bars=120),
]


def analyze_stock(data: pd.DataFrame, code: str) -> Optional[StockSignal]:
    if len(data) < 120:
        return None

    last = data.iloc[-1]
    signal = StockSignal(
        code=code,
        name=get_stock_name(code),
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
    market_latest_date = get_market_latest_date(engine)

    print(f"\n{'='*70}")
    print(f"  核心自选池 · 历史低点扫描")
    print(f"  策略: {' | '.join(s.name for s in STRATEGIES)}")
    print(f"  扫描: {len(codes)} 只股票（近 {LOOKBACK_DAYS} 根日线）")
    if market_latest_date is not None:
        print(f"  最新交易日: {market_latest_date.strftime('%Y-%m-%d')}")
    print(f"{'='*70}\n")

    results: List[StockSignal] = []
    skipped_stale = 0
    total_codes = len(codes)

    def process_single_stock(code: str):
        try:
            data = get_stock_data(engine, code)
            if data.empty:
                return None, False

            latest_date = data.iloc[-1]["date"]
            if market_latest_date is not None and latest_date < market_latest_date:
                return None, True

            sig = analyze_stock(data, code)
            if sig and sig.strategy_count >= min_strategies:
                return sig, False
        except Exception:
            pass
        return None, False

    print("🚀 开始扫描自选池...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_single_stock, code): code for code in codes}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                sig, is_stale = future.result()
                if is_stale:
                    skipped_stale += 1
                elif sig:
                    results.append(sig)
            except Exception:
                pass

            if i % 10 == 0 or i == total_codes:
                print(f"  ... {i}/{total_codes}  发现 {len(results)} 个信号  跳过过期 {skipped_stale} 只")

    results.sort(key=lambda x: (x.strategy_count, x.total_score), reverse=True)
    if skipped_stale:
        print(f"⚠️ 跳过 {skipped_stale} 只数据不是最新交易日的标的")
    print(f"\n✅ 共发现 {len(results)} 个信号，返回前 {min(top_n, len(results))} 个\n")
    return results[:top_n]


def print_results(results: List[StockSignal], top_n: int = 30) -> None:
    if not results:
        print("❌ 未找到任何触及历史低点的股票。")
        return

    print(f"\n{'='*70}")
    print(f"  历史低点提醒 (前 {min(top_n, len(results))} 名)")
    print(f"{'='*70}\n")

    for rank, r in enumerate(results[:top_n], 1):
        name = r.name or get_stock_name(r.code)
        print(f"#{rank:<3} {r.code:<14} {name:<8} ¥{r.price:<8.2f}")
        print(f"      {' | '.join(r.strategy_names)}")
        for sig in r.signals:
            d = sig.details
            if "hist_low" in d:
                flag = "🔥新低" if d.get("is_new_low") else "逼近"
                print(
                    f"      → {d.get('pattern', flag)}  "
                    f"历史低={d.get('hist_low')} ({d.get('hist_low_date')})  "
                    f"现价={d.get('current_close')}  "
                    f"距低点={d.get('dist_pct')}%  "
                    f"窗口={d.get('lookback_days')}日"
                )
        print()


def save_results(results: List[StockSignal], output_dir: str = ".") -> str:
    if not results:
        return ""
    today = datetime.now().strftime("%Y%m%d")
    rows = []
    for i, r in enumerate(results):
        detail = r.signals[0].details if r.signals else {}
        rows.append({
            "rank": i + 1,
            "code": r.code,
            "name": r.name or get_stock_name(r.code),
            "date": r.date,
            "price": r.price,
            "strategy_count": r.strategy_count,
            "strategies": " | ".join(r.strategy_names),
            "total_score": round(r.total_score, 2),
            "hist_low": detail.get("hist_low"),
            "dist_pct": detail.get("dist_pct"),
            "is_new_low": detail.get("is_new_low"),
        })
    path = os.path.join(output_dir, f"stock_picks_{today}.csv")
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"💾 结果已保存: {path}")
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="核心自选池 · 历史低点扫描")
    parser.add_argument("--min-strategies", type=int, default=1, help="最少满足策略数")
    parser.add_argument("--top", type=int, default=50, help="显示前 N 个")
    parser.add_argument("--include-etf", action="store_true", help="兼容参数，已忽略")
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
