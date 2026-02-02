"""
AlphaX - A股量化交易系统
目标：一年十倍投资收益

核心模块：
- risk: 风险管理
- position: 仓位管理
- strategy: 策略框架
- evaluation: 策略评估
- backtest: 回测框架
"""

__version__ = "1.0.0"

from .risk import RiskManager, RiskLevel
from .position import PositionManager
from .evaluation import PerformanceEvaluator
from .backtest import BacktestEngine, BacktestResult
from .strategies import StrategyTemplate, MovingAverageStrategy

__all__ = [
    "RiskManager",
    "RiskLevel",
    "PositionManager",
    "PerformanceEvaluator",
    "BacktestEngine",
    "BacktestResult",
    "StrategyTemplate",
    "MovingAverageStrategy",
]
