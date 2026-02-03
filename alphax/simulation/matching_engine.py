"""
模拟撮合引擎

实现订单撮合逻辑，支持多种撮合模式
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from collections import defaultdict
import random

from vnpy.trader.object import BarData, TickData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset

from alphax.simulation.paper_account import PaperAccount, PaperOrder, OrderStatus


class MatchMode(Enum):
    """撮合模式"""
    BAR_OPEN = "bar_open"           # K线开盘价成交
    BAR_CLOSE = "bar_close"         # K线收盘价成交
    BAR_VWAP = "bar_vwap"           # K线VWAP成交
    TICK_LAST = "tick_last"         # Tick最新价成交
    TICK_BEST = "tick_best"         # Tick最优价成交
    DELAYED = "delayed"             # 延迟成交（模拟滑点）


@dataclass
class MatchConfig:
    """撮合配置"""
    mode: MatchMode = MatchMode.BAR_OPEN
    fill_rate: float = 1.0              # 成交率
    partial_fill: bool = True           # 是否允许部分成交
    min_fill_volume: float = 1.0        # 最小成交数量
    price_impact: float = 0.0           # 价格冲击（大单影响）
    random_slippage: bool = False       # 随机滑点
    slippage_std: float = 0.0001        # 滑点标准差


@dataclass
class OrderBookLevel:
    """订单簿档位"""
    price: float
    volume: float


@dataclass
class SimulatedOrderBook:
    """模拟订单簿"""
    vt_symbol: str
    timestamp: datetime
    
    # 买卖盘
    bids: List[OrderBookLevel] = field(default_factory=list)  # 买盘（从高到低）
    asks: List[OrderBookLevel] = field(default_factory=list)  # 卖盘（从低到高）
    
    # 最新成交
    last_price: float = 0.0
    last_volume: float = 0.0
    
    # 统计
    volume: float = 0.0
    turnover: float = 0.0
    
    def get_best_bid(self) -> Optional[OrderBookLevel]:
        """获取最优买价"""
        return self.bids[0] if self.bids else None
    
    def get_best_ask(self) -> Optional[OrderBookLevel]:
        """获取最优卖价"""
        return self.asks[0] if self.asks else None
    
    def get_mid_price(self) -> float:
        """获取中间价"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if best_bid and best_ask:
            return (best_bid.price + best_ask.price) / 2
        elif best_bid:
            return best_bid.price
        elif best_ask:
            return best_ask.price
        return self.last_price


