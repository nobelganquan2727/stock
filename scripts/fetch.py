#!/usr/bin/env python3
"""
数据抓取入口（默认：核心自选池 50 只，近 2 年）

用法:
    python scripts/fetch.py                    # 抓取自选池
    python scripts/fetch.py --workers 8        # 调整并发数
    python scripts/fetch.py --start 2024-01-01 # 自定义默认起始日
    python scripts/fetch.py --with-etfs        # 额外抓 ETF
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from datetime import datetime, timedelta
from db import get_engine, init_db
from data_fetcher import run_fetch_job
from watchlist import get_watchlist_codes
from stock_symbols import get_etf_codes


DEFAULT_START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="核心自选池数据抓取")
    parser.add_argument("--with-etfs", action="store_true", help="额外抓取 ETF")
    parser.add_argument("--workers", type=int, default=4, help="并发数 (默认 4)")
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help=f"默认起始日 (默认近2年: {DEFAULT_START})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  核心自选池数据抓取")
    print("=" * 60)

    engine = get_engine()
    init_db(engine)

    codes = get_watchlist_codes()
    print(f"自选池股票: {len(codes)} 只")

    if args.with_etfs:
        etf_codes = get_etf_codes()
        print(f"ETF:  {len(etf_codes)} 只")
        codes = list(set(codes + etf_codes))

    print(f"共计: {len(codes)} 只  起始日: {args.start}\n")

    if not codes:
        print("没有任何代码，退出。")
        return

    run_fetch_job(engine, codes, max_workers=args.workers, default_start=args.start)
    print("\n✅ 抓取完成！")


if __name__ == "__main__":
    main()
