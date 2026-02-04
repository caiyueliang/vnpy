"""
消息队列基类

定义统一的消息队列接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import json
import uuid


class MessageType(Enum):
    """消息类型"""
    TRADE = "trade"                    # 交易消息
    ORDER = "order"                    # 订单消息
    MARKET_DATA = "market_data"        # 行情数据
    SIGNAL = "signal"                  # 策略信号
    RISK_ALERT = "risk_alert"          # 风险告警
    SYSTEM = "system"                  # 系统消息
    LOG = "log"                        # 日志消息
    HEARTBEAT = "heartbeat"            # 心跳消息


@dataclass
class Message:
    """
    消息数据结构
    
    统一的消息格式，支持序列化和反序列化
    """
    msg_type: MessageType              # 消息类型
    payload: Dict[str, Any]            # 消息内容
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""                   # 消息来源
    target: str = ""                   # 消息目标（空表示广播）
    priority: int = 0                  # 优先级（0-9，数字越大优先级越高）
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        data = {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "target": self.target,
            "priority": self.priority
        }
        return json.dumps(data, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """从JSON字符串解析"""
        data = json.loads(json_str)
        return cls(
            msg_id=data["msg_id"],
            msg_type=MessageType(data["msg_type"]),
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data.get("source", ""),
            target=data.get("target", ""),
            priority=data.get("priority", 0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "target": self.target,
            "priority": self.priority
        }


@dataclass
class QueueConfig:
    """队列配置"""
    host: str = "localhost"
    port: int = 5672                    # RabbitMQ默认端口
    username: str = "guest"
    password: str = "guest"
    virtual_host: str = "/"
    
    # 连接池配置
    connection_timeout: int = 30
    heartbeat: int = 60
    
    # 重试配置
    retry_times: int = 3
    retry_delay: float = 1.0
    
    # 队列配置
    durable: bool = True                # 持久化队列
    auto_delete: bool = False           # 不自动删除
    
    # 消息确认
    auto_ack: bool = False              # 手动确认
    prefetch_count: int = 1             # 预取数量
    
    # 额外参数
    extra_params: Dict[str, Any] = field(default_factory=dict)


class MessageQueue(ABC):
    """
    消息队列基类
    
    所有具体消息队列实现必须继承此类
    """
    
    def __init__(self, config: QueueConfig) -> None:
        """Constructor"""
        self.config = config
        self._connected = False
        self._callbacks: Dict[MessageType, List[Callable[[Message], None]]] = {}
        self._consumer_tags: List[str] = []
        
        # 统计信息
        self._published_count = 0
        self._consumed_count = 0
        self._error_count = 0
    
    @abstractmethod
    def connect(self) -> bool:
        """
        连接消息队列
        
        Returns:
            是否连接成功
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass
    
    @abstractmethod
    def publish(
        self,
        message: Message,
        routing_key: str = "",
        exchange: str = ""
    ) -> bool:
        """
        发布消息
        
        Args:
            message: 消息对象
            routing_key: 路由键
            exchange: 交换机名称
            
        Returns:
            是否发布成功
        """
        pass
    
    @abstractmethod
    def subscribe(
        self,
        queue_name: str,
        msg_type: MessageType,
        callback: Callable[[Message], None],
        auto_ack: bool = False
    ) -> bool:
        """
        订阅消息
        
        Args:
            queue_name: 队列名称
            msg_type: 消息类型
            callback: 回调函数
            auto_ack: 是否自动确认
            
        Returns:
            是否订阅成功
        """
        pass
    
    @abstractmethod
    def unsubscribe(self, queue_name: str) -> bool:
        """
        取消订阅
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否取消成功
        """
        pass
    
    @abstractmethod
    def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        auto_delete: bool = False
    ) -> bool:
        """
        声明队列
        
        Args:
            queue_name: 队列名称
            durable: 是否持久化
            auto_delete: 是否自动删除
            
        Returns:
            是否声明成功
        """
        pass
    
    @abstractmethod
    def delete_queue(self, queue_name: str) -> bool:
        """
        删除队列
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    def get_queue_info(self, queue_name: str) -> Dict[str, Any]:
        """
        获取队列信息
        
        Args:
            queue_name: 队列名称
            
        Returns:
            队列信息字典
        """
        pass
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected
    
    def register_callback(
        self,
        msg_type: MessageType,
        callback: Callable[[Message], None]
    ) -> None:
        """
        注册回调函数
        
        Args:
            msg_type: 消息类型
            callback: 回调函数
        """
        if msg_type not in self._callbacks:
            self._callbacks[msg_type] = []
        if callback not in self._callbacks[msg_type]:
            self._callbacks[msg_type].append(callback)
    
    def unregister_callback(
        self,
        msg_type: MessageType,
        callback: Callable[[Message], None]
    ) -> None:
        """
        注销回调函数
        
        Args:
            msg_type: 消息类型
            callback: 回调函数
        """
        if msg_type in self._callbacks and callback in self._callbacks[msg_type]:
            self._callbacks[msg_type].remove(callback)
    
    def _trigger_callbacks(self, message: Message) -> None:
        """
        触发回调函数
        
        Args:
            message: 消息对象
        """
        callbacks = self._callbacks.get(message.msg_type, [])
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                self._error_count += 1
                print(f"回调执行失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "connected": self._connected,
            "published": self._published_count,
            "consumed": self._consumed_count,
            "errors": self._error_count,
            "callbacks_registered": sum(len(cbs) for cbs in self._callbacks.values())
        }
    
    def create_trade_message(
        self,
        symbol: str,
        action: str,
        volume: float,
        price: float,
        **kwargs
    ) -> Message:
        """
        创建交易消息
        
        Args:
            symbol: 合约代码
            action: 动作（buy/sell）
            volume: 数量
            price: 价格
            **kwargs: 其他参数
            
        Returns:
            交易消息
        """
        payload = {
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "price": price,
            **kwargs
        }
        return Message(
            msg_type=MessageType.TRADE,
            payload=payload,
            source=kwargs.get("source", "")
        )
    
    def create_signal_message(
        self,
        strategy_name: str,
        symbol: str,
        signal: str,
        strength: float,
        **kwargs
    ) -> Message:
        """
        创建信号消息
        
        Args:
            strategy_name: 策略名称
            symbol: 合约代码
            signal: 信号类型
            strength: 信号强度
            **kwargs: 其他参数
            
        Returns:
            信号消息
        """
        payload = {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "signal": signal,
            "strength": strength,
            **kwargs
        }
        return Message(
            msg_type=MessageType.SIGNAL,
            payload=payload,
            source=strategy_name
        )
    
    def create_risk_alert_message(
        self,
        alert_type: str,
        level: str,
        description: str,
        **kwargs
    ) -> Message:
        """
        创建风险告警消息
        
        Args:
            alert_type: 告警类型
            level: 告警级别
            description: 描述
            **kwargs: 其他参数
            
        Returns:
            风险告警消息
        """
        payload = {
            "alert_type": alert_type,
            "level": level,
            "description": description,
            **kwargs
        }
        return Message(
            msg_type=MessageType.RISK_ALERT,
            payload=payload,
            priority=9  # 风险告警最高优先级
        )
