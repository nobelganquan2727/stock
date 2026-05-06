# Stock Strategy Project

A 股量化策略工具 — 数据抓取、多策略选股、历史回测、K 线可视化。

## 目录结构

```
stock-strategy/
├── src/
│   ├── db.py                          # SQLAlchemy ORM + MySQL 连接管理
│   ├── stock_symbols.py               # 上证50 / 沪深300 / 中证500 / ETF 代码表
│   │
│   ├── data_fetcher/
│   │   └── __init__.py                # YFinanceFetcher / AkShareFetcher + 并发抓取
│   │
│   ├── analysis/
│   │   ├── screener.py                # 综合选股扫描器（读 DB → 跑策略 → 排序输出）
│   │   ├── backtest.py                # 通用回测引擎（滑动窗口 + 止损/止盈）
│   │   └── strategies/
│   │       ├── base.py                # BaseStrategy ABC + SignalResult
│   │       ├── ma_strategy.py         # 均线策略（4 种形态）
│   │       ├── reversal_candle.py     # K 线反包策略
│   │       ├── w_bottom.py            # W 底（双底）形态
│   │       ├── hs_bottom.py           # 头肩底形态
│   │       └── support_bounce.py      # 颈线支撑反弹策略
│   │
│   └── visualizer/
│       └── __init__.py                # mplfinance K 线图（中国配色）
│
├── scripts/
│   ├── fetch.py                       # 数据抓取入口
│   ├── scan.py                        # 选股扫描入口
│   ├── backtest.py                    # 回测入口
│   └── chart.py                       # K 线图入口
│
├── data/                              # 回测输出 CSV
├── docs/                              # 策略文档
├── tests/                             # 单元测试
├── requirements.txt
└── .env                               # DB 连接配置（不入 Git）
```

## 快速开始

### 环境配置

```bash
pip install -r requirements.txt
```

`.env` 文件：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=astock_data
```

---

## 使用方法

### 1. 抓取数据

```bash
# 抓取全部股票 + ETF（增量更新）
python scripts/fetch.py

# 只抓股票，跳过 ETF
python scripts/fetch.py --no-etfs

# 调整并发数 / 自定义起始日
python scripts/fetch.py --workers 8 --start 2024-01-01
```

### 2. 选股扫描

```bash
# 运行全部策略，显示前 30 名
python scripts/scan.py

# 至少满足 2 个策略才上榜
python scripts/scan.py --min-strategies 2 --top 50

# 包含 ETF
python scripts/scan.py --include-etf
```

结果同时保存为 `stock_picks_YYYYMMDD.csv`。

### 3. 回测

```bash
# 回测均线策略（全量股票）
python scripts/backtest.py --strategy ma

# 回测 K 线反包，自定义止损/止盈
python scripts/backtest.py --strategy reversal --stop-loss 0.07 --take-profit 0.20

# 快速验证（限 100 只）
python scripts/backtest.py --strategy support --max-stocks 100
```

可选策略: `ma` | `reversal` | `w_bottom` | `hs_bottom` | `support`

结果保存为 `backtest_<策略>_YYYYMMDD.csv`。

### 4. K 线图

```bash
# 最近 60 天（默认）
python scripts/chart.py 600519.SS

# 自定义天数 / 日期范围
python scripts/chart.py 600519.SS --days 90
python scripts/chart.py 600519.SS --start 2025-01-01 --end 2025-06-01

# 保存为文件（不弹窗）
python scripts/chart.py 600519.SS --save charts/maotai.png

# 代码可以不带后缀，自动识别沪深
python scripts/chart.py 600519
```

---

## 策略说明

### MA 均线策略 (`ma_strategy.py`)

使用 MA5 / MA20，趋势由 MA60 斜率判断，包含 4 种入场形态：

| 形态 | 条件 | 评分 |
|------|------|------|
| 上升趋势回踩 | 上升趋势中 MA5 回踩 MA20 后价格回升 | 0.85 |
| 跌穿回归 | 上升趋势中 MA5 小幅跌穿 MA20 后开始收复 | 0.80 |
| 金叉反转 | 下降趋势中 MA5 由下穿越 MA20 | 0.90 |
| 超卖反弹 | 下降/横盘中 MA5 大幅低于 MA20，价格企稳 | 0.75 |

### K 线反包策略 (`reversal_candle.py`)

- 近 5 天至少 3 天收阴，累计跌幅 ≥ 5%
- 下跌过程中量能逐步放大（恐慌抛售）
- 当日阳线吞噬昨日实体，成交量 ≥ 近 10 天均量 × 1.8

### W 底形态 (`w_bottom.py`)

- 两个价格相近（差异 ≤ 3%）的局部低点，间距 10~50 根 K 线
- 底部到颈线深度 ≥ 5%
- 当前价格接近或突破颈线

### 头肩底形态 (`hs_bottom.py`)

- 三个低点：左肩 > 头（最低）< 右肩
- 两肩高度差 ≤ 6%
- 颈线由头两侧高点均值决定

### 颈线支撑反弹 (`support_bounce.py`)

- 过去 60 天内存在被 ≥ 2 次测试的支撑位（含假跌破识别）
- 当前价格在支撑位上方 5% 以内
- 近 3 天盘整（振幅 < 6%），今日阳线确认反弹

---

## 扩展新策略

所有策略都继承 `BaseStrategy`，只需实现一个方法：

```python
# src/analysis/strategies/my_strategy.py
from .base import BaseStrategy, SignalResult
import pandas as pd

class MyStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "我的策略"

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        # data: 按日期升序的 OHLCV DataFrame
        # ...
        return SignalResult(triggered=True, name=self.name, score=0.85, details={})
```

然后在 `analysis/screener.py` 的 `STRATEGIES` 列表里加上它即可。
