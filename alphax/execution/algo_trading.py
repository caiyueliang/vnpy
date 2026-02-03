"""
算法交易模块

实现TWAP、VWAP等算法订单执行策略
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from collections import defaultdict
import random

import numpy as np

from vnpy.trader.object import TickData, BarData
from vnpy.trader.constant import Direction, Offset, Exchange


class AlgoStatus(Enum):
    """算法状态"""
    PENDING = "pending"           # 待启动
    RUNNING = "running"           # 运行中
    PAUSED = "paused"             # 暂停
    COMPLETED = "completed"       # 已完成
    CANCELLED = "cancelled"       # 已取消
    ERROR = "error"               # 错误


class AlgoType(Enum):
    """算法类型"""
    TWAP = "twap"                 # 时间加权平均价格
    VWAP = "vwap"                 # 成交量加权平均价格
    ICEBERG = "iceberg"           # 冰山订单
    SNAPSHOT = "snapshot"         # 快照执行
    ADAPTIVE = "adaptive"         # 自适应算法


@dataclass
class AlgoOrder:
    """算法订单"""
    algo_id: str
    vt_symbol: str
    direction: Direction
    offset: Offset
    
    # 目标
    target_volume: float          # 目标数量
    target_price: float = 0.0     # 目标价格（限价）
    
    # 时间控制
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # 状态
    status: AlgoStatus = AlgoStatus.PENDING
    filled_volume: float = 0.0
    filled_price: float = 0.0
    
    # 统计
    create_time: datetime = field(default_factory=datetime.now)
    update_time: Optional[datetime] = None
    
    def get_remaining_volume(self) -> float:
        """获取剩余数量"""
        return self.target_volume - self.filled_volume
    
    def get_fill_rate(self) -> float:
        """获取完成率"""
        if self.target_volume <= 0:
            return 0.0
        return self.filled_volume / self.target_volume


@dataclass
class ChildOrder:
    """子订单"""
    order_id: str
    algo_id: str
    
    vt_symbol: str
    direction: Direction
    offset: Offset
    price: float
    volume: float
    
    status: str = "pending"
    traded: float = 0.0
    create_time: datetime = field(default_factory=datetime.now)


@dataclass
class AlgoConfig:
    """算法配置"""
    # 基本配置
    min_order_size: float = 100.0     # 最小订单数量
    max_order_size: float = 10000.0   # 最大订单数量
    price_tolerance: float = 0.001    # 价格容忍度 0.1%
    
    # 时间配置
    interval_seconds: int = 60        # 下单间隔（秒）
    min_interval_seconds: int = 10    # 最小间隔
    max_interval_seconds: int = 300   # 最大间隔
    
    # 风险控制
    max_slippage_pct: float = 0.002   # 最大滑点 0.2%
    urgency_factor: float = 1.0       # 紧急程度因子 (0-2)


@dataclass
class TWAPConfig(AlgoConfig):
    """TWAP配置"""
    algo_type: AlgoType = AlgoType.TWAP
    slice_count: int = 10             # 切片数量
    randomize: bool = True            # 随机化切片大小
    random_range: float = 0.2         # 随机范围 ±20%


@dataclass
class VWAPConfig(AlgoConfig):
    """VWAP配置"""
    algo_type: AlgoType = AlgoType.VWAP
    volume_profile: Dict[int, float] = field(default_factory=dict)  # 成交量分布
    participation_rate: float = 0.1   # 参与率（占市场成交量比例）
    adaptive: bool = True             # 是否自适应调整


@dataclass
class IcebergConfig(AlgoConfig):
    """冰山订单配置"""
    algo_type: AlgoType = AlgoType.ICEBERG
    display_size: float = 100.0       # 显示数量
    variance_pct: float = 0.2         # 数量变化范围 ±20%
    refresh_condition: str = "fill"   # 刷新条件: fill/price/time


@dataclass
class MarketSlice:
    """市场切片数据"""
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    turnover: float
    
    @property
    def vwap(self) -> float:
        """计算VWAP"""
        if self.volume > 0:
            return self.turnover / self.volume
        return self.close_price


class AlgoTemplate(ABC):
    """
    算法模板基类
    
    所有算法订单执行器必须继承此类
    """
    
    def __init__(
        self,
        algo_order: AlgoOrder,
        config: AlgoConfig,
        send_order_callback: Callable,
        cancel_order_callback: Callable
    ) -> None:
        """Constructor"""
        self.algo_order = algo_order
        self.config = config
        self.send_order_callback = send_order_callback
        self.cancel_order_callback = cancel_order_callback
        
        # 子订单管理
        self.child_orders: Dict[str, ChildOrder] = {}
        self.active_child_orders: Dict[str, ChildOrder] = {}
        
        # 市场数据
        self.current_tick: Optional[TickData] = None
        self.current_bar: Optional[BarData] = None
        self.price_history: List[MarketSlice] = []
        self.volume_profile: Dict[int, float] = defaultdict(float)
        
        # 执行计划
        self.execution_plan: List[Dict] = []
        self.current_slice_index: int = 0
        
        # 统计
        self.total_trades: int = 0
        self.avg_fill_price: float = 0.0
        self.slippage_stats: List[float] = []
        
        # 时间控制
        self.last_order_time: Optional[datetime] = None
        self.next_order_time: Optional[datetime] = None
        
        # 回调
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)
    
    def start(self) -> None:
        """启动算法"""
        if self.algo_order.status != AlgoStatus.PENDING:
            return
        
        self.algo_order.status = AlgoStatus.RUNNING
        self.algo_order.start_time = datetime.now()
        
        # 生成执行计划
        self._generate_execution_plan()
        
        self._emit("algo_started", self.algo_order)
    
    def pause(self) -> None:
        """暂停算法"""
        if self.algo_order.status == AlgoStatus.RUNNING:
            self.algo_order.status = AlgoStatus.PAUSED
            self._emit("algo_paused", self.algo_order)
    
    def resume(self) -> None:
        """恢复算法"""
        if self.algo_order.status == AlgoStatus.PAUSED:
            self.algo_order.status = AlgoStatus.RUNNING
            self._emit("algo_resumed", self.algo_order)
    
    def cancel(self) -> None:
        """取消算法"""
        self.algo_order.status = AlgoStatus.CANCELLED
        
        # 取消所有活跃子订单
        for child_order in list(self.active_child_orders.values()):
            self.cancel_order_callback(child_order.order_id)
        
        self.active_child_orders.clear()
        self._emit("algo_cancelled", self.algo_order)
    
    def on_tick(self, tick: TickData) -> None:
        """
        Tick数据回调
        
        Args:
            tick: Tick数据
        """
        self.current_tick = tick
        
        if self.algo_order.status != AlgoStatus.RUNNING:
            return
        
        self._process_tick(tick)
    
    def on_bar(self, bar: BarData) -> None:
        """
        K线数据回调
        
        Args:
            bar: K线数据
        """
        self.current_bar = bar
        
        # 更新价格历史
        slice_data = MarketSlice(
            timestamp=bar.datetime,
            open_price=bar.open_price,
            high_price=bar.high_price,
            low_price=bar.low_price,
            close_price=bar.close_price,
            volume=bar.volume,
            turnover=getattr(bar, 'turnover', bar.volume * bar.close_price)
        )
        self.price_history.append(slice_data)
        
        # 保持最近100条
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]
        
        if self.algo_order.status != AlgoStatus.RUNNING:
            return
        
        self._process_bar(bar)
    
    def on_child_order_filled(
        self,
        order_id: str,
        price: float,
        volume: float
    ) -> None:
        """
        子订单成交回调
        
        Args:
            order_id: 订单ID
            price: 成交价格
            volume: 成交数量
        """
        child_order = self.child_orders.get(order_id)
        if not child_order:
            return
        
        # 更新子订单
        child_order.traded += volume
        if child_order.traded >= child_order.volume:
            child_order.status = "filled"
            if order_id in self.active_child_orders:
                del self.active_child_orders[order_id]
        else:
            child_order.status = "partial"
        
        # 更新算法订单
        self.algo_order.filled_volume += volume
        
        # 更新成交均价
        total_value = self.avg_fill_price * (self.algo_order.filled_volume - volume) + price * volume
        if self.algo_order.filled_volume > 0:
            self.avg_fill_price = total_value / self.algo_order.filled_volume
        
        # 计算滑点
        if self.algo_order.target_price > 0:
            slippage = abs(price - self.algo_order.target_price) / self.algo_order.target_price
            self.slippage_stats.append(slippage)
        
        self.total_trades += 1
        
        # 检查是否完成
        if self.algo_order.get_remaining_volume() <= 0:
            self.algo_order.status = AlgoStatus.COMPLETED
            self.algo_order.end_time = datetime.now()
            self._emit("algo_completed", self.algo_order)
        else:
            self._emit("algo_progress", self.algo_order)
    
    @abstractmethod
    def _generate_execution_plan(self) -> None:
        """生成执行计划"""
        pass
    
    @abstractmethod
    def _process_tick(self, tick: TickData) -> None:
        """处理Tick数据"""
        pass
    
    @abstractmethod
    def _process_bar(self, bar: BarData) -> None:
        """处理K线数据"""
        pass
    
    def _send_child_order(self, price: float, volume: float) -> Optional[str]:
        """
        发送子订单
        
        Args:
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        # 检查数量限制
        volume = max(self.config.min_order_size, min(volume, self.config.max_order_size))
        
        # 检查剩余数量
        remaining = self.algo_order.get_remaining_volume()
        volume = min(volume, remaining)
        
        if volume <= 0:
            return None
        
        # 生成订单ID
        order_id = f"{self.algo_order.algo_id}_{len(self.child_orders):04d}"
        
        # 创建子订单
        child_order = ChildOrder(
            order_id=order_id,
            algo_id=self.algo_order.algo_id,
            vt_symbol=self.algo_order.vt_symbol,
            direction=self.algo_order.direction,
            offset=self.algo_order.offset,
            price=price,
            volume=volume
        )
        
        self.child_orders[order_id] = child_order
        self.active_child_orders[order_id] = child_order
        
        # 发送订单
        self.send_order_callback(
            vt_symbol=self.algo_order.vt_symbol,
            direction=self.algo_order.direction,
            offset=self.algo_order.offset,
            price=price,
            volume=volume,
            order_id=order_id
        )
        
        self.last_order_time = datetime.now()
        
        return order_id
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "algo_id": self.algo_order.algo_id,
            "status": self.algo_order.status.value,
            "target_volume": self.algo_order.target_volume,
            "filled_volume": self.algo_order.filled_volume,
            "fill_rate": self.algo_order.get_fill_rate(),
            "avg_fill_price": self.avg_fill_price,
            "target_price": self.algo_order.target_price,
            "total_trades": self.total_trades,
            "avg_slippage": np.mean(self.slippage_stats) if self.slippage_stats else 0.0,
            "child_orders": len(self.child_orders),
            "active_child_orders": len(self.active_child_orders),
        }


