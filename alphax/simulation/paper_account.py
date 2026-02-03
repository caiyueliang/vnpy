"""
虚拟账户管理模块

实现模拟交易账户管理，包括资金、持仓、订单、成交等
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable
from collections import defaultdict
from enum import Enum

from vnpy.trader.object import (
    BarData, TickData, OrderData, TradeData, PositionData, AccountData
)
from vnpy.trader.constant import Direction, Offset, Status, Exchange


class OrderStatus(Enum):
    """订单状态扩展"""
    PENDING = "pending"           # 待提交
    SUBMITTED = "submitted"       # 已提交
    PARTIAL = "partial"           # 部分成交
    FILLED = "filled"             # 全部成交
    CANCELLED = "cancelled"       # 已撤销
    REJECTED = "rejected"         # 已拒绝


@dataclass
class PaperPosition:
    """虚拟持仓"""
    vt_symbol: str
    direction: Direction
    volume: float = 0.0
    price: float = 0.0
    pnl: float = 0.0
    
    def update(self, volume: float, price: float) -> None:
        """更新持仓"""
        if self.volume == 0:
            self.price = price
            self.volume = volume
        else:
            # 计算加权平均成本
            total_cost = self.volume * self.price + volume * price
            self.volume += volume
            if self.volume > 0:
                self.price = total_cost / abs(self.volume)
    
    def calculate_pnl(self, current_price: float) -> float:
        """计算浮动盈亏"""
        if self.volume == 0:
            return 0.0
        if self.direction == Direction.LONG:
            return (current_price - self.price) * self.volume
        else:
            return (self.price - current_price) * abs(self.volume)


@dataclass
class PaperOrder:
    """虚拟订单"""
    vt_orderid: str
    vt_symbol: str
    direction: Direction
    offset: Offset
    price: float
    volume: float
    status: OrderStatus = OrderStatus.PENDING
    traded: float = 0.0
    create_time: datetime = field(default_factory=datetime.now)
    update_time: Optional[datetime] = None
    
    def to_vnpy_order(self) -> OrderData:
        """转换为vn.py订单对象"""
        symbol, exchange = self.vt_symbol.split(".")
        
        status_map = {
            OrderStatus.PENDING: Status.NOTTRADED,
            OrderStatus.SUBMITTED: Status.NOTTRADED,
            OrderStatus.PARTIAL: Status.PARTTRADED,
            OrderStatus.FILLED: Status.ALLTRADED,
            OrderStatus.CANCELLED: Status.CANCELLED,
            OrderStatus.REJECTED: Status.REJECTED,
        }
        
        order = OrderData(
            symbol=symbol,
            exchange=Exchange(exchange),
            orderid=self.vt_orderid.split(".")[-1],
            direction=self.direction,
            offset=self.offset,
            price=self.price,
            volume=self.volume,
            traded=self.traded,
            status=status_map.get(self.status, Status.NOTTRADED),
            datetime=self.create_time,
            gateway_name="PAPER"
        )
        order.vt_orderid = self.vt_orderid
        return order


@dataclass
class PaperTrade:
    """虚拟成交"""
    vt_tradeid: str
    vt_orderid: str
    vt_symbol: str
    direction: Direction
    offset: Offset
    price: float
    volume: float
    trade_time: datetime = field(default_factory=datetime.now)
    
    def to_vnpy_trade(self) -> TradeData:
        """转换为vn.py成交对象"""
        symbol, exchange = self.vt_symbol.split(".")
        
        trade = TradeData(
            symbol=symbol,
            exchange=Exchange(exchange),
            orderid=self.vt_orderid.split(".")[-1],
            tradeid=self.vt_tradeid.split(".")[-1],
            direction=self.direction,
            offset=self.offset,
            price=self.price,
            volume=self.volume,
            datetime=self.trade_time,
            gateway_name="PAPER"
        )
        trade.vt_orderid = self.vt_orderid
        trade.vt_tradeid = self.vt_tradeid
        return trade


@dataclass
class PaperAccountConfig:
    """虚拟账户配置"""
    initial_capital: float = 1_000_000.0      # 初始资金
    commission_rate: float = 0.0003           # 手续费率
    slippage: float = 0.0001                  # 滑点
    size: int = 1                             # 合约乘数
    margin_rate: float = 0.1                  # 保证金比例


class PaperAccount:
    """
    虚拟账户
    
    模拟真实交易账户的资金、持仓、订单管理
    """
    
    def __init__(self, config: Optional[PaperAccountConfig] = None) -> None:
        """Constructor"""
        self.config = config or PaperAccountConfig()
        
        # 资金
        self.balance: float = self.config.initial_capital
        self.available: float = self.config.initial_capital
        self.frozen: float = 0.0
        
        # 持仓
        self.positions: Dict[str, PaperPosition] = {}
        
        # 订单
        self.orders: Dict[str, PaperOrder] = {}
        self.active_orders: Dict[str, PaperOrder] = {}
        
        # 成交
        self.trades: List[PaperTrade] = []
        
        # 统计
        self._order_count: int = 0
        self._trade_count: int = 0
        self.total_commission: float = 0.0
        self.total_slippage: float = 0.0
        
        # 回调
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)
    
    def send_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> str:
        """
        发送订单
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            offset: 开平
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        # 生成订单ID
        self._order_count += 1
        vt_orderid = f"PAPER.{self._order_count:08d}"
        
        # 创建订单
        order = PaperOrder(
            vt_orderid=vt_orderid,
            vt_symbol=vt_symbol,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume
        )
        
        # 检查资金
        if offset == Offset.OPEN:
            required_margin = price * volume * self.config.size * self.config.margin_rate
            if required_margin > self.available:
                order.status = OrderStatus.REJECTED
                order.update_time = datetime.now()
                self.orders[vt_orderid] = order
                self._emit("order_rejected", order)
                return vt_orderid
        
        # 提交订单
        order.status = OrderStatus.SUBMITTED
        order.update_time = datetime.now()
        self.orders[vt_orderid] = order
        self.active_orders[vt_orderid] = order
        
        self._emit("order_submitted", order)
        
        return vt_orderid
    
    def cancel_order(self, vt_orderid: str) -> bool:
        """
        撤销订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            是否成功
        """
        order = self.active_orders.get(vt_orderid)
        if not order:
            return False
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            return False
        
        order.status = OrderStatus.CANCELLED
        order.update_time = datetime.now()
        
        del self.active_orders[vt_orderid]
        
        self._emit("order_cancelled", order)
        
        return True
    
    def cancel_all(self) -> int:
        """
        撤销所有订单
        
        Returns:
            撤销的订单数量
        """
        count = 0
        for vt_orderid in list(self.active_orders.keys()):
            if self.cancel_order(vt_orderid):
                count += 1
        return count
    
    def process_trade(
        self,
        vt_orderid: str,
        trade_price: float,
        trade_volume: float
    ) -> Optional[PaperTrade]:
        """
        处理成交
        
        Args:
            vt_orderid: 订单ID
            trade_price: 成交价格
            trade_volume: 成交数量
            
        Returns:
            成交记录
        """
        order = self.active_orders.get(vt_orderid)
        if not order:
            return None
        
        # 生成成交ID
        self._trade_count += 1
        vt_tradeid = f"PAPER.{self._trade_count:08d}"
        
        # 创建成交
        trade = PaperTrade(
            vt_tradeid=vt_tradeid,
            vt_orderid=vt_orderid,
            vt_symbol=order.vt_symbol,
            direction=order.direction,
            offset=order.offset,
            price=trade_price,
            volume=trade_volume
        )
        
        self.trades.append(trade)
        
        # 更新订单
        order.traded += trade_volume
        if order.traded >= order.volume:
            order.status = OrderStatus.FILLED
            del self.active_orders[vt_orderid]
        else:
            order.status = OrderStatus.PARTIAL
        order.update_time = datetime.now()
        
        # 更新持仓
        self._update_position(trade)
        
        # 计算费用
        turnover = trade_price * trade_volume * self.config.size
        commission = turnover * self.config.commission_rate
        slippage_cost = trade_price * trade_volume * self.config.slippage * self.config.size
        
        self.total_commission += commission
        self.total_slippage += slippage_cost
        
        # 更新资金
        if order.offset == Offset.OPEN:
            # 开仓，冻结保证金
            margin = turnover * self.config.margin_rate
            self.frozen += margin
        else:
            # 平仓，释放保证金
            margin = turnover * self.config.margin_rate
            self.frozen = max(0, self.frozen - margin)
        
        self.available = self.balance - self.frozen - commission - slippage_cost
        
        self._emit("trade", trade)
        self._emit("order_update", order)
        
        return trade
    
    def _update_position(self, trade: PaperTrade) -> None:
        """更新持仓"""
        vt_symbol = trade.vt_symbol
        
        if vt_symbol not in self.positions:
            self.positions[vt_symbol] = PaperPosition(
                vt_symbol=vt_symbol,
                direction=Direction.LONG if trade.volume > 0 else Direction.SHORT
            )
        
        position = self.positions[vt_symbol]
        
        if trade.offset == Offset.OPEN:
            # 开仓
            volume = trade.volume if trade.direction == Direction.LONG else -trade.volume
            position.update(volume, trade.price)
        else:
            # 平仓
            volume = -trade.volume if trade.direction == Direction.LONG else trade.volume
            position.update(volume, trade.price)
            
            # 如果持仓为0，移除
            if abs(position.volume) < 0.0001:
                del self.positions[vt_symbol]
    
    def update_position_pnl(self, vt_symbol: str, current_price: float) -> float:
        """
        更新持仓盈亏
        
        Args:
            vt_symbol: 合约代码
            current_price: 当前价格
            
        Returns:
            浮动盈亏
        """
        position = self.positions.get(vt_symbol)
        if not position:
            return 0.0
        
        pnl = position.calculate_pnl(current_price)
        position.pnl = pnl
        
        return pnl
    
    def get_position(self, vt_symbol: str) -> Optional[PaperPosition]:
        """获取持仓"""
        return self.positions.get(vt_symbol)
    
    def get_all_positions(self) -> Dict[str, PaperPosition]:
        """获取所有持仓"""
        return self.positions.copy()
    
    def get_order(self, vt_orderid: str) -> Optional[PaperOrder]:
        """获取订单"""
        return self.orders.get(vt_orderid)
    
    def get_active_orders(self) -> Dict[str, PaperOrder]:
        """获取活跃订单"""
        return self.active_orders.copy()
    
    def get_account_data(self) -> AccountData:
        """获取账户数据"""
        return AccountData(
            accountid="PAPER",
            balance=self.balance,
            frozen=self.frozen,
            available=self.available,
            gateway_name="PAPER"
        )
    
    def get_position_data(self, vt_symbol: str) -> Optional[PositionData]:
        """获取持仓数据"""
        position = self.positions.get(vt_symbol)
        if not position:
            return None
        
        symbol, exchange = vt_symbol.split(".")
        
        pos_data = PositionData(
            symbol=symbol,
            exchange=Exchange(exchange),
            direction=position.direction,
            volume=abs(position.volume),
            price=position.price,
            pnl=position.pnl,
            gateway_name="PAPER"
        )
        pos_data.vt_symbol = vt_symbol
        pos_data.vt_positionid = f"{vt_symbol}.{position.direction.value}"
        
        return pos_data
    
    def get_all_position_data(self) -> List[PositionData]:
        """获取所有持仓数据"""
        return [self.get_position_data(vt_symbol) for vt_symbol in self.positions.keys()]
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        total_trades = len(self.trades)
        
        # 计算盈亏
        realized_pnl = sum(
            trade.price * trade.volume * (1 if trade.direction == Direction.LONG else -1)
            for trade in self.trades
            if trade.offset == Offset.CLOSE
        )
        
        unrealized_pnl = sum(pos.pnl for pos in self.positions.values())
        
        return {
            "balance": self.balance,
            "available": self.available,
            "frozen": self.frozen,
            "total_trades": total_trades,
            "total_orders": len(self.orders),
            "active_orders": len(self.active_orders),
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": realized_pnl + unrealized_pnl - self.total_commission - self.total_slippage,
            "position_count": len(self.positions),
        }
