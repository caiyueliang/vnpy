"""
成交率优化模块

实现多种策略来优化订单成交率，目标>95%
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable, Any
from enum import Enum
from collections import deque, defaultdict
import random

import numpy as np

from vnpy.trader.object import TickData, BarData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset, Exchange, OrderType, Status


class FillRateStatus(Enum):
    """成交率状态"""
    EXCELLENT = "excellent"      # >98%
    GOOD = "good"                # >95%
    ACCEPTABLE = "acceptable"    # >90%
    POOR = "poor"                # >80%
    CRITICAL = "critical"        # <80%


@dataclass
class OrderFillStats:
    """订单成交统计"""
    order_id: str
    vt_symbol: str
    direction: Direction
    order_volume: float
    filled_volume: float = 0.0
    price: float = 0.0
    order_type: OrderType = OrderType.LIMIT
    status: Status = Status.SUBMITTING
    
    # 时间记录
    submit_time: Optional[datetime] = None
    first_fill_time: Optional[datetime] = None
    complete_time: Optional[datetime] = None
    cancel_time: Optional[datetime] = None
    
    # 成交统计
    fill_times: List[datetime] = field(default_factory=list)
    fill_prices: List[float] = field(default_factory=list)
    fill_volumes: List[float] = field(default_factory=list)
    
    def get_fill_rate(self) -> float:
        """获取成交率"""
        if self.order_volume <= 0:
            return 0.0
        return self.filled_volume / self.order_volume
    
    def get_fill_time_seconds(self) -> Optional[float]:
        """获取成交耗时（秒）"""
        if not self.first_fill_time or not self.submit_time:
            return None
        return (self.first_fill_time - self.submit_time).total_seconds()
    
    def get_avg_fill_price(self) -> float:
        """获取平均成交价格"""
        if not self.fill_volumes:
            return 0.0
        total_value = sum(p * v for p, v in zip(self.fill_prices, self.fill_volumes))
        total_volume = sum(self.fill_volumes)
        return total_value / total_volume if total_volume > 0 else 0.0


@dataclass
class FillRateMetrics:
    """成交率指标"""
    timestamp: datetime
    
    # 订单统计
    total_orders: int = 0
    filled_orders: int = 0
    partial_orders: int = 0
    cancelled_orders: int = 0
    rejected_orders: int = 0
    expired_orders: int = 0
    
    # 成交统计
    total_volume: float = 0.0
    filled_volume: float = 0.0
    
    # 时间统计
    avg_fill_time_seconds: float = 0.0
    
    # 计算属性
    @property
    def fill_rate(self) -> float:
        """成交率"""
        if self.total_orders == 0:
            return 0.0
        return self.filled_orders / self.total_orders
    
    @property
    def volume_fill_rate(self) -> float:
        """成交量成交率"""
        if self.total_volume == 0:
            return 0.0
        return self.filled_volume / self.total_volume
    
    @property
    def status(self) -> FillRateStatus:
        """成交率状态"""
        rate = self.fill_rate
        if rate >= 0.98:
            return FillRateStatus.EXCELLENT
        elif rate >= 0.95:
            return FillRateStatus.GOOD
        elif rate >= 0.90:
            return FillRateStatus.ACCEPTABLE
        elif rate >= 0.80:
            return FillRateStatus.POOR
        else:
            return FillRateStatus.CRITICAL


@dataclass
class LiquidityMetrics:
    """流动性指标"""
    vt_symbol: str
    timestamp: datetime
    
    # 盘口数据
    bid_price_1: float = 0.0
    ask_price_1: float = 0.0
    bid_volume_1: float = 0.0
    ask_volume_1: float = 0.0
    
    # 深度数据
    bid_depth_5: float = 0.0
    ask_depth_5: float = 0.0
    bid_volume_5: float = 0.0
    ask_volume_5: float = 0.0
    
    # 计算属性
    @property
    def spread(self) -> float:
        """买卖价差"""
        if self.ask_price_1 > 0 and self.bid_price_1 > 0:
            return self.ask_price_1 - self.bid_price_1
        return 0.0
    
    @property
    def spread_pct(self) -> float:
        """买卖价差百分比"""
        if self.bid_price_1 > 0:
            return self.spread / self.bid_price_1
        return 0.0
    
    @property
    def mid_price(self) -> float:
        """中间价"""
        if self.ask_price_1 > 0 and self.bid_price_1 > 0:
            return (self.ask_price_1 + self.bid_price_1) / 2
        return 0.0
    
    def can_fill(self, volume: float, direction: Direction) -> bool:
        """检查是否可以成交指定数量"""
        if direction == Direction.LONG:
            return self.ask_volume_1 >= volume
        else:
            return self.bid_volume_1 >= volume
    
    def get_market_impact(self, volume: float, direction: Direction) -> float:
        """估算市场冲击成本"""
        if direction == Direction.LONG:
            available_volume = self.ask_volume_1
        else:
            available_volume = self.bid_volume_1
        
        if available_volume <= 0:
            return 0.01  # 1% 默认冲击成本
        
        # 简单的线性冲击模型
        impact_ratio = min(volume / available_volume, 5.0)
        return impact_ratio * 0.001  # 0.1% per unit ratio


class PriceImprovementStrategy(ABC):
    """价格优化策略基类"""
    
    @abstractmethod
    def adjust_price(
        self,
        base_price: float,
        direction: Direction,
        liquidity: LiquidityMetrics,
        urgency: float = 1.0
    ) -> float:
        """
        调整订单价格以提高成交概率
        
        Args:
            base_price: 基础价格
            direction: 方向
            liquidity: 流动性指标
            urgency: 紧急程度 (0-2, 越高越激进)
            
        Returns:
            调整后的价格
        """
        pass


class PassivePriceStrategy(PriceImprovementStrategy):
    """被动价格策略 - 挂更优价格等待成交"""
    
    def __init__(self, tick_offset: int = 1):
        """
        Constructor
        
        Args:
            tick_offset: 价格偏移（tick数）
        """
        self.tick_offset = tick_offset
    
    def adjust_price(
        self,
        base_price: float,
        direction: Direction,
        liquidity: LiquidityMetrics,
        urgency: float = 1.0
    ) -> float:
        """调整价格"""
        tick_size = self._estimate_tick_size(liquidity)
        offset = tick_size * self.tick_offset * urgency
        
        if direction == Direction.LONG:
            # 买入，挂更低价格
            return base_price - offset
        else:
            # 卖出，挂更高价格
            return base_price + offset
    
    def _estimate_tick_size(self, liquidity: LiquidityMetrics) -> float:
        """估算tick大小"""
        if liquidity.spread > 0:
            # A股通常最小变动单位是0.01
            return max(liquidity.spread / 5, 0.01)
        return 0.01


class AggressivePriceStrategy(PriceImprovementStrategy):
    """激进价格策略 - 主动吃单"""
    
    def __init__(self, slippage_tolerance: float = 0.001):
        """
        Constructor
        
        Args:
            slippage_tolerance: 滑点容忍度
        """
        self.slippage_tolerance = slippage_tolerance
    
    def adjust_price(
        self,
        base_price: float,
        direction: Direction,
        liquidity: LiquidityMetrics,
        urgency: float = 1.0
    ) -> float:
        """调整价格"""
        if direction == Direction.LONG:
            # 买入，使用卖一价或更激进
            price = liquidity.ask_price_1
            if urgency > 1.0:
                # 更激进，加价
                price = price * (1 + self.slippage_tolerance * (urgency - 1))
        else:
            # 卖出，使用买一价或更激进
            price = liquidity.bid_price_1
            if urgency > 1.0:
                # 更激进，降价
                price = price * (1 - self.slippage_tolerance * (urgency - 1))
        
        return price


class AdaptivePriceStrategy(PriceImprovementStrategy):
    """自适应价格策略 - 根据市场情况动态调整"""
    
    def __init__(
        self,
        passive_strategy: Optional[PassivePriceStrategy] = None,
        aggressive_strategy: Optional[AggressivePriceStrategy] = None,
        spread_threshold: float = 0.002
    ):
        """
        Constructor
        
        Args:
            passive_strategy: 被动策略
            aggressive_strategy: 激进策略
            spread_threshold: 价差阈值，超过则使用被动策略
        """
        self.passive_strategy = passive_strategy or PassivePriceStrategy()
        self.aggressive_strategy = aggressive_strategy or AggressivePriceStrategy()
        self.spread_threshold = spread_threshold
    
    def adjust_price(
        self,
        base_price: float,
        direction: Direction,
        liquidity: LiquidityMetrics,
        urgency: float = 1.0
    ) -> float:
        """根据市场情况选择策略"""
        # 价差大时，使用被动策略
        if liquidity.spread_pct > self.spread_threshold:
            return self.passive_strategy.adjust_price(base_price, direction, liquidity, urgency)
        
        # 价差小时，使用激进策略
        return self.aggressive_strategy.adjust_price(base_price, direction, liquidity, urgency)


class OrderSplitStrategy:
    """订单拆分策略"""
    
    def __init__(
        self,
        max_single_order_size: float = 100000.0,  # 最大单笔订单金额
        min_order_size: float = 100.0,             # 最小订单数量
        optimal_fill_size: float = 50000.0         # 最优单笔金额
    ):
        """
        Constructor
        
        Args:
            max_single_order_size: 最大单笔订单金额
            min_order_size: 最小订单数量
            optimal_fill_size: 最优单笔金额
        """
        self.max_single_order_size = max_single_order_size
        self.min_order_size = min_order_size
        self.optimal_fill_size = optimal_fill_size
    
    def split_order(
        self,
        total_volume: float,
        price: float,
        liquidity: Optional[LiquidityMetrics] = None
    ) -> List[float]:
        """
        拆分订单
        
        Args:
            total_volume: 总数量
            price: 价格
            liquidity: 流动性指标
            
        Returns:
            拆分后的订单数量列表
        """
        if total_volume <= 0 or price <= 0:
            return []
        
        total_value = total_volume * price
        
        # 如果总金额小于最大单笔，不拆分
        if total_value <= self.max_single_order_size:
            return [total_volume]
        
        # 根据流动性调整单笔大小
        if liquidity:
            available_volume = (liquidity.ask_volume_1 + liquidity.bid_volume_1) / 2
            optimal_volume = min(
                self.optimal_fill_size / price,
                available_volume * 0.3,  # 不超过流动性的30%
                total_volume / 3  # 至少拆成3笔
            )
        else:
            optimal_volume = self.optimal_fill_size / price
        
        optimal_volume = max(optimal_volume, self.min_order_size)
        
        # 生成拆分计划
        slices = []
        remaining = total_volume
        
        while remaining > 0:
            # 添加随机性
            variance = random.uniform(0.8, 1.2)
            slice_volume = min(optimal_volume * variance, remaining)
            slice_volume = max(slice_volume, self.min_order_size)
            
            slices.append(slice_volume)
            remaining -= slice_volume
        
        # 调整最后一笔
        if len(slices) > 1 and slices[-1] < self.min_order_size:
            slices[-2] += slices[-1]
            slices.pop()
        
        return slices


class RetryStrategy:
    """订单重试策略"""
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_interval_seconds: float = 5.0,
        price_adjustment_pct: float = 0.001
    ):
        """
        Constructor
        
        Args:
            max_retries: 最大重试次数
            retry_interval_seconds: 重试间隔（秒）
            price_adjustment_pct: 每次重试价格调整百分比
        """
        self.max_retries = max_retries
        self.retry_interval_seconds = retry_interval_seconds
        self.price_adjustment_pct = price_adjustment_pct
        
        # 重试记录
        self.retry_count: Dict[str, int] = {}
        self.last_retry_time: Dict[str, datetime] = {}
    
    def should_retry(self, order_id: str) -> bool:
        """检查是否应该重试"""
        count = self.retry_count.get(order_id, 0)
        if count >= self.max_retries:
            return False
        
        last_time = self.last_retry_time.get(order_id)
        if last_time:
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < self.retry_interval_seconds:
                return False
        
        return True
    
    def get_retry_price(
        self,
        order_id: str,
        original_price: float,
        direction: Direction
    ) -> float:
        """获取重试价格"""
        count = self.retry_count.get(order_id, 0)
        adjustment = self.price_adjustment_pct * (count + 1)
        
        if direction == Direction.LONG:
            # 买入，提高价格
            return original_price * (1 + adjustment)
        else:
            # 卖出，降低价格
            return original_price * (1 - adjustment)
    
    def record_retry(self, order_id: str) -> None:
        """记录重试"""
        self.retry_count[order_id] = self.retry_count.get(order_id, 0) + 1
        self.last_retry_time[order_id] = datetime.now()
    
    def reset(self, order_id: str) -> None:
        """重置重试计数"""
        if order_id in self.retry_count:
            del self.retry_count[order_id]
        if order_id in self.last_retry_time:
            del self.last_retry_time[order_id]


class FillRateOptimizer:
    """
    成交率优化器
    
    综合使用多种策略优化订单成交率，目标>95%
    """
    
    def __init__(
        self,
        target_fill_rate: float = 0.95,
        price_strategy: Optional[PriceImprovementStrategy] = None,
        split_strategy: Optional[OrderSplitStrategy] = None,
        retry_strategy: Optional[RetryStrategy] = None
    ):
        """
        Constructor
        
        Args:
            target_fill_rate: 目标成交率
            price_strategy: 价格优化策略
            split_strategy: 订单拆分策略
            retry_strategy: 重试策略
        """
        self.target_fill_rate = target_fill_rate
        self.price_strategy = price_strategy or AdaptivePriceStrategy()
        self.split_strategy = split_strategy or OrderSplitStrategy()
        self.retry_strategy = retry_strategy or RetryStrategy()
        
        # 订单跟踪
        self.active_orders: Dict[str, OrderFillStats] = {}
        self.order_history: deque = deque(maxlen=10000)
        
        # 流动性数据
        self.liquidity_data: Dict[str, LiquidityMetrics] = {}
        
        # 统计
        self.metrics_history: deque = deque(maxlen=1000)
        self.current_metrics = FillRateMetrics(timestamp=datetime.now())
        
        # 回调
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)
    
    def update_liquidity(self, tick: TickData) -> None:
        """更新流动性数据"""
        liquidity = LiquidityMetrics(
            vt_symbol=tick.vt_symbol,
            timestamp=tick.datetime,
            bid_price_1=tick.bid_price_1,
            ask_price_1=tick.ask_price_1,
            bid_volume_1=tick.bid_volume_1,
            ask_volume_1=tick.ask_volume_1,
        )
        
        # 计算5档深度
        bid_volume_5 = sum([
            getattr(tick, f'bid_volume_{i}', 0) or 0
            for i in range(1, 6)
        ])
        ask_volume_5 = sum([
            getattr(tick, f'ask_volume_{i}', 0) or 0
            for i in range(1, 6)
        ])
        
        liquidity.bid_volume_5 = bid_volume_5
        liquidity.ask_volume_5 = ask_volume_5
        
        self.liquidity_data[tick.vt_symbol] = liquidity
    
    def optimize_order(
        self,
        vt_symbol: str,
        direction: Direction,
        volume: float,
        base_price: float,
        order_type: OrderType = OrderType.LIMIT,
        urgency: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        优化订单执行
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            volume: 数量
            base_price: 基础价格
            order_type: 订单类型
            urgency: 紧急程度
            
        Returns:
            优化后的订单列表
        """
        # 获取流动性数据
        liquidity = self.liquidity_data.get(vt_symbol)
        
        # 拆分订单
        slices = self.split_strategy.split_order(volume, base_price, liquidity)
        
        # 生成优化后的订单
        orders = []
        for slice_volume in slices:
            # 调整价格
            if order_type == OrderType.LIMIT and liquidity:
                adjusted_price = self.price_strategy.adjust_price(
                    base_price, direction, liquidity, urgency
                )
            else:
                adjusted_price = base_price
            
            orders.append({
                "vt_symbol": vt_symbol,
                "direction": direction,
                "volume": slice_volume,
                "price": adjusted_price,
                "order_type": order_type,
            })
        
        return orders
    
    def on_order_submitted(self, order: OrderData) -> None:
        """订单提交回调"""
        stats = OrderFillStats(
            order_id=order.orderid,
            vt_symbol=order.vt_symbol,
            direction=order.direction,
            order_volume=order.volume,
            price=order.price,
            order_type=order.type,
            status=order.status,
            submit_time=datetime.now()
        )
        
        self.active_orders[order.orderid] = stats
        self.current_metrics.total_orders += 1
        self.current_metrics.total_volume += order.volume
    
    def on_order_update(self, order: OrderData) -> None:
        """订单更新回调"""
        stats = self.active_orders.get(order.orderid)
        if not stats:
            return
        
        stats.status = order.status
        stats.filled_volume = order.traded
        
        if order.status == Status.CANCELLED:
            stats.cancel_time = datetime.now()
            self.current_metrics.cancelled_orders += 1
            
            # 检查是否需要重试
            if stats.filled_volume < stats.order_volume:
                if self.retry_strategy.should_retry(order.orderid):
                    self._emit("order_retry_needed", stats)
        
        elif order.status == Status.REJECTED:
            self.current_metrics.rejected_orders += 1
        
        elif order.status == Status.ALLTRADED:
            stats.complete_time = datetime.now()
            self.current_metrics.filled_orders += 1
            self.current_metrics.filled_volume += stats.order_volume
            
            # 移动到历史
            self.order_history.append(stats)
            del self.active_orders[order.orderid]
            self.retry_strategy.reset(order.orderid)
    
    def on_trade(self, trade: TradeData, order_id: str) -> None:
        """成交回调"""
        stats = self.active_orders.get(order_id)
        if not stats:
            return
        
        # 记录首次成交时间
        if not stats.first_fill_time:
            stats.first_fill_time = datetime.now()
        
        # 记录成交
        stats.fill_times.append(datetime.now())
        stats.fill_prices.append(trade.price)
        stats.fill_volumes.append(trade.volume)
        
        self.current_metrics.filled_volume += trade.volume
    
    def get_fill_rate(self) -> float:
        """获取当前成交率"""
        return self.current_metrics.fill_rate
    
    def get_volume_fill_rate(self) -> float:
        """获取成交量成交率"""
        return self.current_metrics.volume_fill_rate
    
    def get_metrics(self) -> FillRateMetrics:
        """获取当前指标"""
        return self.current_metrics
    
    def get_summary(self) -> Dict[str, Any]:
        """获取汇总报告"""
        metrics = self.current_metrics
        
        return {
            "fill_rate": {
                "current": round(metrics.fill_rate * 100, 2),
                "target": round(self.target_fill_rate * 100, 2),
                "status": metrics.status.value,
                "meets_target": metrics.fill_rate >= self.target_fill_rate,
            },
            "volume_fill_rate": round(metrics.volume_fill_rate * 100, 2),
            "orders": {
                "total": metrics.total_orders,
                "filled": metrics.filled_orders,
                "cancelled": metrics.cancelled_orders,
                "rejected": metrics.rejected_orders,
            },
            "active_orders": len(self.active_orders),
            "liquidity_symbols": len(self.liquidity_data),
        }
    
    def reset_metrics(self) -> None:
        """重置指标"""
        self.metrics_history.append(self.current_metrics)
        self.current_metrics = FillRateMetrics(timestamp=datetime.now())
    
    def get_recommendations(self) -> List[str]:
        """获取优化建议"""
        recommendations = []
        metrics = self.current_metrics
        
        if metrics.fill_rate < self.target_fill_rate:
            gap = (self.target_fill_rate - metrics.fill_rate) * 100
            recommendations.append(f"成交率低于目标{gap:.1f}%，建议：")
            
            if metrics.cancelled_orders > metrics.total_orders * 0.1:
                recommendations.append("  - 减少撤单，使用更激进的价格策略")
            
            if metrics.rejected_orders > 0:
                recommendations.append("  - 检查订单被拒绝原因，调整订单参数")
            
            recommendations.append("  - 考虑增加订单重试机制")
            recommendations.append("  - 优化订单拆分策略，减小单笔订单大小")
        
        if metrics.volume_fill_rate < metrics.fill_rate:
            recommendations.append("成交量成交率低于订单成交率，建议：")
            recommendations.append("  - 避免大单冲击市场，进一步拆分订单")
        
        return recommendations