class TWAPAlgo(AlgoTemplate):
    """
    TWAP算法（时间加权平均价格）
    
    将大单拆分为多个小单，在指定时间区间内均匀执行
    """
    
    def __init__(
        self,
        algo_order: AlgoOrder,
        config: TWAPConfig,
        send_order_callback: Callable,
        cancel_order_callback: Callable
    ) -> None:
        """Constructor"""
        super().__init__(algo_order, config, send_order_callback, cancel_order_callback)
        self.config: TWAPConfig = config
        
        # 时间切片
        self.slice_interval: timedelta = timedelta(seconds=0)
        self.slices: List[Dict] = []
    
    def _generate_execution_plan(self) -> None:
        """生成TWAP执行计划"""
        if not self.algo_order.start_time or not self.algo_order.end_time:
            # 默认使用当天交易时间
            now = datetime.now()
            self.algo_order.start_time = now
            self.algo_order.end_time = now + timedelta(hours=1)
        
        total_duration = self.algo_order.end_time - self.algo_order.start_time
        total_seconds = total_duration.total_seconds()
        
        # 计算切片间隔
        self.slice_interval = timedelta(seconds=total_seconds / self.config.slice_count)
        
        # 生成切片
        base_volume = self.algo_order.target_volume / self.config.slice_count
        
        for i in range(self.config.slice_count):
            # 随机化切片大小
            if self.config.randomize:
                variance = random.uniform(
                    -self.config.random_range,
                    self.config.random_range
                )
                slice_volume = base_volume * (1 + variance)
            else:
                slice_volume = base_volume
            
            slice_time = self.algo_order.start_time + self.slice_interval * i
            
            self.slices.append({
                "index": i,
                "time": slice_time,
                "volume": slice_volume,
                "executed": False
            })
        
        # 调整最后一个切片的数量，确保总量匹配
        total_slice_volume = sum(s["volume"] for s in self.slices)
        if total_slice_volume != self.algo_order.target_volume:
            diff = self.algo_order.target_volume - total_slice_volume
            self.slices[-1]["volume"] += diff
    
    def _process_tick(self, tick: TickData) -> None:
        """处理Tick数据"""
        now = datetime.now()
        
        # 检查是否需要执行切片
        for slice_data in self.slices:
            if slice_data["executed"]:
                continue
            
            if now >= slice_data["time"]:
                # 执行切片
                self._execute_slice(slice_data, tick.last_price)
    
    def _process_bar(self, bar: BarData) -> None:
        """处理K线数据"""
        # TWAP主要基于时间，K线数据用于参考
        pass
    
    def _execute_slice(self, slice_data: Dict, price: float) -> None:
        """执行切片"""
        # 计算订单价格
        if self.algo_order.target_price > 0:
            # 限价单，添加微小随机偏移
            offset = random.uniform(-0.001, 0.001)
            order_price = self.algo_order.target_price * (1 + offset)
        else:
            # 市价单
            order_price = price
        
        # 发送订单
        self._send_child_order(order_price, slice_data["volume"])
        
        slice_data["executed"] = True
        self.current_slice_index += 1


