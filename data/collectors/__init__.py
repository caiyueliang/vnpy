"""
数据采集器模块

提供多种数据源的采集功能
"""

from .base import DataCollector, CollectorConfig, DataSource, DataType
from .akshare_collector import AKShareCollector

__all__ = [
    "DataCollector",
    "CollectorConfig",
    "DataSource",
    "DataType",
    "AKShareCollector",
]
