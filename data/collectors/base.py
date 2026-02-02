"""
数据采集器基类

定义统一的数据采集接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from enum import Enum


class DataSource(Enum):
    """数据源类型"""
    RQDATA = "rqdata"           # 米筐数据
    TUSHARE = "tushare"         # Tushare
    AKSHARE = "akshare"         # AKShare
    YFINANCE = "yfinance"       # Yahoo Finance
    CCXT = "ccxt"               # 数字货币
    CUSTOM = "custom"           # 自定义


class DataType(Enum):
    """数据类型"""
    TICK = "tick"               # Tick数据
    BAR_1MIN = "1m"             # 1分钟K线
    BAR_5MIN = "5m"             # 5分钟K线
    BAR_15MIN = "15m"           # 15分钟K线
    BAR_30MIN = "30m"           # 30分钟K线
    BAR_1HOUR = "1h"            # 1小时K线
    BAR_DAILY = "d"             # 日K线
    BAR_WEEKLY = "w"            # 周K线
    BAR_MONTHLY = "m"           # 月K线


@dataclass
class CollectorConfig:
    """采集器配置"""
    source: DataSource
    api_key: str = ""
    api_secret: str = ""
    rate_limit: int = 1000      # 每分钟请求限制
    retry_times: int = 3        # 重试次数
    timeout: int = 30           # 超时时间（秒）


class DataCollector(ABC):
    """
    数据采集器基类

    所有具体采集器必须继承此类并实现抽象方法
    """

    def __init__(self, config: CollectorConfig) -> None:
        """Constructor"""
        self.config: CollectorConfig = config
        self._connected: bool = False
        self._callback: Callable | None = None

        # 统计信息
        self._requests_count: int = 0
        self._success_count: int = 0
        self._error_count: int = 0

    @abstractmethod
    def connect(self) -> bool:
        """
        连接数据源

        Returns:
            是否连接成功
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开数据源连接"""
        pass

    @abstractmethod
    def get_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """
        获取K线数据

        Args:
            vt_symbol: 合约代码
            interval: 时间周期
            start: 开始时间
            end: 结束时间

        Returns:
            K线数据列表
        """
        pass

    @abstractmethod
    def get_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """
        获取Tick数据

        Args:
            vt_symbol: 合约代码
            start: 开始时间
            end: 结束时间

        Returns:
            Tick数据列表
        """
        pass

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected

    def set_callback(self, callback: Callable) -> None:
        """
        设置数据回调函数

        Args:
            callback: 回调函数，接收数据作为参数
        """
        self._callback = callback

    def _on_data(self, data: Any) -> None:
        """触发数据回调"""
        if self._callback:
            self._callback(data)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "connected": self._connected,
            "requests": self._requests_count,
            "success": self._success_count,
            "errors": self._error_count,
            "success_rate": self._success_count / max(self._requests_count, 1),
        }
