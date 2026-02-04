"""
订单管理模块

提供订单生命周期管理、状态跟踪和风险控制功能
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import threading
import time

from vnpy.trader.object import OrderData, TradeData
from vnpy.trader.constant import Direction, Offset, OrderType, Status


class OrderStage(Enum):
    """订单阶段"""
    CREATED = "created"                # 已创建
    SUBMITTING = "submitting"          # 提交中
    SUBMITTED = "submitted"            # 已提交
    PARTIAL = "partial"                # 部分成交
    FILLED = "filled"                  # 全部成交
    CANCELLING = "cancelling"          # 撤销中
    CANCELLED = "cancelled"            # 已撤销
    REJECTED = "rejected"              # 已拒绝
    EXPIRED = "expired"                # 已过期


class OrderAction(Enum):
    """订单操作"""
    CREATE = "create"                  # 创建
    SUBMIT = "submit"                  # 提交
    CANCEL = "cancel"                  # 撤销
    MODIFY = "modify"                  # 修改
    FILL = "fill"                      # 成交


@dataclass
class OrderRecord:
    """订单记录"""
    # 基本信息
    vt_orderid: str
    vt_symbol: str
    direction: Direction
    offset: Offset
    order_type: OrderType
    price: float
    volume: float
    
    # 状态
    stage: OrderStage = OrderStage.CREATED
    status: Status = Status.SUBMITTING
    traded: float = 0.0
    traded_price: float = 0.0
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    last_update: datetime = field(default_factory=datetime.now)
    
    # 参考信息
    reference: str = ""
    strategy_name: str = ""
    
    # 扩展数据
    extra: Dict[str, Any] = field(default_factory=dict)
    
    # 历史记录
    history: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "vt_orderid": self.vt_orderid,
            "vt_symbol": self.vt_symbol,
            "direction": self.direction.value if self.direction else None,
            "offset": self.offset.value,
            "order_type": self.order_type.value,
            "price": self.price,
            "volume": self.volume,
            "stage": self.stage.value,
            "status": self.status.value,
            "traded": self.traded,
            "traded_price": self.traded_price,
            "created_at": self.created_at.isoformat(),
            "reference": self.reference,
            "strategy_name": self.strategy_name,
        }


@dataclass
class OrderConfig:
    """订单管理配置"""
    # 超时配置
    submit_timeout: int = 10           # 提交超时（秒）
    fill_timeout: int = 300            # 成交超时（秒）
    cancel_timeout: int = 5            # 撤销超时（秒）
    
    # 自动处理配置
    auto_cancel_on_timeout: bool = True    # 超时自动撤销
    auto_cancel_partial: bool = False      # 部分成交后自动撤销剩余
    
    # 风控配置
    max_pending_orders: int = 100      # 最大待处理订单数
    max_orders_per_minute: int = 60    # 每分钟最大订单数
    max_orders_per_symbol: int = 10    # 每品种最大订单数


class OrderStatusTracker:
    """
    订单状态跟踪器
    
    跟踪单个订单的完整生命周期
    """
    
    def __init__(self, order_record: OrderRecord) -> None:
        """
        构造函数
        
        Args:
            order_record: 订单记录
        """
        self.record = order_record
        self._lock = threading.RLock()
    
    def update_from_order(self, order: OrderData) -> None:
        """
        从OrderData更新状态
        
        Args:
            order: 订单数据
        """
        with self._lock:
            # 更新状态
            self.record.status = order.status
            self.record.traded = order.traded
            self.record.last_update = datetime.now()
            
            # 更新阶段
            self._update_stage_from_status(order.status)
            
            # 记录历史
            self._add_history("order_update", {
                "status": order.status.value,
                "traded": order.traded,
            })
    
    def update_from_trade(self, trade: TradeData) -> None:
        """
        从TradeData更新状态
        
        Args:
            trade: 成交数据
        """
        with self._lock:
            # 更新成交数量
            self.record.traded += trade.volume
            
            # 更新成交均价
            total_value = self.record.traded_price * (self.record.traded - trade.volume) + trade.price * trade.volume
            if self.record.traded > 0:
                self.record.traded_price = total_value / self.record.traded
            
            self.record.last_update = datetime.now()
            
            # 更新阶段
            if self.record.traded >= self.record.volume:
                self.record.stage = OrderStage.FILLED
                self.record.filled_at = datetime.now()
            else:
                self.record.stage = OrderStage.PARTIAL
            
            # 记录历史
            self._add_history("trade", {
                "trade_id": trade.vt_tradeid,
                "price": trade.price,
                "volume": trade.volume,
            })
    
    def _update_stage_from_status(self, status: Status) -> None:
        """根据状态更新阶段"""
        status_stage_map = {
            Status.SUBMITTING: OrderStage.SUBMITTING,
            Status.NOTTRADED: OrderStage.SUBMITTED,
            Status.PARTTRADED: OrderStage.PARTIAL,
            Status.ALLTRADED: OrderStage.FILLED,
            Status.CANCELLED: OrderStage.CANCELLED,
            Status.REJECTED: OrderStage.REJECTED,
        }
        
        new_stage = status_stage_map.get(status)
        if new_stage:
            self.record.stage = new_stage
            
            # 更新时间戳
            if new_stage == OrderStage.SUBMITTED and not self.record.submitted_at:
                self.record.submitted_at = datetime.now()
            elif new_stage == OrderStage.FILLED and not self.record.filled_at:
                self.record.filled_at = datetime.now()
            elif new_stage == OrderStage.CANCELLED and not self.record.cancelled_at:
                self.record.cancelled_at = datetime.now()
            elif new_stage == OrderStage.REJECTED and not self.record.rejected_at:
                self.record.rejected_at = datetime.now()
    
    def _add_history(self, action: str, data: Dict) -> None:
        """添加历史记录"""
        self.record.history.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "data": data,
        })
    
    def is_active(self) -> bool:
        """检查订单是否活跃"""
        with self._lock:
            return self.record.stage in [
                OrderStage.SUBMITTING,
                OrderStage.SUBMITTED,
                OrderStage.PARTIAL,
                OrderStage.CANCELLING,
            ]
    
    def is_completed(self) -> bool:
        """检查订单是否已完成"""
        with self._lock:
            return self.record.stage in [
                OrderStage.FILLED,
                OrderStage.CANCELLED,
                OrderStage.REJECTED,
                OrderStage.EXPIRED,
            ]
    
    def get_fill_rate(self) -> float:
        """获取成交率"""
        with self._lock:
            if self.record.volume <= 0:
                return 0.0
            return self.record.traded / self.record.volume
    
    def get_pending_volume(self) -> float:
        """获取待成交数量"""
        with self._lock:
            return self.record.volume - self.record.traded


class OrderManager:
    """
    订单管理器
    
    管理所有订单的生命周期，提供统一的订单操作接口
    """
    
    def __init__(self, config: Optional[OrderConfig] = None) -> None:
        """
        构造函数
        
        Args:
            config: 订单管理配置
        """
        self.config = config or OrderConfig()
        
        # 订单存储
        self._orders: Dict[str, OrderRecord] = {}
        self._trackers: Dict[str, OrderStatusTracker] = {}
        
        # 索引
        self._symbol_orders: Dict[str, Set[str]] = {}
        self._strategy_orders: Dict[str, Set[str]] = {}
        self._active_orders: Set[str] = set()
        
        # 统计
        self._order_counter = 0
        self._minute_orders: List[datetime] = []
        
        # 回调函数
        self._callbacks: Dict[str, List[Callable]] = {
            "on_order_created": [],
            "on_order_submitted": [],
            "on_order_filled": [],
            "on_order_cancelled": [],
            "on_order_rejected": [],
            "on_order_timeout": [],
            "on_order_error": [],
        }
        
        # 锁
        self._lock = threading.RLock()
        
        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
    
    def start(self) -> None:
        """启动订单管理器"""
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_worker,
            daemon=True
        )
        self._monitor_thread.start()
    
    def stop(self) -> None:
        """停止订单管理器"""
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """
        注册回调函数
        
        Args:
            event: 事件类型
            callback: 回调函数
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发回调"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"订单回调执行失败: {e}")
    
    def create_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        order_type: OrderType = OrderType.LIMIT,
        reference: str = "",
        strategy_name: str = ""
    ) -> Optional[OrderRecord]:
        """
        创建订单
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            offset: 开平
            price: 价格
            volume: 数量
            order_type: 订单类型
            reference: 参考信息
            strategy_name: 策略名称
            
        Returns:
            订单记录
        """
        with self._lock:
            # 风控检查
            if not self._check_risk_limits(vt_symbol):
                return None
            
            # 生成订单ID
            self._order_counter += 1
            vt_orderid = f"ALPHA_{datetime.now().strftime('%Y%m%d')}_{self._order_counter:06d}"
            
            # 创建订单记录
            record = OrderRecord(
                vt_orderid=vt_orderid,
                vt_symbol=vt_symbol,
                direction=direction,
                offset=offset,
                order_type=order_type,
                price=price,
                volume=volume,
                reference=reference,
                strategy_name=strategy_name,
            )
            
            # 创建跟踪器
            tracker = OrderStatusTracker(record)
            
            # 存储
            self._orders[vt_orderid] = record
            self._trackers[vt_orderid] = tracker
            self._active_orders.add(vt_orderid)
            
            # 更新索引
            if vt_symbol not in self._symbol_orders:
                self._symbol_orders[vt_symbol] = set()
            self._symbol_orders[vt_symbol].add(vt_orderid)
            
            if strategy_name:
                if strategy_name not in self._strategy_orders:
                    self._strategy_orders[strategy_name] = set()
                self._strategy_orders[strategy_name].add(vt_orderid)
            
            # 更新统计
            self._minute_orders.append(datetime.now())
            
            # 触发回调
            self._emit("on_order_created", record)
            
            return record
    
    def _check_risk_limits(self, vt_symbol: str) -> bool:
        """
        检查风控限制
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            是否通过检查
        """
        # 检查待处理订单数
        if len(self._active_orders) >= self.config.max_pending_orders:
            print(f"待处理订单数超过限制: {self.config.max_pending_orders}")
            return False
        
        # 检查每分钟订单数
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        self._minute_orders = [t for t in self._minute_orders if t > cutoff]
        
        if len(self._minute_orders) >= self.config.max_orders_per_minute:
            print(f"每分钟订单数超过限制: {self.config.max_orders_per_minute}")
            return False
        
        # 检查每品种订单数
        symbol_orders = self._symbol_orders.get(vt_symbol, set())
        active_symbol_orders = [
            oid for oid in symbol_orders
            if oid in self._active_orders
        ]
        
        if len(active_symbol_orders) >= self.config.max_orders_per_symbol:
            print(f"品种 {vt_symbol} 订单数超过限制: {self.config.max_orders_per_symbol}")
            return False
        
        return True
    
    def on_order_update(self, order: OrderData) -> None:
        """
        处理订单更新
        
        Args:
            order: 订单数据
        """
        with self._lock:
            tracker = self._trackers.get(order.vt_orderid)
            if not tracker:
                return
            
            # 更新跟踪器
            tracker.update_from_order(order)
            
            # 检查状态变化
            if not tracker.is_active():
                self._active_orders.discard(order.vt_orderid)
                
                # 触发相应回调
                if order.status == Status.ALLTRADED:
                    self._emit("on_order_filled", tracker.record)
                elif order.status == Status.CANCELLED:
                    self._emit("on_order_cancelled", tracker.record)
                elif order.status == Status.REJECTED:
                    self._emit("on_order_rejected", tracker.record)
    
    def on_trade_update(self, trade: TradeData) -> None:
        """
        处理成交更新
        
        Args:
            trade: 成交数据
        """
        with self._lock:
            tracker = self._trackers.get(trade.vt_orderid)
            if not tracker:
                return
            
            # 更新跟踪器
            tracker.update_from_trade(trade)
            
            # 检查是否完成
            if tracker.is_completed():
                self._active_orders.discard(trade.vt_orderid)
                self._emit("on_order_filled", tracker.record)
    
    def get_order(self, vt_orderid: str) -> Optional[OrderRecord]:
        """
        获取订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            订单记录
        """
        with self._lock:
            return self._orders.get(vt_orderid)
    
    def get_tracker(self, vt_orderid: str) -> Optional[OrderStatusTracker]:
        """
        获取订单跟踪器
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            订单跟踪器
        """
        with self._lock:
            return self._trackers.get(vt_orderid)
    
    def get_active_orders(
        self,
        vt_symbol: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> List[OrderRecord]:
        """
        获取活跃订单
        
        Args:
            vt_symbol: 合约代码过滤
            strategy_name: 策略名称过滤
            
        Returns:
            活跃订单列表
        """
        with self._lock:
            orders = []
            
            for vt_orderid in self._active_orders:
                record = self._orders.get(vt_orderid)
                if not record:
                    continue
                
                # 过滤
                if vt_symbol and record.vt_symbol != vt_symbol:
                    continue
                if strategy_name and record.strategy_name != strategy_name:
                    continue
                
                orders.append(record)
            
            return orders
    
    def get_symbol_orders(self, vt_symbol: str) -> List[OrderRecord]:
        """
        获取品种的所有订单
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            订单列表
        """
        with self._lock:
            order_ids = self._symbol_orders.get(vt_symbol, set())
            return [self._orders[oid] for oid in order_ids if oid in self._orders]
    
    def get_strategy_orders(self, strategy_name: str) -> List[OrderRecord]:
        """
        获取策略的所有订单
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            订单列表
        """
        with self._lock:
            order_ids = self._strategy_orders.get(strategy_name, set())
            return [self._orders[oid] for oid in order_ids if oid in self._orders]
    
    def cancel_order(self, vt_orderid: str) -> bool:
        """
        撤销订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            是否撤销成功
        """
        with self._lock:
            tracker = self._trackers.get(vt_orderid)
            if not tracker:
                return False
            
            if not tracker.is_active():
                return False
            
            # 更新状态
            tracker.record.stage = OrderStage.CANCELLING
            tracker.record.last_update = datetime.now()
            tracker._add_history("cancel_request", {})
            
            return True
    
    def cancel_all_orders(
        self,
        vt_symbol: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> List[str]:
        """
        撤销所有订单
        
        Args:
            vt_symbol: 合约代码过滤
            strategy_name: 策略名称过滤
            
        Returns:
            撤销的订单ID列表
        """
        with self._lock:
            cancelled = []
            
            for vt_orderid in list(self._active_orders):
                record = self._orders.get(vt_orderid)
                if not record:
                    continue
                
                # 过滤
                if vt_symbol and record.vt_symbol != vt_symbol:
                    continue
                if strategy_name and record.strategy_name != strategy_name:
                    continue
                
                if self.cancel_order(vt_orderid):
                    cancelled.append(vt_orderid)
            
            return cancelled
    
    def _monitor_worker(self) -> None:
        """监控工作线程"""
        while not self._stop_monitor.is_set():
            try:
                self._check_timeouts()
                time.sleep(1)
            except Exception as e:
                print(f"订单监控异常: {e}")
    
    def _check_timeouts(self) -> None:
        """检查超时订单"""
        with self._lock:
            now = datetime.now()
            
            for vt_orderid in list(self._active_orders):
                tracker = self._trackers.get(vt_orderid)
                if not tracker:
                    continue
                
                record = tracker.record
                
                # 检查提交超时
                if record.stage == OrderStage.SUBMITTING:
                    if record.created_at + timedelta(seconds=self.config.submit_timeout) < now:
                        self._emit("on_order_timeout", record, "submit_timeout")
                        if self.config.auto_cancel_on_timeout:
                            self.cancel_order(vt_orderid)
                
                # 检查成交超时
                elif record.stage in [OrderStage.SUBMITTED, OrderStage.PARTIAL]:
                    if record.submitted_at and \
                       record.submitted_at + timedelta(seconds=self.config.fill_timeout) < now:
                        self._emit("on_order_timeout", record, "fill_timeout")
                        if self.config.auto_cancel_on_timeout:
                            self.cancel_order(vt_orderid)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计字典
        """
        with self._lock:
            total_orders = len(self._orders)
            active_orders = len(self._active_orders)
            
            filled_orders = sum(
                1 for t in self._trackers.values()
                if t.record.stage == OrderStage.FILLED
            )
            cancelled_orders = sum(
                1 for t in self._trackers.values()
                if t.record.stage == OrderStage.CANCELLED
            )
            rejected_orders = sum(
                1 for t in self._trackers.values()
                if t.record.stage == OrderStage.REJECTED
            )
            
            return {
                "total_orders": total_orders,
                "active_orders": active_orders,
                "filled_orders": filled_orders,
                "cancelled_orders": cancelled_orders,
                "rejected_orders": rejected_orders,
                "fill_rate": filled_orders / total_orders if total_orders > 0 else 0.0,
            }
    
    def get_orders_report(self) -> Dict[str, Any]:
        """
        获取订单报告
        
        Returns:
            订单报告
        """
        with self._lock:
            return {
                "active_orders": [
                    self._orders[oid].to_dict()
                    for oid in self._active_orders
                    if oid in self._orders
                ],
                "statistics": self.get_statistics(),
                "symbol_distribution": {
                    symbol: len(orders)
                    for symbol, orders in self._symbol_orders.items()
                },
                "strategy_distribution": {
                    strategy: len(orders)
                    for strategy, orders in self._strategy_orders.items()
                },
            }
