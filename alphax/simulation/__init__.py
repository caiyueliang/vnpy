"""
模拟交易模块

提供完整的模拟交易环境，包括虚拟账户管理和撮合引擎
"""

from alphax.simulation.paper_account import (
    PaperAccount,
    PaperAccountConfig,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    OrderStatus
)

from alphax.simulation.matching_engine import (
    MatchingEngine,
    MatchConfig,
    MatchMode,
    SimulatedOrderBook,
    OrderBookLevel
)

from alphax.simulation.engine import (
    SimulationEngine,
    SimulationConfig,
    DailyTradeSummary
)

__all__ = [
    # 虚拟账户
    "PaperAccount",
    "PaperAccountConfig",
    "PaperOrder",
    "PaperPosition",
    "PaperTrade",
    "OrderStatus",
    
    # 撮合引擎
    "MatchingEngine",
    "MatchConfig",
    "MatchMode",
    "SimulatedOrderBook",
    "OrderBookLevel",
    
    # 模拟引擎
    "SimulationEngine",
    "SimulationConfig",
    "DailyTradeSummary",
]
