"""
策略集合模块

提供各种量化交易策略实现
"""

from .template import StrategyTemplate, StrategyConfig
from .moving_average_strategy import MovingAverageStrategy

__all__ = [
    "StrategyTemplate",
    "StrategyConfig",
    "MovingAverageStrategy",
]