class VWAPAlgo(AlgoTemplate):
    """
    VWAP算法（成交量加权平均价格）
    
    根据历史成交量分布，在成交量大的时段多下单
    """
    
    def __init__(
        self,
        algo_order: AlgoOrder,
        config: VWAPConfig,
        send_order_callback: Callable,
        cancel_order_callback: Callable
    ) -> None:
        """Constructor"""
        super().__init__(algo_order, config, send_order_callback, cancel_order_callback)
        self.config: VWAPConfig = config
        
        # 实际成交量跟踪
        self.market_volume: float = 0.0
        self.expected_volume: float = 0.0
        
        # 自适应调整因子
        self.adaptive_factor: float = 1.0
    
    def _generate_execution_plan(self) -> None:
        """生成VWAP执行计划"""
        if not self.config.volume_profile:
            # 使用默认的成交量分布（U型分布）
            self._generate_default_volume_profile()
        
        if not self.algo_order.start_time or not self.algo_order.end_time:
            now = datetime.now()
            self.algo_order.start_time = now
            self.algo_order.end_time = now + timedelta(hours=1)
        
        total_duration = self.algo_order.end_time - self.algo_order.start_time
        interval = timedelta(seconds=self.config.interval_seconds)
        
        # 根据成交量分布生成切片
        current_time = self.algo_order.start_time
        slice_index = 0
        
        while current_time < self.algo_order.end_time:
            # 获取时间段的成交量权重
            time_key = current_time.hour * 60 + current_time.minute
            volume_weight = self.config.volume_profile.get(time_key, 1.0)
            
            # 计算切片数量
            slice_volume = (self.algo_order.target_volume * volume_weight / 
                          sum(self.config.volume_profile.values()))
            
            self.execution_plan.append({
                "index": slice_index,
                "time": current_time,
                "volume": slice_volume,
                "executed": False,
                "volume_weight": volume_weight
            })
            
            current_time += interval
            slice_index += 1
        
        # 归一化数量
        total_slice_volume = sum(s["volume"] for s in self.execution_plan)
        if total_slice_volume > 0:
            for slice_data in self.execution_plan:
                slice_data["volume"] *= self.algo_order.target_volume / total_slice_volume
    
    def _generate_default_volume_profile(self) -> None:
        """生成默认成交量分布（U型分布）"""
        # 模拟A股交易时间的U型成交量分布
        # 开盘和收盘时成交量大，中午成交量小
        
        profile = {}
        
        # 9:30-11:30 上午交易时间
        for minute in range(570, 690):  # 9:30-11:30
            if minute < 600:  # 开盘后30分钟
                weight = 2.0 - (minute - 570) / 30 * 0.5
            elif minute > 660:  # 收盘前30分钟
                weight = 1.5 + (minute - 660) / 30 * 0.5
            else:
                weight = 1.0
            profile[minute] = weight
        
        # 13:00-15:00 下午交易时间
        for minute in range(780, 900):  # 13:00-15:00
            if minute < 810:  # 开盘后30分钟
                weight = 1.5 - (minute - 780) / 30 * 0.3
            elif minute > 870:  # 收盘前30分钟
                weight = 1.2 + (minute - 870) / 30 * 0.8
            else:
                weight = 1.0
            profile[minute] = weight
        
        self.config.volume_profile = profile
    
    def _process_tick(self, tick: TickData) -> None:
        """处理Tick数据"""
        now = datetime.now()
        
        # 跟踪市场成交量
        if hasattr(tick, 'volume'):
            self.market_volume += tick.volume
        
        # 检查是否需要执行切片
        for slice_data in self.execution_plan:
            if slice_data["executed"]:
                continue
            
            if now >= slice_data["time"]:
                # 自适应调整
                if self.config.adaptive:
                    self._adjust_slice_volume(slice_data)
                
                # 执行切片
                price = tick.last_price if self.current_tick else self.algo_order.target_price
                self._execute_slice(slice_data, price)
    
    def _process_bar(self, bar: BarData) -> None:
        """处理K线数据"""
        # 更新市场成交量预期
        self.expected_volume += bar.volume
    
    def _adjust_slice_volume(self, slice_data: Dict) -> None:
        """自适应调整切片数量"""
        if self.expected_volume <= 0 or self.market_volume <= 0:
            return
        
        # 计算实际/预期成交量比率
        volume_ratio = self.market_volume / self.expected_volume
        
        # 调整因子
        if volume_ratio > 1.2:
            # 成交量大于预期，增加下单量
            self.adaptive_factor = min(1.5, self.adaptive_factor * 1.1)
        elif volume_ratio < 0.8:
            # 成交量小于预期，减少下单量
            self.adaptive_factor = max(0.5, self.adaptive_factor * 0.9)
        
        slice_data["volume"] *= self.adaptive_factor
    
    def _execute_slice(self, slice_data: Dict, price: float) -> None:
        """执行切片"""
        # 计算订单价格
        if self.algo_order.target_price > 0:
            order_price = self.algo_order.target_price
        else:
            order_price = price
        
        # 发送订单
        self._send_child_order(order_price, slice_data["volume"])
        
        slice_data["executed"] = True


