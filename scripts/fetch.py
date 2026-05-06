#!/usr/bin/env python3
"""
数据抓取入口

用法:
    python scripts/fetch.py                    # 抓取全部股票 + ETF
    python scripts/fetch.py --no-etfs          # 只抓股票
    python scripts/fetch.py --workers 8        # 调整并发数
    python scripts/fetch.py --start 2024-01-01 # 自定义默认起始日
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from db import get_engine, init_db
from data_fetcher import run_fetch_job
from stock_symbols import get_all_stock_codes, get_etf_codes


def main():
    parser = argparse.ArgumentParser(description="股票数据抓取")
    parser.add_argument("--no-stocks", action="store_true", help="不抓股票")
    parser.add_argument("--no-etfs", action="store_true", help="不抓 ETF")
    parser.add_argument("--workers", type=int, default=4, help="并发数 (默认 4)")
    parser.add_argument("--start", default="2025-01-01", help="默认起始日 (默认 2025-01-01)")
    args = parser.parse_args()

    print("=" * 60)
    print("  股票数据抓取")
    print("=" * 60)

    engine = get_engine()
    init_db(engine)

    codes = []
    if not args.no_stocks:
        stock_codes = get_all_stock_codes()
        print(f"股票: {len(stock_codes)} 只")
        codes.extend(stock_codes)
    if not args.no_etfs:
        etf_codes = get_etf_codes()
        print(f"ETF:  {len(etf_codes)} 只")
        codes.extend(etf_codes)

    codes = list(set(codes))
    print(f"共计: {len(codes)} 只（去重后）\n")

    if not codes:
        print("没有任何代码，退出。")
        return

    run_fetch_job(engine, codes, max_workers=args.workers, default_start=args.start)
    print("\n✅ 抓取完成！")


if __name__ == "__main__":
    main()
