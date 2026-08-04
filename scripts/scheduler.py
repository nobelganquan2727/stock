#!/usr/bin/env python3
"""
每晚定时运行工作流（默认北京时间 18:30，交易日逻辑由数据源决定）。

用法:
    python scripts/scheduler.py                 # 前台常驻，到点执行
    python scripts/scheduler.py --once          # 立即跑一轮后退出
    python scripts/scheduler.py --at 19:00      # 自定义触发时间 HH:MM

也可用系统 cron（推荐生产环境）:
    30 18 * * 1-5 cd /path/to/stock && /path/to/python scripts/workflow.py --quiet-ok
"""

import sys
import os
import argparse
import subprocess
import time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOW = os.path.join(os.path.dirname(__file__), "workflow.py")
TZ_NAME = "Asia/Shanghai"


def now_shanghai() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(TZ_NAME))
    return datetime.now()


def run_workflow(extra_args=None) -> int:
    cmd = [sys.executable, WORKFLOW, "--quiet-ok"]
    if extra_args:
        cmd.extend(extra_args)
    print(f"[{now_shanghai():%Y-%m-%d %H:%M:%S}] 开始执行: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT)
    print(f"[{now_shanghai():%Y-%m-%d %H:%M:%S}] 结束，exit={proc.returncode}")
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description="每晚定时：抓取自选池 + 历史低点 + 飞书")
    parser.add_argument("--once", action="store_true", help="立即执行一次后退出")
    parser.add_argument("--at", default="18:30", help="每日触发时间 HH:MM（北京时间，默认 18:30）")
    parser.add_argument(
        "--workflow-args",
        nargs=argparse.REMAINDER,
        help="传给 workflow.py 的额外参数，写在 -- 之后",
    )
    args = parser.parse_args()

    extra = args.workflow_args or []
    if extra and extra[0] == "--":
        extra = extra[1:]

    if args.once:
        raise SystemExit(run_workflow(extra))

    try:
        hour_s, minute_s = args.at.split(":")
        target_h, target_m = int(hour_s), int(minute_s)
    except ValueError:
        print(f"无效时间格式: {args.at}，请使用 HH:MM")
        raise SystemExit(2)

    print(f"调度已启动：每天 {args.at} ({TZ_NAME}) 运行工作流。Ctrl+C 退出。")
    last_run_date = None

    while True:
        now = now_shanghai()
        today = now.date()
        if (
            now.hour == target_h
            and now.minute == target_m
            and last_run_date != today
        ):
            # 避开周末；节假日仍会尝试，无新行情时抓取为空、扫描无信号
            if now.weekday() < 5:
                run_workflow(extra)
            else:
                print(f"[{now:%Y-%m-%d %H:%M:%S}] 周末跳过")
            last_run_date = today
            time.sleep(60)
        else:
            time.sleep(20)


if __name__ == "__main__":
    main()
