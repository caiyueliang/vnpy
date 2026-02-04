"""
持仓管理模块

提供实时持仓跟踪、持仓盈亏计算和持仓风险控制功能
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
import threading

from vnpy.trader.object import PositionData, TradeData, TickData
from vnpy.trader.constant import Direction


@dataclass
class PositionRecord:
    """持仓记录"""
    # 基本信息
    vt_symbol: str
    vt_positionid: str
    direction: Direction
    
    # 持仓数量
    volume: float = 0.0                # 当前持仓
    frozen: float = 0.0                # 冻结数量
    yd_volume: float = 0.0             # 昨仓
    
    # 成本
    price: float = 0.0                 # 持仓均价
    open_price: float = 0.0            # 开仓均价
    
    # 盈亏
    pnl: float = 0.0                   # 持仓盈亏
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    # 扩展数据
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def available(self) -> float:
        """可用数量"""
        return self.volume - self.frozen
    
    @property
    def position_value(self) -> float:
        """持仓市值"""
        return self.volume * self.price
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "vt_symbol": self.vt_symbol,
            "vt_positionid": self.vt_positionid,
            "direction": self.direction.value if self.direction else None,
            "volume": self.volume,
            "frozen": self.frozen,
            "yd_volume": self.yd_volume,
            "available": self.available,
            "price": self.price,
            "open_price": self.open_price,
            "pnl": self.pnl,
            "position_value": self.position_value,
            "last_update": self.last_update.isoformat(),
        }


@dataclass
class PositionConfig:
    """持仓管理配置"""
    # 风控配置
    max_position_value: float = 0.0        # 最大持仓市值（0表示不限制）
    max_position_ratio: float = 0.2        # 最大持仓比例（相对于总资产）
    
    # 盈亏计算配置
    pnl_calculation_method: str = "fifo"   # 盈亏计算方法：fifo/lifo/avg
    
    # 更新配置
    auto_update_pnl: bool = True           # 自动更新盈亏


class PositionTracker:
    """
    持仓跟踪器
    
    跟踪单个持仓的详细信息和变化
    """
    
    def __init__(self, position_record: PositionRecord) -> None:
        """
        构造函数
        
        Args:
            position_record: 持仓记录
        """
        self.record = position_record
        self._lock = threading.RLock()
        
        # 成交历史
        self.trades: List[TradeData] = []
        
        # 价格历史
        self.price_history: List[Dict[str, Any]] = []
    
    def update_from_position(self, position: PositionData) -> None:
        """
        从PositionData更新
        
        Args:
            position: 持仓数据
        """
        with self._lock:
            self.record.volume = position.volume
            self.record.frozen = position.frozen
            self.record.yd_volume = position.yd_volume
            self.record.price = position.price
            self.record.pnl = position.pnl
            self.record.last_update = datetime.now()
    
    def on_trade(self, trade: TradeData) -> None:
        """
        处理成交
        
        Args:
            trade: 成交数据
        """
        with self._lock:
            self.trades.append(trade)
            
            # 更新持仓数量
            if trade.direction == self.record.direction:
                # 开仓
                self._open_position(trade)
            else:
                # 平仓
                self._close_position(trade)
            
            self.record.last_update = datetime.now()
    
    def _open_position(self, trade: TradeData) -> None:
        """开仓处理"""
        # 更新持仓均价
        total_value = self.record.price * self.record.volume + trade.price * trade.volume
        self.record.volume += trade.volume
        
        if self.record.volume > 0:
            self.record.price = total_value / self.record.volume
        
        # 更新开仓均价（首次开仓）
        if self.record.open_price == 0:
            self.record.open_price = trade.price
    
    def _close_position(self, trade: TradeData) -> None:
        """平仓处理"""
        # 减少持仓
        self.record.volume -= trade.volume
        
        # 如果持仓清零，重置成本价
        if self.record.volume <= 0:
            self.record.price = 0.0
            self.record.open_price = 0.0
            self.record.volume = 0.0
    
    def update_pnl(self, last_price: float) -> float:
        """
        更新盈亏
        
        Args:
            last_price: 最新价格
            
        Returns:
            盈亏金额
        """
        with self._lock:
            if self.record.volume == 0 or self.record.price == 0:
                self.record.pnl = 0.0
                return 0.0
            
            # 计算盈亏
            if self.record.direction == Direction.LONG:
                self.record.pnl = (last_price - self.record.price) * self.record.volume
            else:
                self.record.pnl = (self.record.price - last_price) * self.record.volume
            
            # 记录价格历史
            self.price_history.append({
                "timestamp": datetime.now().isoformat(),
                "price": last_price,
                "pnl": self.record.pnl,
            })
            
            # 限制历史记录长度
            if len(self.price_history) > 1000:
                self.price_history = self.price_history[-1000:]
            
            return self.record.pnl
    
    def get_unrealized_pnl(self, last_price: float) -> float:
        """
        获取浮动盈亏
        
        Args:
            last_price: 最新价格
            
        Returns:
            浮动盈亏
        """
        with self._lock:
            if self.record.volume == 0 or self.record.price == 0:
                return 0.0
            
            if self.record.direction == Direction.LONG:
                return (last_price - self.record.price) * self.record.volume
            else:
                return (self.record.price - last_price) * self.record.volume
    
    def get_realized_pnl(self) -> float:
        """
        获取已实现盈亏
        
        Returns:
            已实现盈亏
        """
        with self._lock:
            realized_pnl = 0.0
            
            for trade in self.trades:
                if trade.direction != self.record.direction:
                    # 平仓成交
                    if self.record.direction == Direction.LONG:
                        realized_pnl += (trade.price - self.record.open_price) * trade.volume
                    else:
                        realized_pnl += (self.record.open_price - trade.price) * trade.volume
            
            return realized_pnl
    
    def is_empty(self) -> bool:
        """检查是否空仓"""
        with self._lock:
            return self.record.volume == 0


class PositionManager:
    """
    持仓管理器
    
    管理所有持仓，提供统一的持仓操作接口
    """
    
    def __init__(self, config: Optional[PositionConfig] = None) -> None:
        """
        构造函数
        
        Args:
            config: 持仓管理配置
        """
        self.config = config or PositionConfig()
        
        # 持仓存储
        self._positions: Dict[str, PositionRecord] = {}
        self._trackers: Dict[str, PositionTracker] = {}
        
        # 索引
        self._symbol_positions: Dict[str, Set[str]] = {}
        
        # 最新价格
        self._last_prices: Dict[str, float] = {}
        
        # 总资产（用于计算持仓比例）
        self._total_asset: float = 0.0
        
        # 回调函数
        self._callbacks: Dict[str, List[Callable]] = {
            "on_position_opened": [],
            "on_position_closed": [],
            "on_position_changed": [],
            "on_position_update": [],
        }
        
        # 锁
        self._lock = threading.RLock()
    
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
                print(f"持仓回调执行失败: {e}")
    
    def set_total_asset(self, asset: float) -> None:
        """
        设置总资产
        
        Args:
            asset: 总资产
        """
        with self._lock:
            self._total_asset = asset
    
    def on_position_update(self, position: PositionData) -> None:
        """
        处理持仓更新
        
        Args:
            position: 持仓数据
        """
        with self._lock:
            tracker = self._trackers.get(position.vt_positionid)
            
            if tracker:
                # 更新现有持仓
                old_volume = tracker.record.volume
                tracker.update_from_position(position)
                
                # 检查持仓变化
                if old_volume == 0 and position.volume > 0:
                    self._emit("on_position_opened", tracker.record)
                elif old_volume > 0 and position.volume == 0:
                    self._emit("on_position_closed", tracker.record)
                elif old_volume != position.volume:
                    self._emit("on_position_changed", tracker.record)
                
                self._emit("on_position_update", tracker.record)
            else:
                # 创建新持仓
                self._create_position(position)
    
    def _create_position(self, position: PositionData) -> PositionTracker:
        """
        创建新持仓
        
        Args:
            position: 持仓数据
            
        Returns:
            持仓跟踪器
        """
        # 创建记录
        record = PositionRecord(
            vt_symbol=position.vt_symbol,
            vt_positionid=position.vt_positionid,
            direction=position.direction,
            volume=position.volume,
            frozen=position.frozen,
            yd_volume=position.yd_volume,
            price=position.price,
            pnl=position.pnl,
        )
        
        # 创建跟踪器
        tracker = PositionTracker(record)
        
        # 存储
        self._positions[position.vt_positionid] = record
        self._trackers[position.vt_positionid] = tracker
        
        # 更新索引
        if position.vt_symbol not in self._symbol_positions:
            self._symbol_positions[position.vt_symbol] = set()
        self._symbol_positions[position.vt_symbol].add(position.vt_positionid)
        
        # 触发回调
        if position.volume > 0:
            self._emit("on_position_opened", record)
        
        return tracker
    
    def on_trade(self, trade: TradeData) -> None:
        """
        处理成交
        
        Args:
            trade: 成交数据
        """
        with self._lock:
            # 构建持仓ID
            position_id = f"{trade.gateway_name}.{trade.vt_symbol}.{trade.direction.value}"
            
            tracker = self._trackers.get(position_id)
            if tracker:
                old_volume = tracker.record.volume
                tracker.on_trade(trade)
                
                # 检查持仓变化
                if old_volume == 0 and tracker.record.volume > 0:
                    self._emit("on_position_opened", tracker.record)
                elif old_volume > 0 and tracker.record.volume == 0:
                    self._emit("on_position_closed", tracker.record)
                else:
                    self._emit("on_position_changed", tracker.record)
    
    def on_tick(self, tick: TickData) -> None:
        """
        处理Tick数据
        
        Args:
            tick: Tick数据
        """
        with self._lock:
            # 更新最新价格
            self._last_prices[tick.vt_symbol] = tick.last_price
            
            # 自动更新盈亏
            if self.config.auto_update_pnl:
                self._update_pnl_for_symbol(tick.vt_symbol, tick.last_price)
    
    def _update_pnl_for_symbol(self, vt_symbol: str, last_price: float) -> None:
        """
        更新品种的盈亏
        
        Args:
            vt_symbol: 合约代码
            last_price: 最新价格
        """
        position_ids = self._symbol_positions.get(vt_symbol, set())
        
        for position_id in position_ids:
            tracker = self._trackers.get(position_id)
            if tracker:
                tracker.update_pnl(last_price)
    
    def get_position(self, vt_positionid: str) -> Optional[PositionRecord]:
        """
        获取持仓
        
        Args:
            vt_positionid: 持仓ID
            
        Returns:
            持仓记录
        """
        with self._lock:
            return self._positions.get(vt_positionid)
    
    def get_tracker(self, vt_positionid: str) -> Optional[PositionTracker]:
        """
        获取持仓跟踪器
        
        Args:
            vt_positionid: 持仓ID
            
        Returns:
            持仓跟踪器
        """
        with self._lock:
            return self._trackers.get(vt_positionid)
    
    def get_symbol_positions(self, vt_symbol: str) -> List[PositionRecord]:
        """
        获取品种的所有持仓
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            持仓列表
        """
        with self._lock:
            position_ids = self._symbol_positions.get(vt_symbol, set())
            return [self._positions[pid] for pid in position_ids if pid in self._positions]
    
    def get_all_positions(self) -> List[PositionRecord]:
        """
        获取所有持仓
        
        Returns:
            持仓列表
        """
        with self._lock:
            return list(self._positions.values())
    
    def get_net_position(self, vt_symbol: str) -> float:
        """
        获取净持仓
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            净持仓数量（正数表示多头，负数表示空头）
        """
        with self._lock:
            positions = self.get_symbol_positions(vt_symbol)
            
            net_position = 0.0
            for pos in positions:
                if pos.direction == Direction.LONG:
                    net_position += pos.volume
                else:
                    net_position -= pos.volume
            
            return net_position
    
    def get_position_value(self, vt_symbol: Optional[str] = None) -> float:
        """
        获取持仓市值
        
        Args:
            vt_symbol: 合约代码（None表示所有品种）
            
        Returns:
            持仓市值
        """
        with self._lock:
            if vt_symbol:
                positions = self.get_symbol_positions(vt_symbol)
                return sum(pos.position_value for pos in positions)
            else:
                return sum(pos.position_value for pos in self._positions.values())
    
    def get_total_pnl(self) -> float:
        """
        获取总盈亏
        
        Returns:
            总盈亏
        """
        with self._lock:
            return sum(pos.pnl for pos in self._positions.values())
    
    def get_unrealized_pnl(self, vt_symbol: Optional[str] = None) -> float:
        """
        获取浮动盈亏
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            浮动盈亏
        """
        with self._lock:
            total_pnl = 0.0
            
            if vt_symbol:
                position_ids = self._symbol_positions.get(vt_symbol, set())
                for position_id in position_ids:
                    tracker = self._trackers.get(position_id)
                    if tracker:
                        last_price = self._last_prices.get(vt_symbol, tracker.record.price)
                        total_pnl += tracker.get_unrealized_pnl(last_price)
            else:
                for position_id, tracker in self._trackers.items():
                    last_price = self._last_prices.get(
                        tracker.record.vt_symbol,
                        tracker.record.price
                    )
                    total_pnl += tracker.get_unrealized_pnl(last_price)
            
            return total_pnl
    
    def check_position_limit(self, vt_symbol: str, direction: Direction, volume: float) -> bool:
        """
        检查持仓限制
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            volume: 数量
            
        Returns:
            是否通过检查
        """
        with self._lock:
            # 计算开仓后的持仓市值
            current_value = self.get_position_value()
            
            # 获取最新价格
            last_price = self._last_prices.get(vt_symbol, 0)
            if last_price == 0:
                return True  # 无法获取价格，跳过检查
            
            new_position_value = current_value + volume * last_price
            
            # 检查最大持仓市值
            if self.config.max_position_value > 0 and new_position_value > self.config.max_position_value:
                print(f"持仓市值 {new_position_value} 超过限制 {self.config.max_position_value}")
                return False
            
            # 检查最大持仓比例
            if self._total_asset > 0:
                position_ratio = new_position_value / self._total_asset
                if position_ratio > self.config.max_position_ratio:
                    print(f"持仓比例 {position_ratio:.2%} 超过限制 {self.config.max_position_ratio:.2%}")
                    return False
            
            return True
    
    def get_position_ratio(self) -> float:
        """
        获取持仓比例
        
        Returns:
            持仓比例
        """
        with self._lock:
            if self._total_asset <= 0:
                return 0.0
            
            position_value = self.get_position_value()
            return position_value / self._total_asset
    
    def get_position_report(self) -> Dict[str, Any]:
        """
        获取持仓报告
        
        Returns:
            持仓报告
        """
        with self._lock:
            positions_data = []
            
            for record in self._positions.values():
                pos_data = record.to_dict()
                
                # 添加最新盈亏
                tracker = self._trackers.get(record.vt_positionid)
                if tracker:
                    last_price = self._last_prices.get(record.vt_symbol, record.price)
                    pos_data["unrealized_pnl"] = tracker.get_unrealized_pnl(last_price)
                
                positions_data.append(pos_data)
            
            return {
                "positions": positions_data,
                "summary": {
                    "total_positions": len(self._positions),
                    "total_value": self.get_position_value(),
                    "total_pnl": self.get_total_pnl(),
                    "unrealized_pnl": self.get_unrealized_pnl(),
                    "position_ratio": self.get_position_ratio(),
                },
                "symbol_distribution": {
                    symbol: sum(
                        self._positions[pid].position_value
                        for pid in pids if pid in self._positions
                    )
                    for symbol, pids in self._symbol_positions.items()
                },
            }
