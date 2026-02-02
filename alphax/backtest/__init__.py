"""
回测框架模块

提供策略回测验证功能
"""

from .engine import BacktestEngine
from .result import BacktestResult

__all__ = [
    "BacktestEngine",
    "BacktestResult",
]
