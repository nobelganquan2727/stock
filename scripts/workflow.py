#!/usr/bin/env python3
"""
完整的工作流：
1. 抓取数据存入DB
2. 运行选股扫描
3. 结果发送到飞书
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from datetime import datetime

from db import get_engine, init_db
from data_fetcher import run_fetch_job
from stock_symbols import get_all_stock_codes, get_etf_codes
from analysis.screener import run_screener
from notify import send_message

def run_fetch(engine):
    print("=" * 60)
    print("  Step 1: 股票数据抓取")
    print("=" * 60)
    init_db(engine)
    
    codes = []
    codes.extend(get_all_stock_codes())
    codes.extend(get_etf_codes())
    codes = list(set(codes))
    
    if not codes:
        print("没有任何代码，跳过抓取。")
        return

    # 默认抓取，可以适当降低并发或指定时间
    run_fetch_job(engine, codes, max_workers=4, default_start="2025-01-01")
    print("\n✅ 数据抓取完成！")

def format_screener_results(results, top_n=10):
    if not results:
        return "❌ 选股结果：未找到任何满足条件的股票。"
        
    lines = [f"📊 选股报告 ({datetime.now().strftime('%Y-%m-%d')})"]
    lines.append(f"共发现 {len(results)} 个信号，以下是前 {min(top_n, len(results))} 名：\n")
    
    for rank, r in enumerate(results[:top_n], 1):
        stars = "⭐" * r.strategy_count
        lines.append(f"#{rank} {r.code} ¥{r.price} {stars}")
        lines.append(f"策略: {' | '.join(r.strategy_names)}")
        lines.append("")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="完整工作流: 抓取 -> 选股 -> 飞书通知")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过抓取数据步骤")
    parser.add_argument("--top", type=int, default=10, help="最多发送多少个结果到飞书")
    args = parser.parse_args()

    engine = get_engine()
    
    # 1. 抓取数据
    if not args.skip_fetch:
        run_fetch(engine)
    else:
        print("⚠️ 跳过数据抓取步骤")

    # 2. 选股
    print("\n" + "=" * 60)
    print("  Step 2: 执行选股扫描")
    print("=" * 60)
    results = run_screener(
        engine=engine,
        top_n=args.top,
        exclude_etf=True,  # 默认筛选普票，排除ETF
        min_strategies=1,
    )
    
    # 3. 发送飞书
    print("\n" + "=" * 60)
    print("  Step 3: 发送结果到飞书")
    print("=" * 60)
    
    msg_text = format_screener_results(results, top_n=args.top)
    print(msg_text)
    
    send_message(msg_text)

if __name__ == "__main__":
    main()
