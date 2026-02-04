"""
消息总线

统一的消息总线，支持多种消息队列后端：
- RabbitMQ（推荐，功能完整）
- Kafka（高吞吐量场景）
- Redis（简单场景，降级方案）

提供自动降级和故障转移功能
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type
import threading
import time

from .base import MessageQueue, QueueConfig, MessageType, Message
from .rabbitmq_queue import RabbitMQQueue
from .kafka_queue import KafkaQueue
from .redis_queue import RedisQueue


class BackendType(Enum):
    """消息队列后端类型"""
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"
    REDIS = "redis"


class MessageBus:
    """
    消息总线
    
    统一的消息队列接口，支持自动降级和故障转移
    """
    
    # 后端优先级（从高到低）
    BACKEND_PRIORITY = [
        BackendType.RABBITMQ,
        BackendType.KAFKA,
        BackendType.REDIS
    ]
    
    # 后端类映射
    BACKEND_CLASSES: Dict[BackendType, Type[MessageQueue]] = {
        BackendType.RABBITMQ: RabbitMQQueue,
        BackendType.KAFKA: KafkaQueue,
        BackendType.REDIS: RedisQueue
    }
    
    def __init__(self, configs: Optional[Dict[BackendType, QueueConfig]] = None) -> None:
        """
        Constructor
        
        Args:
            configs: 各后端的配置字典
        """
        self._configs = configs or {}
        self._backends: Dict[BackendType, MessageQueue] = {}
        self._primary_backend: Optional[BackendType] = None
        self._fallback_enabled = True
        
        # 订阅管理
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        # 统计信息
        self._stats = {
            "messages_published": 0,
            "messages_consumed": 0,
            "failover_count": 0,
            "errors": 0
        }
    
    def connect(self, preferred_backend: Optional[BackendType] = None) -> bool:
        """
        连接消息总线
        
        Args:
            preferred_backend: 首选后端类型
            
        Returns:
            是否连接成功
        """
        # 如果指定了首选后端，优先尝试
        if preferred_backend:
            priority_list = [preferred_backend] + [
                b for b in self.BACKEND_PRIORITY if b != preferred_backend
            ]
        else:
            priority_list = self.BACKEND_PRIORITY
        
        # 按优先级尝试连接
        for backend_type in priority_list:
            try:
                config = self._configs.get(backend_type, QueueConfig())
                backend_class = self.BACKEND_CLASSES[backend_type]
                backend = backend_class(config)
                
                if backend.connect():
                    self._backends[backend_type] = backend
                    
                    # 设置主后端
                    if self._primary_backend is None:
                        self._primary_backend = backend_type
                        print(f"消息总线主后端: {backend_type.value}")
                    else:
                        print(f"消息总线备用后端: {backend_type.value}")
                        
            except Exception as e:
                print(f"连接{backend_type.value}失败: {e}")
                continue
        
        return self._primary_backend is not None
    
    def disconnect(self) -> None:
        """断开所有连接"""
        for backend in self._backends.values():
            try:
                backend.disconnect()
            except Exception as e:
                print(f"断开连接失败: {e}")
        
        self._backends.clear()
        self._primary_backend = None
    
    def publish(
        self,
        message: Message,
        routing_key: str = "",
        exchange: str = "alphax"
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
        # 尝试主后端
        if self._primary_backend and self._primary_backend in self._backends:
            backend = self._backends[self._primary_backend]
            if backend.is_connected():
                if backend.publish(message, routing_key, exchange):
                    self._stats["messages_published"] += 1
                    return True
        
        # 主后端失败，尝试备用后端
        if self._fallback_enabled:
            for backend_type, backend in self._backends.items():
                if backend_type != self._primary_backend and backend.is_connected():
                    try:
                        if backend.publish(message, routing_key, exchange):
                            self._stats["messages_published"] += 1
                            self._stats["failover_count"] += 1
                            print(f"故障转移: 使用{backend_type.value}发布消息")
                            return True
                    except Exception as e:
                        continue
        
        self._stats["errors"] += 1
        return False
    
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
        with self._lock:
            # 记录订阅信息（用于故障转移后恢复）
            self._subscriptions[queue_name] = {
                "msg_type": msg_type,
                "callback": callback,
                "auto_ack": auto_ack
            }
        
        # 在主后端上订阅
        if self._primary_backend and self._primary_backend in self._backends:
            backend = self._backends[self._primary_backend]
            if backend.is_connected():
                return backend.subscribe(queue_name, msg_type, callback, auto_ack)
        
        # 尝试备用后端
        for backend_type, backend in self._backends.items():
            if backend.is_connected():
                return backend.subscribe(queue_name, msg_type, callback, auto_ack)
        
        return False
    
    def unsubscribe(self, queue_name: str) -> bool:
        """
        取消订阅
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否取消成功
        """
        with self._lock:
            if queue_name in self._subscriptions:
                del self._subscriptions[queue_name]
        
        # 在所有后端上取消订阅
        success = True
        for backend in self._backends.values():
            try:
                if not backend.unsubscribe(queue_name):
                    success = False
            except Exception:
                success = False
        
        return success
    
    def broadcast(
        self,
        message: Message,
        exchange: str = "alphax.fanout"
    ) -> bool:
        """
        广播消息
        
        Args:
            message: 消息对象
            exchange: 广播交换机名称
            
        Returns:
            是否广播成功
        """
        return self.publish(message, routing_key="", exchange=exchange)
    
    def create_trade_signal(
        self,
        strategy_name: str,
        symbol: str,
        action: str,
        volume: float,
        price: float,
        **kwargs
    ) -> bool:
        """
        创建交易信号
        
        Args:
            strategy_name: 策略名称
            symbol: 合约代码
            action: 动作（buy/sell）
            volume: 数量
            price: 价格
            **kwargs: 其他参数
            
        Returns:
            是否发送成功
        """
        if self._primary_backend and self._primary_backend in self._backends:
            backend = self._backends[self._primary_backend]
            message = backend.create_trade_message(
                symbol, action, volume, price,
                strategy_name=strategy_name,
                **kwargs
            )
            return self.publish(message, routing_key="trade")
        return False
    
    def create_strategy_signal(
        self,
        strategy_name: str,
        symbol: str,
        signal: str,
        strength: float,
        **kwargs
    ) -> bool:
        """
        创建策略信号
        
        Args:
            strategy_name: 策略名称
            symbol: 合约代码
            signal: 信号类型
            strength: 信号强度
            **kwargs: 其他参数
            
        Returns:
            是否发送成功
        """
        if self._primary_backend and self._primary_backend in self._backends:
            backend = self._backends[self._primary_backend]
            message = backend.create_signal_message(
                strategy_name, symbol, signal, strength,
                **kwargs
            )
            return self.publish(message, routing_key="signal")
        return False
    
    def create_risk_alert(
        self,
        alert_type: str,
        level: str,
        description: str,
        **kwargs
    ) -> bool:
        """
        创建风险告警
        
        Args:
            alert_type: 告警类型
            level: 告警级别
            description: 描述
            **kwargs: 其他参数
            
        Returns:
            是否发送成功
        """
        if self._primary_backend and self._primary_backend in self._backends:
            backend = self._backends[self._primary_backend]
            message = backend.create_risk_alert_message(
                alert_type, level, description,
                **kwargs
            )
            return self.publish(message, routing_key="risk_alert")
        return False
    
    def get_backend_status(self) -> Dict[str, Any]:
        """
        获取后端状态
        
        Returns:
            后端状态字典
        """
        status = {}
        for backend_type, backend in self._backends.items():
            status[backend_type.value] = {
                "connected": backend.is_connected(),
                "is_primary": backend_type == self._primary_backend,
                "stats": backend.get_stats()
            }
        return status
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            **self._stats,
            "backends": self.get_backend_status(),
            "subscriptions": len(self._subscriptions)
        }
    
    def switch_primary_backend(self, backend_type: BackendType) -> bool:
        """
        切换主后端
        
        Args:
            backend_type: 新的主后端类型
            
        Returns:
            是否切换成功
        """
        if backend_type not in self._backends:
            print(f"后端{backend_type.value}未连接")
            return False
        
        if not self._backends[backend_type].is_connected():
            print(f"后端{backend_type.value}未连接")
            return False
        
        old_backend = self._primary_backend
        self._primary_backend = backend_type
        
        print(f"主后端切换: {old_backend.value if old_backend else 'None'} -> {backend_type.value}")
        
        # 重新订阅
        with self._lock:
            for queue_name, sub_info in self._subscriptions.items():
                try:
                    self.subscribe(
                        queue_name,
                        sub_info["msg_type"],
                        sub_info["callback"],
                        sub_info["auto_ack"]
                    )
                except Exception as e:
                    print(f"重新订阅{queue_name}失败: {e}")
        
        return True
    
    def enable_fallback(self, enabled: bool = True) -> None:
        """
        启用/禁用故障转移
        
        Args:
            enabled: 是否启用
        """
        self._fallback_enabled = enabled
        print(f"故障转移{'启用' if enabled else '禁用'}")
    
    def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            是否健康
        """
        # 检查主后端
        if self._primary_backend and self._primary_backend in self._backends:
            backend = self._backends[self._primary_backend]
            if backend.is_connected():
                return True
        
        # 主后端不健康，尝试切换
        if self._fallback_enabled:
            for backend_type in self.BACKEND_PRIORITY:
                if (backend_type in self._backends and 
                    self._backends[backend_type].is_connected()):
                    if backend_type != self._primary_backend:
                        self.switch_primary_backend(backend_type)
                    return True
        
        return False


# 全局消息总线实例
_message_bus: Optional[MessageBus] = None


def get_message_bus(
    configs: Optional[Dict[BackendType, QueueConfig]] = None,
    force_new: bool = False
) -> MessageBus:
    """
    获取消息总线实例（单例模式）
    
    Args:
        configs: 配置字典
        force_new: 强制创建新实例
        
    Returns:
        消息总线实例
    """
    global _message_bus
    
    if _message_bus is None or force_new:
        _message_bus = MessageBus(configs)
    
    return _message_bus