class SmartOrderRouter:
    """
    智能订单路由
    
    根据市场条件自动选择最优执行策略
    """
    
    def __init__(self, optimizer: Optional[FillRateOptimizer] = None):
        """
        Constructor
        
        Args:
            optimizer: 成交率优化器
        """
        self.optimizer = optimizer or FillRateOptimizer()
        
        # 执行策略选择阈值
        self.spread_threshold = 0.002  # 0.2%
        self.volume_threshold = 100000  # 10万
    
    def route_order(
        self,
        vt_symbol: str,
        direction: Direction,
        volume: float,
        price: float,
        urgency: float = 1.0
    ) -> Dict[str, Any]:
        """
        路由订单
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            volume: 数量
            price: 价格
            urgency: 紧急程度
            
        Returns:
            执行计划
        """
        liquidity = self.optimizer.liquidity_data.get(vt_symbol)
        
        if not liquidity:
            # 无流动性数据，使用保守策略
            return {
                "strategy": "conservative",
                "orders": self.optimizer.optimize_order(
                    vt_symbol, direction, volume, price, urgency=0.5
                ),
                "reason": "无流动性数据"
            }
        
        # 根据市场条件选择策略
        if liquidity.spread_pct > self.spread_threshold:
            # 价差大，使用被动策略
            strategy = "passive"
            orders = self.optimizer.optimize_order(
                vt_symbol, direction, volume, price, urgency=0.5
            )
        elif volume * price > self.volume_threshold:
            # 大单，使用TWAP/VWAP
            strategy = "algo"
            orders = self.optimizer.optimize_order(
                vt_symbol, direction, volume, price, urgency=urgency
            )
        else:
            # 普通订单，使用自适应策略
            strategy = "adaptive"
            orders = self.optimizer.optimize_order(
                vt_symbol, direction, volume, price, urgency=urgency
            )
        
        return {
            "strategy": strategy,
            "orders": orders,
            "liquidity": {
                "spread_pct": round(liquidity.spread_pct * 100, 4),
                "bid_volume": liquidity.bid_volume_1,
                "ask_volume": liquidity.ask_volume_1,
            }
        }
