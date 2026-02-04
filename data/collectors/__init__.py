"""
数据采集器模块

提供多种数据源的采集功能
"""

from .base import DataCollector, CollectorConfig, DataSource, DataType
from .akshare_collector import AKShareCollector
from .capital_flow_collector import (
    CapitalFlowCollector,
    CapitalFlowData,
    CapitalFlowType,
    DragonTigerData
)
from .tick_collector import (
    TickCollector,
    TickData,
    TickDataType,
    TradeData,
    DepthLevel
)
from .tushare_collector import TushareCollector
from .rqdata_collector import RQDataCollector
from .fundamental_collector import FundamentalCollector
from .alternative_collector import AlternativeCollector

__all__ = [
    "DataCollector",
    "CollectorConfig",
    "DataSource",
    "DataType",
    "AKShareCollector",
    "CapitalFlowCollector",
    "CapitalFlowData",
    "CapitalFlowType",
    "DragonTigerData",
    "TickCollector",
    "TickData",
    "TickDataType",
    "TradeData",
    "DepthLevel",
    "TushareCollector",
    "RQDataCollector",
    "FundamentalCollector",
    "AlternativeCollector",
]
