"""
滑点控制系统

提供滑点估计、控制和优化功能。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class SlippageType(Enum):
    """滑点类型"""
    FIXED = "fixed"                    # 固定滑点
    PERCENTAGE = "percentage"          # 百分比滑点
    VOLATILITY_BASED = "volatility"    # 基于波动率的滑点
    VOLUME_BASED = "volume"            # 基于成交量的滑点
    SPREAD_BASED = "spread"            # 基于买卖价的滑点


@dataclass
class SlippageEstimate:
    """滑点估计结果"""
    estimated_slippage: float          # 估计滑点金额
    slippage_pct: float                # 滑点百分比
    confidence: float                  # 置信度
    factors: Dict[str, float]          # 影响因素


class SlippageModel:
    """
    滑点模型基类
    """

    def __init__(self, slippage_type: SlippageType):
        self.slippage_type = slippage_type

    def estimate(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """
        估计滑点

        Args:
            price: 目标价格
            volume: 交易量
            market_data: 市场数据

        Returns:
            滑点估计结果
        """
        raise NotImplementedError


class FixedSlippageModel(SlippageModel):
    """
    固定滑点模型
    """

    def __init__(self, fixed_amount: float = 0.01):
        """
        初始化固定滑点模型

        Args:
            fixed_amount: 固定滑点金额（元）
        """
        super().__init__(SlippageType.FIXED)
        self.fixed_amount = fixed_amount

    def estimate(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """估计固定滑点"""
        slippage_pct = self.fixed_amount / price

        return SlippageEstimate(
            estimated_slippage=self.fixed_amount,
            slippage_pct=slippage_pct,
            confidence=0.9,
            factors={'fixed_amount': self.fixed_amount}
        )


class PercentageSlippageModel(SlippageModel):
    """
    百分比滑点模型
    """

    def __init__(self, base_slippage_pct: float = 0.0005):
        """
        初始化百分比滑点模型

        Args:
            base_slippage_pct: 基础滑点百分比（默认0.05%）
        """
        super().__init__(SlippageType.PERCENTAGE)
        self.base_slippage_pct = base_slippage_pct

    def estimate(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """估计百分比滑点"""
        slippage_amount = price * self.base_slippage_pct

        return SlippageEstimate(
            estimated_slippage=slippage_amount,
            slippage_pct=self.base_slippage_pct,
            confidence=0.85,
            factors={'base_slippage_pct': self.base_slippage_pct}
        )


class VolatilitySlippageModel(SlippageModel):
    """
    基于波动率的滑点模型

    波动率越高，滑点越大。
    """

    def __init__(
        self,
        base_slippage_pct: float = 0.0003,
        volatility_multiplier: float = 2.0
    ):
        """
        初始化波动率滑点模型

        Args:
            base_slippage_pct: 基础滑点百分比
            volatility_multiplier: 波动率乘数
        """
        super().__init__(SlippageType.VOLATILITY_BASED)
        self.base_slippage_pct = base_slippage_pct
        self.volatility_multiplier = volatility_multiplier

    def estimate(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """估计基于波动率的滑点"""
        # 计算波动率
        if 'close' in market_data.columns and len(market_data) >= 20:
            returns = market_data['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)  # 年化波动率
        else:
            volatility = 0.2  # 默认20%波动率

        # 计算滑点
        slippage_pct = self.base_slippage_pct * (
            1 + self.volatility_multiplier * volatility
        )
        slippage_amount = price * slippage_pct

        return SlippageEstimate(
            estimated_slippage=slippage_amount,
            slippage_pct=slippage_pct,
            confidence=max(0.7, 1 - volatility),
            factors={
                'volatility': volatility,
                'base_slippage_pct': self.base_slippage_pct
            }
        )


class VolumeSlippageModel(SlippageModel):
    """
    基于成交量的滑点模型

    交易量占成交量比例越大，滑点越大。
    """

    def __init__(
        self,
        base_slippage_pct: float = 0.0002,
        volume_impact_factor: float = 0.1
    ):
        """
        初始化成交量滑点模型

        Args:
            base_slippage_pct: 基础滑点百分比
            volume_impact_factor: 成交量影响因子
        """
        super().__init__(SlippageType.VOLUME_BASED)
        self.base_slippage_pct = base_slippage_pct
        self.volume_impact_factor = volume_impact_factor

    def estimate(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """估计基于成交量的滑点"""
        # 获取平均成交量
        if 'volume' in market_data.columns and len(market_data) >= 20:
            avg_volume = market_data['volume'].mean()
        else:
            avg_volume = volume * 10  # 假设平均成交量是订单量的10倍

        # 计算成交量占比
        volume_ratio = volume / (avg_volume + 1e-6)

        # 计算滑点
        slippage_pct = self.base_slippage_pct * (
            1 + self.volume_impact_factor * volume_ratio
        )
        slippage_amount = price * slippage_pct

        # 置信度与成交量占比负相关
        confidence = max(0.5, 1 - volume_ratio)

        return SlippageEstimate(
            estimated_slippage=slippage_amount,
            slippage_pct=slippage_pct,
            confidence=confidence,
            factors={
                'volume_ratio': volume_ratio,
                'avg_volume': avg_volume,
                'base_slippage_pct': self.base_slippage_pct
            }
        )


class CompositeSlippageModel(SlippageModel):
    """
    综合滑点模型

    结合多种因素估计滑点。
    """

    def __init__(
        self,
        base_slippage_pct: float = 0.0003,
        volatility_weight: float = 0.3,
        volume_weight: float = 0.3,
        spread_weight: float = 0.4
    ):
        """
        初始化综合滑点模型

        Args:
            base_slippage_pct: 基础滑点百分比
            volatility_weight: 波动率权重
            volume_weight: 成交量权重
            spread_weight: 买卖价差权重
        """
        super().__init__(SlippageType.SPREAD_BASED)
        self.base_slippage_pct = base_slippage_pct
        self.volatility_weight = volatility_weight
        self.volume_weight = volume_weight
        self.spread_weight = spread_weight

    def estimate(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """估计综合滑点"""
        factors = {}

        # 波动率因子
        if 'close' in market_data.columns and len(market_data) >= 20:
            returns = market_data['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)
        else:
            volatility = 0.2
        factors['volatility'] = volatility

        # 成交量因子
        if 'volume' in market_data.columns and len(market_data) >= 20:
            avg_volume = market_data['volume'].mean()
            volume_ratio = volume / (avg_volume + 1e-6)
        else:
            volume_ratio = 0.1
        factors['volume_ratio'] = volume_ratio

        # 买卖价差因子
        if 'high' in market_data.columns and 'low' in market_data.columns:
            spread = (market_data['high'].iloc[-1] - market_data['low'].iloc[-1]) / price
        else:
            spread = 0.001
        factors['spread'] = spread

        # 计算加权滑点
        slippage_pct = self.base_slippage_pct * (
            1 +
            self.volatility_weight * volatility +
            self.volume_weight * volume_ratio * 10 +
            self.spread_weight * spread * 100
        )

        # 限制滑点上限
        slippage_pct = min(slippage_pct, 0.01)  # 最大1%

        slippage_amount = price * slippage_pct

        # 综合置信度
        confidence = max(0.5, 1 - (volatility * 0.3 + volume_ratio * 0.3))

        return SlippageEstimate(
            estimated_slippage=slippage_amount,
            slippage_pct=slippage_pct,
            confidence=confidence,
            factors=factors
        )


class SlippageController:
    """
    滑点控制器

    管理滑点估计和控制策略。
    """

    def __init__(
        self,
        model: Optional[SlippageModel] = None,
        max_slippage_pct: float = 0.005,  # 最大0.5%
        target_slippage_pct: float = 0.0005  # 目标0.05%
    ):
        """
        初始化滑点控制器

        Args:
            model: 滑点模型，None则使用综合模型
            max_slippage_pct: 最大允许滑点百分比
            target_slippage_pct: 目标滑点百分比
        """
        self.model = model or CompositeSlippageModel()
        self.max_slippage_pct = max_slippage_pct
        self.target_slippage_pct = target_slippage_pct

        # 滑点统计
        self.slippage_history: List[Dict] = []

    def estimate_slippage(
        self,
        price: float,
        volume: float,
        market_data: pd.DataFrame,
        **kwargs
    ) -> SlippageEstimate:
        """
        估计滑点

        Args:
            price: 目标价格
            volume: 交易量
            market_data: 市场数据

        Returns:
            滑点估计结果
        """
        return self.model.estimate(price, volume, market_data, **kwargs)

    def check_slippage_acceptable(
        self,
        estimated_slippage_pct: float
    ) -> Tuple[bool, str]:
        """
        检查滑点是否可接受

        Args:
            estimated_slippage_pct: 估计滑点百分比

        Returns:
            (是否可接受, 原因)
        """
        if estimated_slippage_pct > self.max_slippage_pct:
            return False, f"滑点{estimated_slippage_pct:.4%}超过最大限制{self.max_slippage_pct:.4%}"

        if estimated_slippage_pct > self.target_slippage_pct * 2:
            return True, f"滑点{estimated_slippage_pct:.4%}较高，建议谨慎"

        return True, f"滑点{estimated_slippage_pct:.4%}在合理范围内"

    def adjust_order_size(
        self,
        target_volume: float,
        price: float,
        market_data: pd.DataFrame
    ) -> Tuple[float, SlippageEstimate]:
        """
        调整订单大小以控制滑点

        Args:
            target_volume: 目标交易量
            price: 目标价格
            market_data: 市场数据

        Returns:
            (调整后交易量, 滑点估计)
        """
        # 估计当前滑点
        estimate = self.estimate_slippage(price, target_volume, market_data)

        # 如果滑点可接受，直接返回
        is_acceptable, _ = self.check_slippage_acceptable(estimate.slippage_pct)
        if is_acceptable:
            return target_volume, estimate

        # 逐步减小订单量直到滑点可接受
        adjusted_volume = target_volume
        for reduction in [0.8, 0.6, 0.4, 0.2]:
            adjusted_volume = target_volume * reduction
            estimate = self.estimate_slippage(price, adjusted_volume, market_data)
            is_acceptable, _ = self.check_slippage_acceptable(estimate.slippage_pct)
            if is_acceptable:
                break

        return adjusted_volume, estimate

    def record_actual_slippage(
        self,
        expected_price: float,
        actual_price: float,
        volume: float,
        timestamp: datetime
    ) -> None:
        """
        记录实际滑点

        Args:
            expected_price: 预期价格
            actual_price: 实际成交价格
            volume: 成交量
            timestamp: 时间戳
        """
        slippage_pct = abs(actual_price - expected_price) / expected_price

        self.slippage_history.append({
            'timestamp': timestamp,
            'expected_price': expected_price,
            'actual_price': actual_price,
            'volume': volume,
            'slippage_pct': slippage_pct
        })

    def get_slippage_statistics(self) -> Dict[str, float]:
        """
        获取滑点统计

        Returns:
            滑点统计信息
        """
        if not self.slippage_history:
            return {
                'mean_slippage_pct': 0,
                'median_slippage_pct': 0,
                'max_slippage_pct': 0,
                'min_slippage_pct': 0
            }

        slippages = [s['slippage_pct'] for s in self.slippage_history]

        return {
            'mean_slippage_pct': np.mean(slippages),
            'median_slippage_pct': np.median(slippages),
            'max_slippage_pct': np.max(slippages),
            'min_slippage_pct': np.min(slippages),
            'std_slippage_pct': np.std(slippages),
            'sample_count': len(slippages)
        }

    def generate_report(self) -> str:
        """
        生成滑点控制报告

        Returns:
            报告文本
        """
        stats = self.get_slippage_statistics()

        lines = []
        lines.append("=" * 60)
        lines.append("滑点控制报告")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"目标滑点: {self.target_slippage_pct:.4%}")
        lines.append(f"最大滑点: {self.max_slippage_pct:.4%}")
        lines.append("")
        lines.append("【实际滑点统计】")
        lines.append(f"  平均滑点: {stats['mean_slippage_pct']:.4%}")
        lines.append(f"  中位数滑点: {stats['median_slippage_pct']:.4%}")
        lines.append(f"  最大滑点: {stats['max_slippage_pct']:.4%}")
        lines.append(f"  最小滑点: {stats['min_slippage_pct']:.4%}")
        lines.append(f"  样本数量: {stats['sample_count']}")
        lines.append("")

        # 评估滑点控制效果
        if stats['mean_slippage_pct'] <= self.target_slippage_pct:
            lines.append("✅ 滑点控制良好，平均滑点低于目标")
        elif stats['mean_slippage_pct'] <= self.max_slippage_pct:
            lines.append("⚠️ 滑点偏高，建议优化执行策略")
        else:
            lines.append("🚨 滑点过高，需要立即调整")

        return "\n".join(lines)
