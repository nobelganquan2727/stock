#!/usr/bin/env python3
"""
选股扫描入口

用法:
    python scripts/scan.py                  # 默认：全部策略，min 1 策略
    python scripts/scan.py --min-strategies 2
    python scripts/scan.py --top 50
    python scripts/scan.py --include-etf
    python scripts/scan.py --strategy ma    # 只跑单一策略
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from db import get_engine
from analysis.screener import run_screener, print_results, save_results


def main():
    parser = argparse.ArgumentParser(description="多策略选股扫描")
    parser.add_argument("--min-strategies", type=int, default=1)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--include-etf", action="store_true")
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


if __name__ == "__main__":
    main()
