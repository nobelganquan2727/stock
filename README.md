# Stock Strategy Project

A 股核心自选池监控 — 固定 50 只票、近 2 年日线、历史低点扫描、飞书提醒。

## 当前策略

只关注自选池里的 **50 只股票**（见 `src/watchlist.py`）。

每天收盘后：

1. **增量更新**近 2 年日线（已有数据则只补新）
2. **扫描历史低点**：当日 low/close 触及或逼近窗口内最低价（默认容差 1%）
3. **飞书推送**提醒（可选附带 K 线图）

## 目录结构

```
stock/
├── src/
│   ├── watchlist.py                   # 核心 50 只自选池
│   ├── db.py                          # SQLAlchemy + MySQL
│   ├── notify.py                      # 飞书推送
│   ├── stock_symbols.py               # 旧指数成分（兼容）
│   ├── data_fetcher/                  # yfinance / akshare 抓取
│   ├── analysis/
│   │   ├── screener.py                # 自选池扫描器
│   │   └── strategies/
│   │       └── historical_low.py      # 历史低点策略（主策略）
│   └── visualizer/                    # K 线图
├── scripts/
│   ├── workflow.py                    # 抓取 → 扫描 → 飞书
│   ├── scheduler.py                   # 每晚定时（默认 18:30 北京时间）
│   ├── fetch.py                       # 仅抓取
│   ├── scan.py                        # 仅扫描
│   ├── backtest.py
│   └── chart.py
├── requirements.txt
└── .env
```

## 环境配置

```bash
pip install -r requirements.txt
```

`.env`：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=astock_data

FEISHU_APP_ID=xxx
FEISHU_APP_SECRET=xxx
FEISHU_USER_OPEN_ID=ou_xxx
```

## 使用方法

### 一键工作流（推荐）

```bash
# 抓取近 2 年 → 历史低点扫描 → 飞书
python scripts/workflow.py

# 无信号时不推飞书
python scripts/workflow.py --quiet-ok

# 跳过抓取，只扫描 + 推送
python scripts/workflow.py --skip-fetch

# 不发明细 K 线
python scripts/workflow.py --no-charts
```

### 每晚定时

**方式 A：内置调度（前台常驻）**

```bash
# 默认每天 18:30（Asia/Shanghai）执行，周末跳过
python scripts/scheduler.py

# 立即跑一轮
python scripts/scheduler.py --once

# 改到 19:00
python scripts/scheduler.py --at 19:00
```

**方式 B：系统 cron（生产推荐）**

```cron
30 18 * * 1-5 cd /path/to/stock && /path/to/python scripts/workflow.py --quiet-ok >> logs/workflow.log 2>&1
```

### 单独抓取 / 扫描

```bash
python scripts/fetch.py                  # 自选池，近 2 年
python scripts/fetch.py --workers 8
python scripts/scan.py                   # 历史低点扫描
python scripts/scan.py --top 20
```

### K 线图

```bash
python scripts/chart.py 600519.SS --days 120 --save data/charts/maotai.png
```

## 历史低点定义

- 窗口：数据库中该票最近约 **520 个交易日**（≈ 2 年）
- 历史低点 = 窗口内 `low` 的最小值
- **创历史新低**：当日 `low` 等于历史低点
- **逼近历史低点**：当日 `low` 或 `close` 距历史低点 ≤ **1%**
- 命中后推送飞书；可用 `--quiet-ok` 在无人命中时保持安静

## 自选池

完整列表在 `src/watchlist.py`，例如：长江电力、中国神华、贵州茅台、宁德时代、比亚迪、中芯国际等共 50 只。

修改自选池：编辑该文件后重新跑 `fetch` / `workflow` 即可。
