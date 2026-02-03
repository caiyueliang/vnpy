"""
交易监控模块

监控交易执行情况
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque


@dataclass
class TradeMetrics:
    """交易指标数据"""
    timestamp: datetime
    total_orders: int
    filled_orders: int
    cancelled_orders: int
    rejected_orders: int
    total_trades: int
    total_volume: float
    total_turnover: float
    avg_slippage: float
    avg_latency_ms: float


class TradeMonitor:
    """
    交易监控器

    监控交易执行情况，包括：
    - 订单状态统计
    - 成交统计
    - 滑点分析
    - 延迟分析
    """

    def __init__(self, history_size: int = 10000) -> None:
        """
        Constructor

        Args:
            history_size: 历史数据保留数量
        """
        self.history_size = history_size
        self.orders_history: deque = deque(maxlen=history_size)
        self.trades_history: deque = deque(maxlen=history_size)

        # 统计计数
        self.stats = {
            "total_orders": 0,
            "filled_orders": 0,
            "cancelled_orders": 0,
            "rejected_orders": 0,
            "total_trades": 0,
            "total_volume": 0.0,
            "total_turnover": 0.0,
        }

        # 滑点和延迟记录
        self.slippages: List[float] = []
        self.latencies: List[float] = []

    def record_order(
        self,
        order_id: str,
        status: str,
        volume: float = 0.0,
        latency_ms: float = 0.0
    ) -> None:
        """
        记录订单

        Args:
            order_id: 订单ID
            status: 订单状态
            volume: 委托数量
            latency_ms: 延迟（毫秒）
        """
        order_record = {
            "order_id": order_id,
            "status": status,
            "volume": volume,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(),
        }

        self.orders_history.append(order_record)
        self.stats["total_orders"] += 1

        if status == "filled":
            self.stats["filled_orders"] += 1
        elif status == "cancelled":
            self.stats["cancelled_orders"] += 1
        elif status == "rejected":
            self.stats["rejected_orders"] += 1

        if latency_ms > 0:
            self.latencies.append(latency_ms)

    def record_trade(
        self,
        trade_id: str,
        volume: float,
        price: float,
        expected_price: float = 0.0
    ) -> None:
        """
        记录成交

        Args:
            trade_id: 成交ID
            volume: 成交数量
            price: 成交价格
            expected_price: 预期价格（用于计算滑点）
        """
        trade_record = {
            "trade_id": trade_id,
            "volume": volume,
            "price": price,
            "timestamp": datetime.now(),
        }

        self.trades_history.append(trade_record)
        self.stats["total_trades"] += 1
        self.stats["total_volume"] += volume
        self.stats["total_turnover"] += volume * price

        # 计算滑点
        if expected_price > 0:
            slippage = abs(price - expected_price) / expected_price * 100
            self.slippages.append(slippage)

    def get_fill_rate(self) -> float:
        """
        获取成交率

        Returns:
            成交率（0-1）
        """
        if self.stats["total_orders"] == 0:
            return 0.0
        return self.stats["filled_orders"] / self.stats["total_orders"]

    def get_avg_slippage(self) -> float:
        """
        获取平均滑点

        Returns:
            平均滑点百分比
        """
        if not self.slippages:
            return 0.0
        return sum(self.slippages) / len(self.slippages)

    def get_avg_latency(self) -> float:
        """
        获取平均延迟

        Returns:
            平均延迟（毫秒）
        """
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    def get_summary(self) -> Dict:
        """
        获取交易摘要

        Returns:
            交易统计摘要
        """
        return {
            "orders": {
                "total": self.stats["total_orders"],
                "filled": self.stats["filled_orders"],
                "cancelled": self.stats["cancelled_orders"],
                "rejected": self.stats["rejected_orders"],
                "fill_rate": round(self.get_fill_rate() * 100, 2),
            },
            "trades": {
                "total": self.stats["total_trades"],
                "total_volume": round(self.stats["total_volume"], 2),
                "total_turnover": round(self.stats["total_turnover"], 2),
            },
            "performance": {
                "avg_slippage_pct": round(self.get_avg_slippage(), 4),
                "avg_latency_ms": round(self.get_avg_latency(), 2),
            }
        }

    def reset_stats(self) -> None:
        """重置统计"""
        self.stats = {
            "total_orders": 0,
            "filled_orders": 0,
            "cancelled_orders": 0,
            "rejected_orders": 0,
            "total_trades": 0,
            "total_volume": 0.0,
            "total_turnover": 0.0,
        }
        self.slippages.clear()
        self.latencies.clear()
