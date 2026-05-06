"""
蜡烛图可视化模块

从数据库读取 OHLCV 数据，用 mplfinance 绘制 K 线图（中国市场配色：红涨绿跌）。
"""

import pandas as pd
import mplfinance as mpf
from sqlalchemy import text


# 中国市场配色: 红涨绿跌
_CN_STYLE = mpf.make_mpf_style(
    base_mpf_style="yahoo",
    marketcolors=mpf.make_marketcolors(
        up="red", down="green",
        edge="inherit", wick="inherit", volume="inherit",
    ),
)


def plot_candlestick(
    code: str,
    start_date: str,
    end_date: str,
    engine=None,
    moving_averages: tuple = (5, 10, 20),
    savefig: str = None,
) -> None:
    """
    绘制蜡烛图。

    Parameters
    ----------
    code : str
        股票代码，如 '600519.SS'
    start_date : str
        开始日期 'YYYY-MM-DD'
    end_date : str
        结束日期 'YYYY-MM-DD'
    engine :
        SQLAlchemy engine；None 时自动创建
    moving_averages : tuple
        均线周期，如 (5, 10, 20)；None 则不画
    savefig : str
        保存路径（PNG）；None 则弹窗显示
    """
    if engine is None:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from db import get_engine
        engine = get_engine()

    q = text("""
        SELECT date, open, high, low, close, volume
        FROM daily_stock_data
        WHERE code = :code AND date >= :start AND date <= :end
        ORDER BY date ASC
    """)
    df = pd.read_sql(q, engine, params={"code": code, "start": start_date, "end": end_date})

    if df.empty:
        print(f"[visualizer] 无数据: {code}  {start_date} ~ {end_date}")
        return

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })

    print(f"[visualizer] {code}  {len(df)} 根 K 线")

    kwargs = dict(
        type="candle",
        style=_CN_STYLE,
        title=f"{code}  {start_date} → {end_date}",
        ylabel="Price",
        ylabel_lower="Volume",
        volume=True,
        figscale=1.2,
        tight_layout=True,
    )
    if moving_averages:
        kwargs["mav"] = moving_averages
    if savefig:
        kwargs["savefig"] = dict(fname=savefig, bbox_inches="tight")
        print(f"[visualizer] 图表已保存: {savefig}")

    mpf.plot(df, **kwargs)
