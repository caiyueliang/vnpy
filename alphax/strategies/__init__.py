"""
策略集合模块

提供各种量化交易策略实现
"""

from .template import StrategyTemplate, StrategyConfig
from .moving_average_strategy import MovingAverageStrategy
from .momentum_strategy import MultiFactorMomentumStrategy, MomentumFactor
from .breakout_strategy import BreakoutStrategy, BreakoutType, BreakoutFilter

__all__ = [
    "StrategyTemplate",
    "StrategyConfig",
    "MovingAverageStrategy",
    "MultiFactorMomentumStrategy",
    "MomentumFactor",
    "BreakoutStrategy",
    "BreakoutType",
    "BreakoutFilter",
]
