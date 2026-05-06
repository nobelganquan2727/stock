#!/usr/bin/env python3
"""
回测入口

用法:
    python scripts/backtest.py --strategy ma
    python scripts/backtest.py --strategy reversal --stop-loss 0.07 --take-profit 0.20
    python scripts/backtest.py --strategy support --max-stocks 100   # 快速测试
    
可选策略: ma | reversal | w_bottom | hs_bottom | support
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from db import get_engine
from analysis.backtest import run_backtest, print_backtest_summary, save_backtest
from analysis.strategies import (
    MAStrategy, ReversalCandleStrategy,
    WBottomStrategy, HSBottomStrategy, SupportBounceStrategy,
)

STRATEGY_MAP = {
    "ma": MAStrategy(),
    "reversal": ReversalCandleStrategy(),
    "w_bottom": WBottomStrategy(),
    "hs_bottom": HSBottomStrategy(),
    "support": SupportBounceStrategy(),
}


def main():
    parser = argparse.ArgumentParser(description="策略回测")
    parser.add_argument("--strategy", choices=STRATEGY_MAP.keys(), default="ma")
    parser.add_argument("--stop-loss", type=float, default=0.05, help="止损比例 (默认 0.05)")
    parser.add_argument("--take-profit", type=float, default=0.15, help="止盈比例 (默认 0.15)")
    parser.add_argument("--max-hold", type=int, default=20, help="最长持仓天数 (默认 20)")
    parser.add_argument("--max-stocks", type=int, default=None, help="限制股票数量（调试用）")
    parser.add_argument("--include-etf", action="store_true")
    args = parser.parse_args()

    engine = get_engine()
    result = run_backtest(
        engine=engine,
        strategy=STRATEGY_MAP[args.strategy],
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
        max_hold_days=args.max_hold,
        max_stocks=args.max_stocks,
        exclude_etf=not args.include_etf,
    )
    print_backtest_summary(result)
    save_backtest(result)


if __name__ == "__main__":
    main()
