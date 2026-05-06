"""
数据抓取模块

从 yfinance / akshare 拉取历史 OHLCV 数据，写入 MySQL。
支持增量更新（从 DB 最新日期续拉）。
"""

import time
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod


class BaseStockFetcher(ABC):
    """数据抓取器抽象基类"""

    @abstractmethod
    def fetch(self, code: str, start_date: str, end_date: str, retries: int = 3) -> pd.DataFrame:
        """
        拉取股票数据。

        Returns DataFrame with columns:
            [date, code, open, close, high, low, volume, percentage]
        """
        pass


class YFinanceFetcher(BaseStockFetcher):
    """使用 yfinance 拉取数据"""

    def fetch(self, code: str, start_date: str, end_date: str, retries: int = 3) -> pd.DataFrame:
        import yfinance as yf

        # 多取 7 天以便计算第一行的 pct_change
        actual_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        requested_start = datetime.strptime(start_date, "%Y-%m-%d").date()

        for attempt in range(retries):
            try:
                df = yf.Ticker(code).history(start=actual_start, end=end_date)
                if df.empty:
                    return pd.DataFrame()

                df = df.reset_index()
                df["date"] = df["Date"].dt.date if "Date" in df.columns else df["Datetime"].dt.date
                df["code"] = code
                df = df.rename(columns={"Open": "open", "Close": "close", "High": "high", "Low": "low", "Volume": "volume"})
                df["percentage"] = df["close"].pct_change() * 100
                df = df[df["date"] >= requested_start]

                cols = ["date", "code", "open", "close", "high", "low", "volume", "percentage"]
                return df[[c for c in cols if c in df.columns]]

            except Exception as e:
                print(f"[YFinance] {code} attempt {attempt+1}/{retries}: {e}")
                if attempt < retries - 1:
                    time.sleep(2)

        return pd.DataFrame()


class AkShareFetcher(BaseStockFetcher):
    """使用 akshare 拉取 A 股数据（前复权）"""

    def fetch(self, code: str, start_date: str, end_date: str, retries: int = 3) -> pd.DataFrame:
        import akshare as ak

        actual_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y%m%d")
        actual_end = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y%m%d")
        requested_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        symbol = code.split(".")[0]

        for attempt in range(retries):
            try:
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=actual_start, end_date=actual_end, adjust="qfq")
                if df is None or df.empty:
                    return pd.DataFrame()

                df["date"] = pd.to_datetime(df["日期"]).dt.date
                df["code"] = code
                df = df.rename(columns={"开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume"})
                df["volume"] = df["volume"] * 100  # akshare 单位是手
                df["percentage"] = df["close"].pct_change() * 100
                df = df[df["date"] >= requested_start]

                cols = ["date", "code", "open", "close", "high", "low", "volume", "percentage"]
                return df[[c for c in cols if c in df.columns]]

            except Exception as e:
                print(f"[AkShare] {code} attempt {attempt+1}/{retries}: {e}")
                if attempt < retries - 1:
                    time.sleep(2)

        return pd.DataFrame()


# ── 并发抓取 + 写库 ────────────────────────────────────────────────────────────

def _fetch_and_upsert(fetcher: BaseStockFetcher, engine, code: str, end_date: str, default_start: str):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from db import get_latest_date, upsert_stock_data

    latest = get_latest_date(engine, code)
    start = latest.strftime("%Y-%m-%d") if latest else default_start

    print(f"[{code}] {start} → {end_date}")
    df = fetcher.fetch(code, start_date=start, end_date=end_date)
    if not df.empty:
        upsert_stock_data(engine, df)
        print(f"[{code}] ✓ {len(df)} 条")
    else:
        print(f"[{code}] 无新数据")
    time.sleep(0.3)


def run_fetch_job(
    engine,
    codes: list,
    max_workers: int = 4,
    fetcher_type: str = "yfinance",
    default_start: str = "2025-01-01",
):
    """并发抓取多只股票并写入 DB"""
    end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    fetcher = YFinanceFetcher() if fetcher_type == "yfinance" else AkShareFetcher()
    print(f"Fetcher: {fetcher.__class__.__name__}  end_date={end_date}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_and_upsert, fetcher, engine, code, end_date, default_start): code
            for code in codes
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[{code}] ERROR: {e}")
