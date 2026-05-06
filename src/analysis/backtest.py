"""
回测引擎

对任意策略在历史数据上逐根 K 线滑动，生成信号并模拟持仓。

止损/止盈逻辑:
  - 开盘价入场（信号当日收盘触发，次日开盘以 open 价格入场）
  - 持仓中每日检查: 收盘 <= stop_loss → 止损; 收盘 >= take_profit → 止盈
  - 超过 max_hold_days 仍未触发 → 到期出场

用法示例:
    from analysis.backtest import run_backtest
    from analysis.strategies import MAStrategy

    results = run_backtest(engine, MAStrategy(), codes=['600519.SS'])
    print_backtest_summary(results)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from sqlalchemy import text

from db import get_engine
from analysis.strategies.base import BaseStrategy


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    code: str
    strategy_name: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float       # 百分比，如 5.23
    exit_reason: str        # '止盈' | '止损' | '到期'
    holding_days: int


@dataclass
class BacktestResult:
    strategy_name: str
    total_trades: int
    win_trades: int
    lose_trades: int
    win_rate: float         # 0~1
    avg_return: float       # %
    total_return: float     # %
    max_win: float
    max_loss: float
    avg_holding: float
    trades: List[Trade]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_all_codes(engine, exclude_etf: bool = True) -> List[str]:
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


def _get_data(engine, code: str) -> pd.DataFrame:
    q = text("""
        SELECT date, open, high, low, close, volume
        FROM daily_stock_data
        WHERE code = :code
        ORDER BY date ASC
    """)
    df = pd.read_sql(q, engine, params={"code": code})
    df["date"] = pd.to_datetime(df["date"])
    return df.reset_index(drop=True)


# ── 核心回测逻辑 ──────────────────────────────────────────────────────────────

def _backtest_one_stock(
    data: pd.DataFrame,
    code: str,
    strategy: BaseStrategy,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_hold_days: int,
    min_rows: int = 70,
) -> List[Trade]:
    """在单只股票的全部历史上滑动回测"""
    trades: List[Trade] = []
    n = len(data)
    i = min_rows  # 从第 min_rows 根 K 线开始

    while i < n - 1:
        window = data.iloc[:i + 1].copy()
        result = strategy.analyze(window)

        if result.triggered:
            # 次日开盘入场
            entry_i = i + 1
            entry_price = data.iloc[entry_i]["open"]
            if entry_price <= 0:
                i += 1
                continue

            stop = entry_price * (1 - stop_loss_pct)
            target = entry_price * (1 + take_profit_pct)

            exit_i = None
            exit_reason = "到期"
            for j in range(entry_i + 1, min(entry_i + max_hold_days + 1, n)):
                close = data.iloc[j]["close"]
                if close <= stop:
                    exit_i = j
                    exit_reason = "止损"
                    break
                if close >= target:
                    exit_i = j
                    exit_reason = "止盈"
                    break
            else:
                exit_i = min(entry_i + max_hold_days, n - 1)

            exit_price = data.iloc[exit_i]["close"]
            ret_pct = (exit_price - entry_price) / entry_price * 100

            trades.append(Trade(
                code=code,
                strategy_name=strategy.name,
                entry_date=data.iloc[entry_i]["date"].strftime("%Y-%m-%d"),
                exit_date=data.iloc[exit_i]["date"].strftime("%Y-%m-%d"),
                entry_price=round(entry_price, 2),
                exit_price=round(exit_price, 2),
                return_pct=round(ret_pct, 2),
                exit_reason=exit_reason,
                holding_days=exit_i - entry_i,
            ))

            # 跳过已持仓区间，避免重复信号
            i = exit_i + 1
        else:
            i += 1

    return trades


# ── 汇总统计 ──────────────────────────────────────────────────────────────────

def _summarize(strategy_name: str, trades: List[Trade]) -> BacktestResult:
    if not trades:
        return BacktestResult(
            strategy_name=strategy_name, total_trades=0,
            win_trades=0, lose_trades=0, win_rate=0.0,
            avg_return=0.0, total_return=0.0,
            max_win=0.0, max_loss=0.0, avg_holding=0.0,
            trades=[],
        )
    wins = [t for t in trades if t.return_pct > 0]
    losses = [t for t in trades if t.return_pct <= 0]
    returns = [t.return_pct for t in trades]
    return BacktestResult(
        strategy_name=strategy_name,
        total_trades=len(trades),
        win_trades=len(wins),
        lose_trades=len(losses),
        win_rate=len(wins) / len(trades),
        avg_return=sum(returns) / len(returns),
        total_return=sum(returns),
        max_win=max(returns),
        max_loss=min(returns),
        avg_holding=sum(t.holding_days for t in trades) / len(trades),
        trades=trades,
    )


# ── 公共入口 ──────────────────────────────────────────────────────────────────

def run_backtest(
    engine,
    strategy: BaseStrategy,
    codes: Optional[List[str]] = None,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.15,
    max_hold_days: int = 20,
    max_stocks: Optional[int] = None,
    exclude_etf: bool = True,
) -> BacktestResult:
    """
    对指定策略运行全量历史回测。

    Parameters
    ----------
    engine      : SQLAlchemy engine
    strategy    : BaseStrategy 子类实例
    codes       : 指定股票列表；None 则从 DB 取全量
    stop_loss_pct  : 止损比例，默认 5%
    take_profit_pct: 止盈比例，默认 15%
    max_hold_days  : 最长持仓天数，默认 20
    max_stocks     : 限制回测股票数量（调试用）
    exclude_etf    : 是否排除 ETF，默认 True
    """
    if engine is None:
        engine = get_engine()

    if codes is None:
        codes = _get_all_codes(engine, exclude_etf=exclude_etf)
    if max_stocks:
        codes = codes[:max_stocks]

    print(f"\n{'='*60}")
    print(f"  策略回测: {strategy.name}")
    print(f"  股票数量: {len(codes)}")
    print(f"  止损: {stop_loss_pct*100:.0f}%  止盈: {take_profit_pct*100:.0f}%  最长持仓: {max_hold_days}天")
    print(f"{'='*60}\n")

    all_trades: List[Trade] = []

    for idx, code in enumerate(codes, 1):
        try:
            data = _get_data(engine, code)
            if len(data) < 80:
                continue
            trades = _backtest_one_stock(
                data, code, strategy,
                stop_loss_pct, take_profit_pct, max_hold_days,
            )
            all_trades.extend(trades)
        except Exception as e:
            pass

        if idx % 100 == 0:
            print(f"  ... {idx}/{len(codes)}  累计 {len(all_trades)} 笔交易")

    result = _summarize(strategy.name, all_trades)
    return result


def print_backtest_summary(result: BacktestResult, top_n: int = 10) -> None:
    print(f"\n{'='*60}")
    print(f"  回测结果: {result.strategy_name}")
    print(f"{'='*60}")
    print(f"  总交易数:  {result.total_trades}")
    if result.total_trades == 0:
        print("  无交易记录。")
        return
    print(f"  盈利交易:  {result.win_trades}")
    print(f"  亏损交易:  {result.lose_trades}")
    print(f"  胜率:      {result.win_rate*100:.1f}%")
    print(f"  平均收益:  {result.avg_return:+.2f}%")
    print(f"  总收益:    {result.total_return:+.2f}%")
    print(f"  最大盈利:  {result.max_win:+.2f}%")
    print(f"  最大亏损:  {result.max_loss:+.2f}%")
    print(f"  平均持仓:  {result.avg_holding:.1f} 天")

    exit_counts = {}
    for t in result.trades:
        exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1
    print(f"\n  退出原因:")
    for reason, cnt in sorted(exit_counts.items(), key=lambda x: -x[1]):
        pct = cnt / result.total_trades * 100
        print(f"    {reason}: {cnt} ({pct:.1f}%)")

    print(f"\n  最佳 {top_n} 笔:")
    top = sorted(result.trades, key=lambda t: t.return_pct, reverse=True)[:top_n]
    for t in top:
        print(f"    {t.code}  {t.entry_date}→{t.exit_date}  {t.return_pct:+.2f}%  [{t.exit_reason}]")


def save_backtest(result: BacktestResult, output_dir: str = ".") -> None:
    if not result.trades:
        return
    today = datetime.now().strftime("%Y%m%d")
    name = result.strategy_name.replace("/", "_")
    path = os.path.join(output_dir, f"backtest_{name}_{today}.csv")
    rows = [
        {
            "code": t.code,
            "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "return_pct": t.return_pct,
            "exit_reason": t.exit_reason,
            "holding_days": t.holding_days,
        }
        for t in result.trades
    ]
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n💾 回测结果已保存: {path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="策略回测")
    parser.add_argument(
        "--strategy",
        choices=["ma", "reversal", "w_bottom", "hs_bottom", "support"],
        default="ma",
        help="选择策略",
    )
    parser.add_argument("--stop-loss", type=float, default=0.05)
    parser.add_argument("--take-profit", type=float, default=0.15)
    parser.add_argument("--max-hold", type=int, default=20)
    parser.add_argument("--max-stocks", type=int, default=None)
    args = parser.parse_args()

    from analysis.strategies import (
        MAStrategy, ReversalCandleStrategy, WBottomStrategy,
        HSBottomStrategy, SupportBounceStrategy,
    )

    strategy_map = {
        "ma": MAStrategy(),
        "reversal": ReversalCandleStrategy(),
        "w_bottom": WBottomStrategy(),
        "hs_bottom": HSBottomStrategy(),
        "support": SupportBounceStrategy(),
    }

    engine = get_engine()
    result = run_backtest(
        engine,
        strategy=strategy_map[args.strategy],
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
        max_hold_days=args.max_hold,
        max_stocks=args.max_stocks,
    )
    print_backtest_summary(result)
    save_backtest(result)