class MatchingEngine:
    """
    撮合引擎
    
    实现订单撮合逻辑，支持K线数据和Tick数据撮合
    """
    
    def __init__(
        self,
        account: PaperAccount,
        config: Optional[MatchConfig] = None
    ) -> None:
        """Constructor"""
        self.account = account
        self.config = config or MatchConfig()
        
        # 当前市场数据
        self.current_bars: Dict[str, BarData] = {}
        self.current_ticks: Dict[str, TickData] = {}
        self.current_orderbooks: Dict[str, SimulatedOrderBook] = {}
        
        # 待撮合订单队列
        self.pending_orders: List[PaperOrder] = []
        
        # 回调
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)
    
    def on_bar(self, vt_symbol: str, bar: BarData) -> None:
        """
        K线数据回调
        
        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        self.current_bars[vt_symbol] = bar
        
        # 生成模拟订单簿
        orderbook = self._generate_orderbook_from_bar(vt_symbol, bar)
        self.current_orderbooks[vt_symbol] = orderbook
        
        # 撮合该品种的订单
        self._match_symbol_orders(vt_symbol)
    
    def on_tick(self, vt_symbol: str, tick: TickData) -> None:
        """
        Tick数据回调
        
        Args:
            vt_symbol: 合约代码
            tick: Tick数据
        """
        self.current_ticks[vt_symbol] = tick
        
        # 生成模拟订单簿
        orderbook = self._generate_orderbook_from_tick(vt_symbol, tick)
        self.current_orderbooks[vt_symbol] = orderbook
        
        # 撮合该品种的订单
        self._match_symbol_orders(vt_symbol)
    
    def _generate_orderbook_from_bar(
        self,
        vt_symbol: str,
        bar: BarData
    ) -> SimulatedOrderBook:
        """从K线生成模拟订单簿"""
        orderbook = SimulatedOrderBook(
            vt_symbol=vt_symbol,
            timestamp=bar.datetime,
            last_price=bar.close_price,
            volume=bar.volume,
            turnover=bar.turnover if hasattr(bar, 'turnover') else bar.volume * bar.close_price
        )
        
        # 根据K线数据模拟买卖盘
        spread = (bar.high_price - bar.low_price) * 0.1  # 假设价差为高低点的10%
        
        # 买盘（从高到低）
        for i in range(5):
            price = bar.close_price - spread * (i + 1) * 0.5
            volume = bar.volume * 0.1 / (i + 1)
            orderbook.bids.append(OrderBookLevel(price=price, volume=volume))
        
        # 卖盘（从低到高）
        for i in range(5):
            price = bar.close_price + spread * (i + 1) * 0.5
            volume = bar.volume * 0.1 / (i + 1)
            orderbook.asks.append(OrderBookLevel(price=price, volume=volume))
        
        # 排序
        orderbook.bids.sort(key=lambda x: x.price, reverse=True)
        orderbook.asks.sort(key=lambda x: x.price)
        
        return orderbook
    
    def _generate_orderbook_from_tick(
        self,
        vt_symbol: str,
        tick: TickData
    ) -> SimulatedOrderBook:
        """从Tick生成模拟订单簿"""
        orderbook = SimulatedOrderBook(
            vt_symbol=vt_symbol,
            timestamp=tick.datetime,
            last_price=tick.last_price,
            volume=tick.volume if hasattr(tick, 'volume') else 0,
            last_volume=tick.last_volume if hasattr(tick, 'last_volume') else 0
        )
        
        # 使用Tick的买卖盘数据
        if hasattr(tick, 'bid_price_1') and tick.bid_price_1 > 0:
            orderbook.bids.append(OrderBookLevel(
                price=tick.bid_price_1,
                volume=tick.bid_volume_1 if hasattr(tick, 'bid_volume_1') else 0
            ))
        
        if hasattr(tick, 'ask_price_1') and tick.ask_price_1 > 0:
            orderbook.asks.append(OrderBookLevel(
                price=tick.ask_price_1,
                volume=tick.ask_volume_1 if hasattr(tick, 'ask_volume_1') else 0
            ))
        
        return orderbook
    
    def _match_symbol_orders(self, vt_symbol: str) -> None:
        """撮合指定品种的订单"""
        orderbook = self.current_orderbooks.get(vt_symbol)
        if not orderbook:
            return
        
        # 获取该品种的活跃订单
        active_orders = [
            order for order in self.account.get_active_orders().values()
            if order.vt_symbol == vt_symbol
        ]
        
        for order in active_orders:
            self._match_order(order, orderbook)
    
    def _match_order(
        self,
        order: PaperOrder,
        orderbook: SimulatedOrderBook
    ) -> bool:
        """
        撮合单个订单
        
        Args:
            order: 订单
            orderbook: 订单簿
            
        Returns:
            是否成交
        """
        # 检查成交率
        if random.random() > self.config.fill_rate:
            return False
        
        # 确定成交价格
        match_price = self._get_match_price(order, orderbook)
        if match_price <= 0:
            return False
        
        # 检查价格是否满足订单条件
        if not self._check_price_condition(order, match_price):
            return False
        
        # 计算成交量
        match_volume = self._calculate_match_volume(order, orderbook)
        if match_volume < self.config.min_fill_volume:
            return False
        
        # 应用价格冲击
        if self.config.price_impact > 0:
            impact = match_volume * self.config.price_impact / orderbook.volume
            if order.direction == Direction.LONG:
                match_price *= (1 + impact)
            else:
                match_price *= (1 - impact)
        
        # 应用随机滑点
        if self.config.random_slippage:
            slippage = random.gauss(0, self.config.slippage_std)
            if order.direction == Direction.LONG:
                match_price *= (1 + abs(slippage))
            else:
                match_price *= (1 - abs(slippage))
        
        # 执行成交
        trade = self.account.process_trade(
            vt_orderid=order.vt_orderid,
            trade_price=match_price,
            trade_volume=match_volume
        )
        
        if trade:
            self._emit("trade", trade)
            return True
        
        return False
    
    def _get_match_price(
        self,
        order: PaperOrder,
        orderbook: SimulatedOrderBook
    ) -> float:
        """获取成交价格"""
        if self.config.mode == MatchMode.BAR_OPEN:
            bar = self.current_bars.get(order.vt_symbol)
            return bar.open_price if bar else 0.0
        
        elif self.config.mode == MatchMode.BAR_CLOSE:
            bar = self.current_bars.get(order.vt_symbol)
            return bar.close_price if bar else 0.0
        
        elif self.config.mode == MatchMode.BAR_VWAP:
            bar = self.current_bars.get(order.vt_symbol)
            if bar and hasattr(bar, 'turnover') and bar.volume > 0:
                return bar.turnover / bar.volume
            return bar.close_price if bar else 0.0
        
        elif self.config.mode == MatchMode.TICK_LAST:
            tick = self.current_ticks.get(order.vt_symbol)
            return tick.last_price if tick else orderbook.last_price
        
        elif self.config.mode == MatchMode.TICK_BEST:
            if order.direction == Direction.LONG:
                best_ask = orderbook.get_best_ask()
                return best_ask.price if best_ask else orderbook.last_price
            else:
                best_bid = orderbook.get_best_bid()
                return best_bid.price if best_bid else orderbook.last_price
        
        elif self.config.mode == MatchMode.DELAYED:
            # 延迟成交，使用下一根K线的开盘价
            return 0.0  # 延迟到下一根K线处理
        
        return orderbook.last_price
    
    def _check_price_condition(self, order: PaperOrder, price: float) -> bool:
        """检查价格条件"""
        # 市价单总是成交
        if order.price <= 0:
            return True
        
        # 限价单检查
        if order.direction == Direction.LONG:
            return price <= order.price
        else:
            return price >= order.price
    
    def _calculate_match_volume(
        self,
        order: PaperOrder,
        orderbook: SimulatedOrderBook
    ) -> float:
        """计算成交量"""
        remaining = order.volume - order.traded
        
        # 获取市场深度
        if order.direction == Direction.LONG:
            market_volume = sum(ask.volume for ask in orderbook.asks)
        else:
            market_volume = sum(bid.volume for bid in orderbook.bids)
        
        # 计算可成交量
        if self.config.partial_fill:
            # 允许部分成交
            max_volume = min(remaining, market_volume * 0.1)  # 最多吃10%的市场深度
            return max_volume
        else:
            # 全部成交或不成
            if remaining <= market_volume * 0.1:
                return remaining
            return 0.0
    
    def add_order(self, order: PaperOrder) -> None:
        """
        添加订单到撮合队列
        
        Args:
            order: 订单
        """
        # 立即尝试撮合
        orderbook = self.current_orderbooks.get(order.vt_symbol)
        if orderbook:
            if self._match_order(order, orderbook):
                return
        
        # 如果未成交，加入待撮合队列
        self.pending_orders.append(order)
    
    def cancel_order(self, vt_orderid: str) -> bool:
        """
        取消订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            是否成功
        """
        # 从待撮合队列中移除
        self.pending_orders = [
            order for order in self.pending_orders
            if order.vt_orderid != vt_orderid
        ]
        
        return True
    
    def process_pending_orders(self) -> None:
        """处理待撮合订单"""
        for order in self.pending_orders[:]:
            orderbook = self.current_orderbooks.get(order.vt_symbol)
            if orderbook:
                if self._match_order(order, orderbook):
                    self.pending_orders.remove(order)
    
    def get_orderbook(self, vt_symbol: str) -> Optional[SimulatedOrderBook]:
        """获取订单簿"""
        return self.current_orderbooks.get(vt_symbol)
    
    def get_market_depth(self, vt_symbol: str, levels: int = 5) -> Dict:
        """
        获取市场深度
        
        Args:
            vt_symbol: 合约代码
            levels: 档位数
            
        Returns:
            市场深度数据
        """
        orderbook = self.current_orderbooks.get(vt_symbol)
        if not orderbook:
            return {"bids": [], "asks": []}
        
        return {
            "bids": [
                {"price": level.price, "volume": level.volume}
                for level in orderbook.bids[:levels]
            ],
            "asks": [
                {"price": level.price, "volume": level.volume}
                for level in orderbook.asks[:levels]
            ],
            "last_price": orderbook.last_price,
            "mid_price": orderbook.get_mid_price()
        }
