"""
交易执行模块

提供算法交易功能，包括TWAP、VWAP、冰山订单等，
以及交易时间控制和滑点控制功能。
"""

from alphax.execution.algo_trading import (
    # 枚举
    AlgoStatus,
    AlgoType,

    # 数据类
    AlgoOrder,
    ChildOrder,
    AlgoConfig,
    TWAPConfig,
    VWAPConfig,
    IcebergConfig,
    MarketSlice,

    # 算法类
    AlgoTemplate,
    TWAPAlgo,
    VWAPAlgo,
    IcebergAlgo,
    AlgoEngine,
)

from alphax.execution.trading_time import (
    # 枚举
    TradingSession,

    # 类
    TradingTimeController,
    TradingTimeFilter,
)

from alphax.execution.slippage_control import (
    # 枚举
    SlippageType,

    # 数据类
    SlippageEstimate,

    # 滑点模型
    SlippageModel,
    FixedSlippageModel,
    PercentageSlippageModel,
    VolatilitySlippageModel,
    VolumeSlippageModel,
    CompositeSlippageModel,

    # 控制器
    SlippageController,
)

from alphax.execution.fill_rate_optimizer import (
    # 枚举
    FillRateStatus,

    # 数据类
    OrderFillStats,
    FillRateMetrics,
    LiquidityMetrics,

    # 价格策略
    PriceImprovementStrategy,
    PassivePriceStrategy,
    AggressivePriceStrategy,
    AdaptivePriceStrategy,

    # 订单策略
    OrderSplitStrategy,
    RetryStrategy,

    # 优化器
    FillRateOptimizer,
    SmartOrderRouter,
)

__all__ = [
    # 算法交易 - 枚举
    "AlgoStatus",
    "AlgoType",

    # 算法交易 - 数据类
    "AlgoOrder",
    "ChildOrder",
    "AlgoConfig",
    "TWAPConfig",
    "VWAPConfig",
    "IcebergConfig",
    "MarketSlice",

    # 算法交易 - 算法类
    "AlgoTemplate",
    "TWAPAlgo",
    "VWAPAlgo",
    "IcebergAlgo",
    "AlgoEngine",

    # 交易时间控制
    "TradingSession",
    "TradingTimeController",
    "TradingTimeFilter",

    # 滑点控制
    "SlippageType",
    "SlippageEstimate",
    "SlippageModel",
    "FixedSlippageModel",
    "PercentageSlippageModel",
    "VolatilitySlippageModel",
    "VolumeSlippageModel",
    "CompositeSlippageModel",
    "SlippageController",

    # 成交率优化
    "FillRateStatus",
    "OrderFillStats",
    "FillRateMetrics",
    "LiquidityMetrics",
    "PriceImprovementStrategy",
    "PassivePriceStrategy",
    "AggressivePriceStrategy",
    "AdaptivePriceStrategy",
    "OrderSplitStrategy",
    "RetryStrategy",
    "FillRateOptimizer",
    "SmartOrderRouter",
]
