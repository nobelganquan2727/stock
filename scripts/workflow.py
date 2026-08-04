#!/usr/bin/env python3
"""
完整工作流（核心自选池）：
1. 增量抓取近 2 年日线入库
2. 扫描历史低点
3. 结果推送到飞书
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
from datetime import datetime, timedelta

from db import get_engine, init_db
from data_fetcher import run_fetch_job
from watchlist import get_watchlist_codes, get_stock_name
from analysis.screener import run_screener
from notify import send_message, send_image
from visualizer import plot_candlestick


CHART_DIR = os.path.join("data", "charts")
# 约 2 年：按日历日回退，抓取侧会按交易日落库
DEFAULT_START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")


def run_fetch(engine, workers: int = 4, start: str = DEFAULT_START):
    print("=" * 60)
    print("  Step 1: 核心自选池数据抓取（近 2 年）")
    print("=" * 60)
    init_db(engine)

    codes = get_watchlist_codes()
    print(f"自选池: {len(codes)} 只  起始日: {start}")

    if not codes:
        print("没有任何代码，跳过抓取。")
        return

    run_fetch_job(engine, codes, max_workers=workers, default_start=start)
    print("\n✅ 数据抓取完成！")


def format_screener_results(results, top_n=50):
    today = datetime.now().strftime("%Y-%m-%d")
    if not results:
        return (
            f"📉 历史低点监控 ({today})\n"
            f"核心自选池 50 只今日无人触及近 2 年历史低点。"
        )

    lines = [
        f"📉 历史低点提醒 ({today})",
        f"共 {len(results)} 只触及/逼近近 2 年历史低点：\n",
    ]

    for rank, r in enumerate(results[:top_n], 1):
        name = r.name or get_stock_name(r.code)
        detail = r.signals[0].details if r.signals else {}
        pattern = detail.get("pattern", "历史低点")
        hist_low = detail.get("hist_low", "-")
        dist = detail.get("dist_pct", "-")
        flag = "🔥" if detail.get("is_new_low") else "⚠️"
        lines.append(
            f"{flag}#{rank} {name}({r.code}) ¥{r.price}\n"
            f"   {pattern} | 历史低 ¥{hist_low} | 距低点 {dist}%"
        )

    return "\n".join(lines)


def clear_chart_dir():
    os.makedirs(CHART_DIR, exist_ok=True)
    for name in os.listdir(CHART_DIR):
        path = os.path.join(CHART_DIR, name)
        if os.isfile(path):
            os.remove(path)


def send_result_charts(results, engine, top_n=10, days=120):
    if not results:
        return

    for rank, result in enumerate(results[:top_n], 1):
        end_date = result.date
        start_date = (
            datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days)
        ).strftime("%Y-%m-%d")
        chart_path = os.path.join(
            CHART_DIR,
            f"{rank:02d}_{result.code.replace('.', '_')}_{end_date}.png",
        )

        try:
            plot_candlestick(
                code=result.code,
                start_date=start_date,
                end_date=end_date,
                engine=engine,
                moving_averages=(5, 10, 20),
                savefig=chart_path,
            )
            send_image(chart_path)
        except Exception as e:
            print(f"[chart] {result.code} 生成或发送失败: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="核心自选池工作流: 抓取(2年) -> 历史低点扫描 -> 飞书通知"
    )
    parser.add_argument("--skip-fetch", action="store_true", help="跳过抓取数据步骤")
    parser.add_argument("--top", type=int, default=50, help="最多发送多少个结果到飞书")
    parser.add_argument("--no-charts", action="store_true", help="不发送 K 线图")
    parser.add_argument("--chart-days", type=int, default=120, help="K 线图展示最近 N 天")
    parser.add_argument("--workers", type=int, default=4, help="抓取并发数")
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help=f"无历史数据时的起始日（默认近2年: {DEFAULT_START}）",
    )
    parser.add_argument(
        "--quiet-ok",
        action="store_true",
        help="无信号时不推送飞书（有信号仍推送）",
    )
    args = parser.parse_args()

    clear_chart_dir()
    engine = get_engine()

    if not args.skip_fetch:
        run_fetch(engine, workers=args.workers, start=args.start)
    else:
        print("⚠️ 跳过数据抓取步骤")

    print("\n" + "=" * 60)
    print("  Step 2: 历史低点扫描")
    print("=" * 60)
    results = run_screener(
        engine=engine,
        top_n=args.top,
        exclude_etf=True,
        min_strategies=1,
    )

    print("\n" + "=" * 60)
    print("  Step 3: 发送结果到飞书")
    print("=" * 60)

    msg_text = format_screener_results(results, top_n=args.top)
    print(msg_text)

    if results or not args.quiet_ok:
        send_message(msg_text)
        if results and not args.no_charts:
            send_result_charts(
                results, engine=engine, top_n=min(args.top, 10), days=args.chart_days
            )
    else:
        print("（--quiet-ok：无信号，跳过飞书推送）")


if __name__ == "__main__":
    main()
