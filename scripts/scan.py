#!/usr/bin/env python3
"""
选股扫描入口（核心自选池 · 历史低点）

用法:
    python scripts/scan.py
    python scripts/scan.py --top 20
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from db import get_engine
from analysis.screener import run_screener, print_results, save_results


def main():
    parser = argparse.ArgumentParser(description="核心自选池 · 历史低点扫描")
    parser.add_argument("--min-strategies", type=int, default=1)
    parser.add_argument("--top", type=int, default=50)
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


if __name__ == "__main__":
    main()