class IcebergAlgo(AlgoTemplate):
    """
    冰山订单算法
    
    大单拆分为多个小单，每次只显示一部分，成交后再显示下一部分
    """
    
    def __init__(
        self,
        algo_order: AlgoOrder,
        config: IcebergConfig,
        send_order_callback: Callable,
        cancel_order_callback: Callable
    ) -> None:
        """Constructor"""
        super().__init__(algo_order, config, send_order_callback, cancel_order_callback)
        self.config: IcebergConfig = config
        
        # 当前显示数量
        self.current_display_size: float = config.display_size
    
    def _generate_execution_plan(self) -> None:
        """生成冰山订单执行计划"""
        # 冰山订单是事件驱动的，不需要预生成计划
        pass
    
    def _process_tick(self, tick: TickData) -> None:
        """处理Tick数据"""
        # 检查是否有活跃子订单
        if self.active_child_orders:
            return
        
        # 检查是否还有剩余数量
        remaining = self.algo_order.get_remaining_volume()
        if remaining <= 0:
            return
        
        # 计算本次下单数量
        self._update_display_size()
        order_volume = min(self.current_display_size, remaining)
        
        # 确定价格
        if self.algo_order.target_price > 0:
            order_price = self.algo_order.target_price
        else:
            # 使用对手价
            if self.algo_order.direction.value == "多":
                order_price = tick.ask_price_1 if hasattr(tick, 'ask_price_1') else tick.last_price
            else:
                order_price = tick.bid_price_1 if hasattr(tick, 'bid_price_1') else tick.last_price
        
        # 发送订单
        self._send_child_order(order_price, order_volume)
    
    def _process_bar(self, bar: BarData) -> None:
        """处理K线数据"""
        # 冰山订单主要基于Tick数据
        pass
    
    def _update_display_size(self) -> None:
        """更新显示数量"""
        if self.config.variance_pct > 0:
            variance = random.uniform(
                -self.config.variance_pct,
                self.config.variance_pct
            )
            self.current_display_size = self.config.display_size * (1 + variance)
        else:
            self.current_display_size = self.config.display_size
    
    def on_child_order_filled(
        self,
        order_id: str,
        price: float,
        volume: float
    ) -> None:
        """
        子订单成交回调（重写以支持冰山订单的连续执行）
        """
        super().on_child_order_filled(order_id, price, volume)
        
        # 冰山订单特性：成交后立即发送下一个
        if self.algo_order.status == AlgoStatus.RUNNING:
            if self.current_tick:
                self._process_tick(self.current_tick)


