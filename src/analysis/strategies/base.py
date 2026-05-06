from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict
import pandas as pd


@dataclass
class SignalResult:
    """每个策略 analyze() 的统一返回格式"""
    triggered: bool
    name: str           # 信号名称，如 'MA金叉反转'
    score: float        # 置信度 0.0 ~ 1.0
    details: Dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    所有策略的抽象基类。

    输入 DataFrame 必须包含列: [date, open, high, low, close, volume]
    按日期升序排列，建议至少 70 行。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass

    @abstractmethod
    def analyze(self, data: pd.DataFrame) -> SignalResult:
        """
        分析股票数据，返回 SignalResult。
        data: 按日期升序排列的 OHLCV DataFrame
        """
        pass
