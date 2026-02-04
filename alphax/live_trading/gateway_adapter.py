"""
网关适配器模块

提供统一的接口适配不同券商的交易网关
支持vnpy原生网关和自定义网关
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union
import threading
import time

from vnpy.trader.object import (
    TickData, OrderData, TradeData, PositionData, AccountData,
    ContractData, OrderRequest, CancelRequest, SubscribeRequest
)
from vnpy.trader.constant import Direction, Offset, OrderType, Exchange, Status
from vnpy.trader.gateway import BaseGateway
from vnpy.event import Event, EventEngine


class GatewayState(Enum):
    """网关状态"""
    DISCONNECTED = "disconnected"      # 未连接
    CONNECTING = "connecting"          # 连接中
    CONNECTED = "connected"            # 已连接
    AUTHENTICATING = "authenticating"  # 认证中
    AUTHENTICATED = "authenticated"    # 已认证
    READY = "ready"                    # 就绪
    ERROR = "error"                    # 错误
    RECONNECTING = "reconnecting"      # 重连中


class GatewayType(Enum):
    """网关类型"""
    CTP = "ctp"                        # CTP期货
    XTP = "xtp"                        # XTP股票
    OES = "oes"                        # OES
    TORA = "tora"                      # 华鑫TORA
    DBF = "dbf"                        # DBF
    REM = "rem"                        # REM
    CUSTOM = "custom"                  # 自定义


@dataclass
class GatewayConfig:
    """网关配置"""
    # 基本信息
    gateway_type: GatewayType
    gateway_name: str
    
    # 连接配置
    user_id: str = ""
    password: str = ""
    broker_id: str = ""
    
    # 服务器地址
    front_address: str = ""            # 前置机地址
    md_address: str = ""               # 行情地址
    td_address: str = ""               # 交易地址
    
    # 认证配置
    auth_code: str = ""                # 认证码
    app_id: str = ""                   # 应用ID
    
    # 重连配置
    auto_reconnect: bool = True
    reconnect_interval: int = 5        # 重连间隔（秒）
    max_reconnect_attempts: int = 10   # 最大重连次数
    
    # 超时配置
    connect_timeout: int = 30          # 连接超时（秒）
    request_timeout: int = 10          # 请求超时（秒）
    
    # 其他配置
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayStatus:
    """网关状态信息"""
    state: GatewayState = GatewayState.DISCONNECTED
    connected_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    error_message: str = ""
    reconnect_count: int = 0
    
    # 统计数据
    orders_sent: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0


class GatewayAdapter:
    """
    网关适配器
    
    统一封装不同券商网关的接口，提供一致的操作方式
    """
    
    def __init__(
        self,
        event_engine: EventEngine,
        config: GatewayConfig
    ) -> None:
        """
        构造函数
        
        Args:
            event_engine: 事件引擎
            config: 网关配置
        """
        self.event_engine = event_engine
        self.config = config
        self.status = GatewayStatus()
        
        # 底层网关实例
        self._gateway: Optional[BaseGateway] = None
        self._gateway_class: Optional[Type[BaseGateway]] = None
        
        # 回调函数注册
        self._callbacks: Dict[str, List[Callable]] = {
            "on_tick": [],
            "on_order": [],
            "on_trade": [],
            "on_position": [],
            "on_account": [],
            "on_contract": [],
            "on_log": [],
            "on_error": [],
            "on_state_change": [],
        }
        
        # 数据缓存
        self._ticks: Dict[str, TickData] = {}
        self._orders: Dict[str, OrderData] = {}
        self._trades: Dict[str, TradeData] = {}
        self._positions: Dict[str, PositionData] = {}
        self._accounts: Dict[str, AccountData] = {}
        self._contracts: Dict[str, ContractData] = {}
        
        # 锁
        self._lock = threading.RLock()
        
        # 重连线程
        self._reconnect_thread: Optional[threading.Thread] = None
        self._stop_reconnect = threading.Event()
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """
        注册回调函数
        
        Args:
            event: 事件类型
            callback: 回调函数
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def unregister_callback(self, event: str, callback: Callable) -> None:
        """
        注销回调函数
        
        Args:
            event: 事件类型
            callback: 回调函数
        """
        if event in self._callbacks and callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发回调"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"回调执行失败: {e}")
    
    def _set_state(self, state: GatewayState, error_message: str = "") -> None:
        """
        设置网关状态
        
        Args:
            state: 新状态
            error_message: 错误信息
        """
        old_state = self.status.state
        self.status.state = state
        self.status.last_activity = datetime.now()
        
        if error_message:
            self.status.error_message = error_message
        
        if state == GatewayState.CONNECTED:
            self.status.connected_at = datetime.now()
            self.status.reconnect_count = 0
        
        self._emit("on_state_change", old_state, state, error_message)
    
    def load_gateway(self, gateway_class: Type[BaseGateway]) -> bool:
        """
        加载网关类
        
        Args:
            gateway_class: 网关类
            
        Returns:
            是否加载成功
        """
        try:
            self._gateway_class = gateway_class
            self._gateway = gateway_class(self.event_engine, self.config.gateway_name)
            
            # 设置事件回调
            self._setup_event_handlers()
            
            return True
        except Exception as e:
            self._set_state(GatewayState.ERROR, str(e))
            return False
    
    def _setup_event_handlers(self) -> None:
        """设置事件处理器"""
        if not self._gateway:
            return
        
        # 注册事件监听
        self.event_engine.register("on_tick", self._on_tick)
        self.event_engine.register("on_order", self._on_order)
        self.event_engine.register("on_trade", self._on_trade)
        self.event_engine.register("on_position", self._on_position)
        self.event_engine.register("on_account", self._on_account)
        self.event_engine.register("on_contract", self._on_contract)
        self.event_engine.register("on_log", self._on_log)
    
    def _on_tick(self, event: Event) -> None:
        """Tick数据处理"""
        tick: TickData = event.data
        with self._lock:
            self._ticks[tick.vt_symbol] = tick
        self._emit("on_tick", tick)
    
    def _on_order(self, event: Event) -> None:
        """订单数据处理"""
        order: OrderData = event.data
        with self._lock:
            self._orders[order.vt_orderid] = order
            
            # 更新统计
            if order.status == Status.ALLTRADED:
                self.status.orders_filled += 1
            elif order.status == Status.CANCELLED:
                self.status.orders_cancelled += 1
            elif order.status == Status.REJECTED:
                self.status.orders_rejected += 1
        
        self._emit("on_order", order)
    
    def _on_trade(self, event: Event) -> None:
        """成交数据处理"""
        trade: TradeData = event.data
        with self._lock:
            self._trades[trade.vt_tradeid] = trade
        self._emit("on_trade", trade)
    
    def _on_position(self, event: Event) -> None:
        """持仓数据处理"""
        position: PositionData = event.data
        with self._lock:
            self._positions[position.vt_positionid] = position
        self._emit("on_position", position)
    
    def _on_account(self, event: Event) -> None:
        """账户数据处理"""
        account: AccountData = event.data
        with self._lock:
            self._accounts[account.vt_accountid] = account
        self._emit("on_account", account)
    
    def _on_contract(self, event: Event) -> None:
        """合约数据处理"""
        contract: ContractData = event.data
        with self._lock:
            self._contracts[contract.vt_symbol] = contract
        self._emit("on_contract", contract)
    
    def _on_log(self, event: Event) -> None:
        """日志处理"""
        log = event.data
        self._emit("on_log", log)
    
    def connect(self) -> bool:
        """
        连接网关
        
        Returns:
            是否连接成功
        """
        if not self._gateway:
            self._set_state(GatewayState.ERROR, "网关未加载")
            return False
        
        if self.status.state in [GatewayState.CONNECTED, GatewayState.READY]:
            return True
        
        self._set_state(GatewayState.CONNECTING)
        
        try:
            # 构建连接配置
            setting = self._build_connection_setting()
            
            # 连接网关
            self._gateway.connect(setting)
            
            self._set_state(GatewayState.CONNECTED)
            
            # 启动重连线程
            if self.config.auto_reconnect:
                self._start_reconnect_thread()
            
            return True
            
        except Exception as e:
            self._set_state(GatewayState.ERROR, str(e))
            return False
    
    def _build_connection_setting(self) -> Dict[str, Any]:
        """
        构建连接配置
        
        Returns:
            连接配置字典
        """
        setting = {
            "用户名": self.config.user_id,
            "密码": self.config.password,
            "经纪商代码": self.config.broker_id,
            "交易服务器": self.config.td_address,
            "行情服务器": self.config.md_address,
            "产品名称": self.config.app_id,
            "授权编码": self.config.auth_code,
        }
        
        # 添加额外配置
        setting.update(self.config.extra)
        
        return setting
    
    def disconnect(self) -> None:
        """断开连接"""
        self._stop_reconnect.set()
        
        if self._gateway:
            try:
                self._gateway.close()
            except Exception as e:
                print(f"关闭网关失败: {e}")
        
        self._set_state(GatewayState.DISCONNECTED)
    
    def _start_reconnect_thread(self) -> None:
        """启动重连线程"""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        
        self._stop_reconnect.clear()
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_worker,
            daemon=True
        )
        self._reconnect_thread.start()
    
    def _reconnect_worker(self) -> None:
        """重连工作线程"""
        while not self._stop_reconnect.is_set():
            time.sleep(self.config.reconnect_interval)
            
            if self.status.state == GatewayState.DISCONNECTED:
                if self.status.reconnect_count < self.config.max_reconnect_attempts:
                    self.status.reconnect_count += 1
                    self._set_state(GatewayState.RECONNECTING)
                    
                    if not self.connect():
                        print(f"重连失败 ({self.status.reconnect_count}/{self.config.max_reconnect_attempts})")
    
    def subscribe(self, vt_symbol: str) -> bool:
        """
        订阅行情
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            是否订阅成功
        """
        if not self._gateway or self.status.state != GatewayState.CONNECTED:
            return False
        
        try:
            symbol, exchange_str = vt_symbol.split(".")
            exchange = Exchange(exchange_str)
            
            req = SubscribeRequest(symbol=symbol, exchange=exchange)
            self._gateway.subscribe(req)
            
            return True
        except Exception as e:
            print(f"订阅失败: {e}")
            return False
    
    def send_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        order_type: OrderType = OrderType.LIMIT,
        reference: str = ""
    ) -> str:
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
            
        Returns:
            订单ID
        """
        if not self._gateway or self.status.state != GatewayState.CONNECTED:
            return ""
        
        try:
            symbol, exchange_str = vt_symbol.split(".")
            exchange = Exchange(exchange_str)
            
            req = OrderRequest(
                symbol=symbol,
                exchange=exchange,
                direction=direction,
                type=order_type,
                volume=volume,
                price=price,
                offset=offset,
                reference=reference
            )
            
            vt_orderid = self._gateway.send_order(req)
            self.status.orders_sent += 1
            
            return vt_orderid
            
        except Exception as e:
            print(f"发送订单失败: {e}")
            return ""
    
    def cancel_order(self, vt_orderid: str) -> bool:
        """
        撤销订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            是否撤销成功
        """
        if not self._gateway or self.status.state != GatewayState.CONNECTED:
            return False
        
        try:
            # 解析订单ID
            gateway_name, orderid = vt_orderid.split(".")
            
            # 获取订单信息
            order = self._orders.get(vt_orderid)
            if not order:
                return False
            
            req = CancelRequest(
                orderid=orderid,
                symbol=order.symbol,
                exchange=order.exchange
            )
            
            self._gateway.cancel_order(req)
            return True
            
        except Exception as e:
            print(f"撤销订单失败: {e}")
            return False
    
    def query_account(self) -> bool:
        """
        查询账户
        
        Returns:
            是否查询成功
        """
        if not self._gateway or self.status.state != GatewayState.CONNECTED:
            return False
        
        try:
            self._gateway.query_account()
            return True
        except Exception as e:
            print(f"查询账户失败: {e}")
            return False
    
    def query_position(self) -> bool:
        """
        查询持仓
        
        Returns:
            是否查询成功
        """
        if not self._gateway or self.status.state != GatewayState.CONNECTED:
            return False
        
        try:
            self._gateway.query_position()
            return True
        except Exception as e:
            print(f"查询持仓失败: {e}")
            return False
    
    def get_tick(self, vt_symbol: str) -> Optional[TickData]:
        """
        获取最新Tick
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            Tick数据
        """
        with self._lock:
            return self._ticks.get(vt_symbol)
    
    def get_order(self, vt_orderid: str) -> Optional[OrderData]:
        """
        获取订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            订单数据
        """
        with self._lock:
            return self._orders.get(vt_orderid)
    
    def get_trade(self, vt_tradeid: str) -> Optional[TradeData]:
        """
        获取成交
        
        Args:
            vt_tradeid: 成交ID
            
        Returns:
            成交数据
        """
        with self._lock:
            return self._trades.get(vt_tradeid)
    
    def get_position(self, vt_positionid: str) -> Optional[PositionData]:
        """
        获取持仓
        
        Args:
            vt_positionid: 持仓ID
            
        Returns:
            持仓数据
        """
        with self._lock:
            return self._positions.get(vt_positionid)
    
    def get_account(self, vt_accountid: str) -> Optional[AccountData]:
        """
        获取账户
        
        Args:
            vt_accountid: 账户ID
            
        Returns:
            账户数据
        """
        with self._lock:
            return self._accounts.get(vt_accountid)
    
    def get_contract(self, vt_symbol: str) -> Optional[ContractData]:
        """
        获取合约
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            合约数据
        """
        with self._lock:
            return self._contracts.get(vt_symbol)
    
    def get_all_positions(self) -> List[PositionData]:
        """
        获取所有持仓
        
        Returns:
            持仓列表
        """
        with self._lock:
            return list(self._positions.values())
    
    def get_all_accounts(self) -> List[AccountData]:
        """
        获取所有账户
        
        Returns:
            账户列表
        """
        with self._lock:
            return list(self._accounts.values())
    
    def get_active_orders(self) -> List[OrderData]:
        """
        获取活跃订单
        
        Returns:
            活跃订单列表
        """
        with self._lock:
            return [
                order for order in self._orders.values()
                if order.is_active()
            ]
    
    def is_ready(self) -> bool:
        """
        检查网关是否就绪
        
        Returns:
            是否就绪
        """
        return self.status.state == GatewayState.CONNECTED
    
    def get_status(self) -> GatewayStatus:
        """
        获取网关状态
        
        Returns:
            网关状态
        """
        return self.status