class AlgoEngine:
    """
    算法交易引擎
    
    管理所有算法订单的执行
    """
    
    def __init__(self) -> None:
        """Constructor"""
        self.algos: Dict[str, AlgoTemplate] = {}
        self.algo_counter: int = 0
        
        # 回调函数
        self.send_order_callback: Optional[Callable] = None
        self.cancel_order_callback: Optional[Callable] = None
        
        # 统计
        self.stats: Dict[str, Any] = {
            "total_algos": 0,
            "completed_algos": 0,
            "cancelled_algos": 0,
            "total_volume": 0.0,
            "filled_volume": 0.0,
        }
    
    def set_callbacks(
        self,
        send_order: Callable,
        cancel_order: Callable
    ) -> None:
        """设置回调函数"""
        self.send_order_callback = send_order
        self.cancel_order_callback = cancel_order
    
    def create_algo(
        self,
        algo_type: AlgoType,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        volume: float,
        price: float = 0.0,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        config: Optional[AlgoConfig] = None
    ) -> str:
        """
        创建算法订单
        
        Args:
            algo_type: 算法类型
            vt_symbol: 合约代码
            direction: 方向
            offset: 开平
            volume: 数量
            price: 价格
            start_time: 开始时间
            end_time: 结束时间
            config: 算法配置
            
        Returns:
            算法ID
        """
        if not self.send_order_callback:
            raise ValueError("回调函数未设置")
        
        # 生成算法ID
        self.algo_counter += 1
        algo_id = f"ALGO_{datetime.now().strftime('%Y%m%d')}_{self.algo_counter:06d}"
        
        # 创建算法订单
        algo_order = AlgoOrder(
            algo_id=algo_id,
            vt_symbol=vt_symbol,
            direction=direction,
            offset=offset,
            target_volume=volume,
            target_price=price,
            start_time=start_time,
            end_time=end_time
        )
        
        # 创建算法实例
        if algo_type == AlgoType.TWAP:
            config = config or TWAPConfig()
            algo = TWAPAlgo(
                algo_order=algo_order,
                config=config,
                send_order_callback=self.send_order_callback,
                cancel_order_callback=self.cancel_order_callback
            )
        elif algo_type == AlgoType.VWAP:
            config = config or VWAPConfig()
            algo = VWAPAlgo(
                algo_order=algo_order,
                config=config,
                send_order_callback=self.send_order_callback,
                cancel_order_callback=self.cancel_order_callback
            )
        elif algo_type == AlgoType.ICEBERG:
            config = config or IcebergConfig()
            algo = IcebergAlgo(
                algo_order=algo_order,
                config=config,
                send_order_callback=self.send_order_callback,
                cancel_order_callback=self.cancel_order_callback
            )
        else:
            raise ValueError(f"不支持的算法类型: {algo_type}")
        
        self.algos[algo_id] = algo
        self.stats["total_algos"] += 1
        self.stats["total_volume"] += volume
        
        return algo_id
    
    def start_algo(self, algo_id: str) -> bool:
        """启动算法"""
        algo = self.algos.get(algo_id)
        if algo:
            algo.start()
            return True
        return False
    
    def cancel_algo(self, algo_id: str) -> bool:
        """取消算法"""
        algo = self.algos.get(algo_id)
        if algo:
            algo.cancel()
            self.stats["cancelled_algos"] += 1
            return True
        return False
    
    def on_tick(self, vt_symbol: str, tick: TickData) -> None:
        """Tick数据回调"""
        for algo in self.algos.values():
            if algo.algo_order.vt_symbol == vt_symbol:
                algo.on_tick(tick)
    
    def on_bar(self, vt_symbol: str, bar: BarData) -> None:
        """K线数据回调"""
        for algo in self.algos.values():
            if algo.algo_order.vt_symbol == vt_symbol:
                algo.on_bar(bar)
    
    def on_order_filled(
        self,
        algo_id: str,
        order_id: str,
        price: float,
        volume: float
    ) -> None:
        """订单成交回调"""
        algo = self.algos.get(algo_id)
        if algo:
            algo.on_child_order_filled(order_id, price, volume)
            self.stats["filled_volume"] += volume
            
            if algo.algo_order.status == AlgoStatus.COMPLETED:
                self.stats["completed_algos"] += 1
    
    def get_algo(self, algo_id: str) -> Optional[AlgoTemplate]:
        """获取算法实例"""
        return self.algos.get(algo_id)
    
    def get_algo_stats(self, algo_id: str) -> Optional[Dict]:
        """获取算法统计"""
        algo = self.algos.get(algo_id)
        if algo:
            return algo.get_stats()
        return None
    
    def get_all_stats(self) -> Dict:
        """获取所有统计"""
        return self.stats.copy()
    
    def get_active_algos(self) -> List[str]:
        """获取活跃算法列表"""
        return [
            algo_id for algo_id, algo in self.algos.items()
            if algo.algo_order.status == AlgoStatus.RUNNING
        ]
