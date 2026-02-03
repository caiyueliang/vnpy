"""
AlphaX 因子库模块

提供各类因子的计算、管理和评估功能。
"""

from .base import Factor, FactorRegistry
from .technical_factors import (
    MomentumFactor,
    VolatilityFactor,
    VolumeFactor,
    TrendFactor,
    MeanReversionFactor
)
from .fundamental_factors import (
    ValuationFactor,
    GrowthFactor,
    ProfitabilityFactor,
    FinancialQualityFactor
)
from .factor_evaluator import FactorEvaluator

__all__ = [
    # 基础类
    'Factor',
    'FactorRegistry',

    # 技术因子
    'MomentumFactor',
    'VolatilityFactor',
    'VolumeFactor',
    'TrendFactor',
    'MeanReversionFactor',

    # 基本面因子
    'ValuationFactor',
    'GrowthFactor',
    'ProfitabilityFactor',
    'FinancialQualityFactor',

    # 评估工具
    'FactorEvaluator',
]
