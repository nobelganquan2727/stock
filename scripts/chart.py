#!/usr/bin/env python3
"""
画 K 线图入口

用法:
    python scripts/chart.py 600519.SS
    python scripts/chart.py 600519.SS --days 90
    python scripts/chart.py 600519.SS --start 2025-01-01 --end 2025-06-01
    python scripts/chart.py 600519.SS --save charts/maotai.png
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from datetime import datetime, timedelta
from db import get_engine
from visualizer import plot_candlestick


def main():
    parser = argparse.ArgumentParser(description="绘制 K 线图")
    parser.add_argument("code", help="股票代码，如 600519.SS 或 600519（自动补后缀）")
    parser.add_argument("--days", type=int, default=60, help="最近 N 天（默认 60）")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD（优先于 --days）")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--save", help="保存路径（默认弹窗显示）")
    parser.add_argument("--ma", default="5,10,20", help="均线周期，逗号分隔（默认 5,10,20）")
    args = parser.parse_args()

    # 自动补后缀
    code = args.code
    if "." not in code:
        code = f"{code}.SS" if code.startswith("6") or code.startswith("688") else f"{code}.SZ"

    end_date = args.end or datetime.now().strftime("%Y-%m-%d")
    if args.start:
        start_date = args.start
    else:
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=args.days)).strftime("%Y-%m-%d")

    mas = tuple(int(x) for x in args.ma.split(",")) if args.ma else None

    # 自动创建保存目录
    savefig = args.save
    if savefig:
        os.makedirs(os.path.dirname(savefig) if os.path.dirname(savefig) else ".", exist_ok=True)

    engine = get_engine()
    plot_candlestick(code=code, start_date=start_date, end_date=end_date,
                     engine=engine, moving_averages=mas, savefig=savefig)


if __name__ == "__main__":
    main()
