"""
策略集合模块

提供各种量化交易策略实现
"""

from .template import StrategyTemplate, StrategyConfig
from .moving_average_strategy import MovingAverageStrategy
from .momentum_strategy import MultiFactorMomentumStrategy, MomentumFactor
from .breakout_strategy import BreakoutStrategy, BreakoutType, BreakoutFilter
from .mean_reversion_strategy import (
    StatisticalArbitrageStrategy,
    PairsTradingStrategy,
    VolatilityMeanReversionStrategy,
    MeanReversionConfig,
)
from .ml_strategy import (
    PricePredictionStrategy,
    ClassificationStrategy,
    RLStrategyFramework,
    MLStrategyConfig,
    FeatureEngineer,
)
from .event_driven_strategy import (
    EarningsEventStrategy,
    CapitalFlowEventStrategy,
    DragonTigerEventStrategy,
    EventDrivenConfig,
)
from .portfolio_strategy import (
    RiskParityStrategy,
    FactorRotationStrategy,
    SmartAssetAllocationStrategy,
    PortfolioConfig,
)

__all__ = [
    "StrategyTemplate",
    "StrategyConfig",
    "MovingAverageStrategy",
    "MultiFactorMomentumStrategy",
    "MomentumFactor",
    "BreakoutStrategy",
    "BreakoutType",
    "BreakoutFilter",
    "StatisticalArbitrageStrategy",
    "PairsTradingStrategy",
    "VolatilityMeanReversionStrategy",
    "MeanReversionConfig",
    "PricePredictionStrategy",
    "ClassificationStrategy",
    "RLStrategyFramework",
    "MLStrategyConfig",
    "FeatureEngineer",
    "EarningsEventStrategy",
    "CapitalFlowEventStrategy",
    "DragonTigerEventStrategy",
    "EventDrivenConfig",
    "RiskParityStrategy",
    "FactorRotationStrategy",
    "SmartAssetAllocationStrategy",
    "PortfolioConfig",
]
