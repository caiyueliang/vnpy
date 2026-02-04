"""
实盘交易引擎

整合网关适配器、订单管理、持仓管理和资金管理，提供完整的实盘交易功能
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type
import threading

from vnpy.event import EventEngine
from vnpy.trader.object import (
    TickData, OrderData, TradeData, PositionData, AccountData
)
from vnpy.trader.constant import Direction, Offset, OrderType
from vnpy.trader.gateway import BaseGateway

from .gateway_adapter import GatewayAdapter, GatewayConfig, GatewayState
from .order_manager import OrderManager, OrderConfig, OrderRecord
from .position_manager import PositionManager, PositionConfig
from .account_manager import AccountManager, AccountConfig


@dataclass
class LiveTradingConfig:
    """实盘交易配置"""
    # 网关配置
    gateway_config: Optional[GatewayConfig] = None
    
    # 各模块配置
    order_config: Optional[OrderConfig] = None
    position_config: Optional[PositionConfig] = None
    account_config: Optional[AccountConfig] = None
    
    # 自动操作配置
    auto_subscribe: bool = True          # 自动订阅行情
    auto_query: bool = True              # 自动查询账户和持仓
    
    # 风控配置
    enable_risk_check: bool = True       # 启用风控检查


class LiveTradingEngine:
    """
    实盘交易引擎
    
    提供完整的实盘交易功能，包括：
    - 网关连接管理
    - 订单生命周期管理
    - 持仓跟踪
    - 资金监控
    - 风险控制
    """
    
    def __init__(
        self,
        event_engine: EventEngine,
        config: Optional[LiveTradingConfig] = None
    ) -> None:
        """
        构造函数
        
        Args:
            event_engine: 事件引擎
            config: 实盘交易配置
        """
        self.event_engine = event_engine
        self.config = config or LiveTradingConfig()
        
        # 初始化各模块
        self.gateway: Optional[GatewayAdapter] = None
        self.order_manager = OrderManager(self.config.order_config)
        self.position_manager = PositionManager(self.config.position_config)
        self.account_manager = AccountManager(self.config.account_config)
        
        # 状态
        self._started = False
        self._ready = False
        
        # 回调函数
        self._callbacks: Dict[str, List[Callable]] = {
            "on_ready": [],
            "on_disconnected": [],
            "on_error": [],
            "on_trade": [],
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
                print(f"实盘引擎回调执行失败: {e}")
    
    def initialize(
        self,
        gateway_class: Type[BaseGateway],
        gateway_config: Optional[GatewayConfig] = None
    ) -> bool:
        """
        初始化引擎
        
        Args:
            gateway_class: 网关类
            gateway_config: 网关配置（None则使用默认配置）
            
        Returns:
            是否初始化成功
        """
        try:
            config = gateway_config or self.config.gateway_config
            if not config:
                print("网关配置未提供")
                return False
            
            # 创建网关适配器
            self.gateway = GatewayAdapter(self.event_engine, config)
            
            # 加载网关
            if not self.gateway.load_gateway(gateway_class):
                print("加载网关失败")
                return False
            
            # 设置网关回调
            self._setup_gateway_callbacks()
            
            return True
            
        except Exception as e:
            print(f"初始化引擎失败: {e}")
            return False
    
    def _setup_gateway_callbacks(self) -> None:
        """设置网关回调"""
        if not self.gateway:
            return
        
        # 注册网关事件回调
        self.gateway.register_callback("on_tick", self._on_tick)
        self.gateway.register_callback("on_order", self._on_order)
        self.gateway.register_callback("on_trade", self._on_trade)
        self.gateway.register_callback("on_position", self._on_position)
        self.gateway.register_callback("on_account", self._on_account)
        self.gateway.register_callback("on_state_change", self._on_gateway_state_change)
    
    def start(self) -> bool:
        """
        启动引擎
        
        Returns:
            是否启动成功
        """
        with self._lock:
            if self._started:
                return True
            
            if not self.gateway:
                print("引擎未初始化")
                return False
            
            # 连接网关
            if not self.gateway.connect():
                print("连接网关失败")
                return False
            
            # 启动订单管理器
            self.order_manager.start()
            
            self._started = True
            
            return True
    
    def stop(self) -> None:
        """停止引擎"""
        with self._lock:
            if not self._started:
                return
            
            # 撤销所有活跃订单
            self.cancel_all_orders()
            
            # 停止订单管理器
            self.order_manager.stop()
            
            # 断开网关
            if self.gateway:
                self.gateway.disconnect()
            
            self._started = False
            self._ready = False
    
    def _on_tick(self, tick: TickData) -> None:
        """处理Tick数据"""
        # 更新持仓盈亏
        self.position_manager.on_tick(tick)
    
    def _on_order(self, order: OrderData) -> None:
        """处理订单更新"""
        self.order_manager.on_order_update(order)
    
    def _on_trade(self, trade: TradeData) -> None:
        """处理成交"""
        # 更新订单
        self.order_manager.on_trade_update(trade)
        
        # 更新持仓
        self.position_manager.on_trade(trade)
        
        # 触发回调
        self._emit("on_trade", trade)
    
    def _on_position(self, position: PositionData) -> None:
        """处理持仓更新"""
        self.position_manager.on_position_update(position)
    
    def _on_account(self, account: AccountData) -> None:
        """处理账户更新"""
        self.account_manager.on_account_update(account)
        
        # 更新持仓管理器的总资产
        total_balance = self.account_manager.get_total_balance()
        self.position_manager.set_total_asset(total_balance)
    
    def _on_gateway_state_change(
        self,
        old_state: GatewayState,
        new_state: GatewayState,
        error_message: str
    ) -> None:
        """处理网关状态变化"""
        if new_state == GatewayState.CONNECTED:
            self._on_gateway_connected()
        elif new_state == GatewayState.DISCONNECTED:
            self._ready = False
            self._emit("on_disconnected")
        elif new_state == GatewayState.ERROR:
            self._emit("on_error", error_message)
    
    def _on_gateway_connected(self) -> None:
        """网关连接成功处理"""
        # 查询账户和持仓
        if self.config.auto_query:
            if self.gateway:
                self.gateway.query_account()
                self.gateway.query_position()
        
        self._ready = True
        self._emit("on_ready")
    
    def subscribe(self, vt_symbol: str) -> bool:
        """
        订阅行情
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            是否订阅成功
        """
        if not self.gateway:
            return False
        
        return self.gateway.subscribe(vt_symbol)
    
    def send_order(
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
        发送订单
        
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
            if not self._ready or not self.gateway:
                print("引擎未就绪")
                return None
            
            # 风控检查
            if self.config.enable_risk_check:
                # 检查持仓限制
                if not self.position_manager.check_position_limit(vt_symbol, direction, volume):
                    return None
                
                # 检查资金限制
                order_value = price * volume
                if not self.account_manager.check_fund_limit(order_value):
                    return None
                
                # 检查策略资金限制
                if strategy_name:
                    if not self.account_manager.check_strategy_fund_limit(strategy_name, order_value):
                        return None
            
            # 创建订单记录
            record = self.order_manager.create_order(
                vt_symbol=vt_symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                order_type=order_type,
                reference=reference,
                strategy_name=strategy_name
            )
            
            if not record:
                return None
            
            # 发送订单到网关
            vt_orderid = self.gateway.send_order(
                vt_symbol=vt_symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                order_type=order_type,
                reference=reference
            )
            
            if not vt_orderid:
                # 发送失败，更新订单状态
                record.stage = "failed"
                return None
            
            # 更新订单ID
            record.vt_orderid = vt_orderid
            
            # 使用策略资金
            if strategy_name:
                self.account_manager.use_funds(strategy_name, price * volume)
            
            return record
    
    def cancel_order(self, vt_orderid: str) -> bool:
        """
        撤销订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            是否撤销成功
        """
        if not self.gateway:
            return False
        
        # 更新订单管理器
        self.order_manager.cancel_order(vt_orderid)
        
        # 发送到网关
        return self.gateway.cancel_order(vt_orderid)
    
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
        # 获取要撤销的订单
        cancelled = self.order_manager.cancel_all_orders(vt_symbol, strategy_name)
        
        # 发送到网关
        if self.gateway:
            for vt_orderid in cancelled:
                self.gateway.cancel_order(vt_orderid)
        
        return cancelled
    
    def get_order(self, vt_orderid: str) -> Optional[OrderRecord]:
        """
        获取订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            订单记录
        """
        return self.order_manager.get_order(vt_orderid)
    
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
        return self.order_manager.get_active_orders(vt_symbol, strategy_name)
    
    def get_position(self, vt_positionid: str):
        """
        获取持仓
        
        Args:
            vt_positionid: 持仓ID
            
        Returns:
            持仓记录
        """
        return self.position_manager.get_position(vt_positionid)
    
    def get_net_position(self, vt_symbol: str) -> float:
        """
        获取净持仓
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            净持仓数量
        """
        return self.position_manager.get_net_position(vt_symbol)
    
    def get_all_positions(self):
        """
        获取所有持仓
        
        Returns:
            持仓列表
        """
        return self.position_manager.get_all_positions()
    
    def get_account(self, vt_accountid: str):
        """
        获取账户
        
        Args:
            vt_accountid: 账户ID
            
        Returns:
            账户记录
        """
        return self.account_manager.get_account(vt_accountid)
    
    def get_total_balance(self) -> float:
        """
        获取总权益
        
        Returns:
            总权益
        """
        return self.account_manager.get_total_balance()
    
    def get_total_available(self) -> float:
        """
        获取总可用资金
        
        Returns:
            总可用资金
        """
        return self.account_manager.get_total_available()
    
    def allocate_funds(self, strategy_name: str, amount: float) -> bool:
        """
        分配资金给策略
        
        Args:
            strategy_name: 策略名称
            amount: 分配金额
            
        Returns:
            是否分配成功
        """
        return self.account_manager.allocate_funds(strategy_name, amount)
    
    def release_funds(self, strategy_name: str, amount: float) -> bool:
        """
        释放策略资金
        
        Args:
            strategy_name: 策略名称
            amount: 释放金额
            
        Returns:
            是否释放成功
        """
        return self.account_manager.release_funds(strategy_name, amount)
    
    def is_ready(self) -> bool:
        """
        检查引擎是否就绪
        
        Returns:
            是否就绪
        """
        return self._ready
    
    def is_started(self) -> bool:
        """
        检查引擎是否已启动
        
        Returns:
            是否已启动
        """
        return self._started
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取引擎状态
        
        Returns:
            状态字典
        """
        return {
            "started": self._started,
            "ready": self._ready,
            "gateway_status": self.gateway.get_status() if self.gateway else None,
            "order_stats": self.order_manager.get_statistics(),
            "position_summary": {
                "total_value": self.position_manager.get_position_value(),
                "total_pnl": self.position_manager.get_total_pnl(),
                "position_ratio": self.position_manager.get_position_ratio(),
            },
            "account_summary": {
                "total_balance": self.account_manager.get_total_balance(),
                "total_available": self.account_manager.get_total_available(),
                "cash_ratio": self.account_manager.get_cash_ratio(),
            },
        }
    
    def get_full_report(self) -> Dict[str, Any]:
        """
        获取完整报告
        
        Returns:
            完整报告
        """
        return {
            "status": self.get_status(),
            "orders": self.order_manager.get_orders_report(),
            "positions": self.position_manager.get_position_report(),
            "accounts": self.account_manager.get_account_report(),
            "timestamp": datetime.now().isoformat(),
        }
