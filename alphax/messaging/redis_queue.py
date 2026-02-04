"""
Redis消息队列实现

基于Redis Pub/Sub的简单消息队列实现
作为RabbitMQ/Kafka的降级方案
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .base import MessageQueue, QueueConfig, MessageType, Message


class RedisQueue(MessageQueue):
    """
    Redis消息队列实现
    
    使用Redis的Pub/Sub功能实现消息队列
    适合作为降级方案或简单场景使用
    """
    
    def __init__(self, config: Optional[QueueConfig] = None) -> None:
        """Constructor"""
        if config is None:
            config = QueueConfig(port=6379)  # Redis默认端口
        super().__init__(config)
        
        self._redis = None
        self._pubsub = None
        self._subscriber_threads: Dict[str, threading.Thread] = {}
        self._running = False
        
    def connect(self) -> bool:
        """
        连接Redis
        
        Returns:
            是否连接成功
        """
        try:
            import redis
            
            self._redis = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password if self.config.password else None,
                decode_responses=True,
                socket_connect_timeout=self.config.connection_timeout
            )
            
            # 测试连接
            self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._connected = True
            self._running = True
            
            return True
            
        except ImportError:
            print("Redis库未安装，请运行: pip install redis")
            return False
        except Exception as e:
            print(f"Redis连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        
        # 停止所有订阅线程
        for thread in self._subscriber_threads.values():
            if thread.is_alive():
                thread.join(timeout=2)
        
        if self._pubsub:
            self._pubsub.close()
            
        if self._redis:
            self._redis.close()
            
        self._connected = False
    
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
            routing_key: 路由键（作为channel）
            exchange: 交换机名称（作为前缀）
            
        Returns:
            是否发布成功
        """
        if not self._connected or not self._redis:
            return False
        
        try:
            # 构建channel名称
            channel = f"{exchange}:{routing_key}" if routing_key else f"{exchange}:{message.msg_type.value}"
            
            # 发布消息
            message_json = message.to_json()
            self._redis.publish(channel, message_json)
            
            # 同时存储到历史列表（保留最近100条）
            history_key = f"history:{channel}"
            self._redis.lpush(history_key, message_json)
            self._redis.ltrim(history_key, 0, 99)
            
            self._published_count += 1
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Redis发布消息失败: {e}")
            return False
    
    def subscribe(
        self,
        queue_name: str,
        msg_type: MessageType,
        callback: Callable[[Message], None],
        auto_ack: bool = True
    ) -> bool:
        """
        订阅消息
        
        Args:
            queue_name: 队列名称（作为channel）
            msg_type: 消息类型
            callback: 回调函数
            auto_ack: 是否自动确认（Redis中忽略）
            
        Returns:
            是否订阅成功
        """
        if not self._connected or not self._pubsub:
            return False
        
        try:
            # 注册回调
            self.register_callback(msg_type, callback)
            
            # 订阅channel
            self._pubsub.subscribe(queue_name)
            
            # 启动订阅线程
            thread = threading.Thread(
                target=self._message_handler,
                args=(queue_name, msg_type),
                daemon=True
            )
            thread.start()
            
            self._subscriber_threads[queue_name] = thread
            
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Redis订阅失败: {e}")
            return False
    
    def _message_handler(self, channel: str, msg_type: MessageType) -> None:
        """
        消息处理线程
        
        Args:
            channel: 频道名称
            msg_type: 消息类型
        """
        while self._running:
            try:
                message = self._pubsub.get_message(timeout=1)
                
                if message and message["type"] == "message":
                    try:
                        # 解析消息
                        msg_data = json.loads(message["data"])
                        msg = Message.from_json(json.dumps(msg_data))
                        
                        # 触发回调
                        self._trigger_callbacks(msg)
                        self._consumed_count += 1
                        
                    except Exception as e:
                        self._error_count += 1
                        print(f"Redis消息解析失败: {e}")
                        
            except Exception as e:
                if self._running:
                    self._error_count += 1
                    print(f"Redis消息处理失败: {e}")
                    time.sleep(1)
    
    def unsubscribe(self, queue_name: str) -> bool:
        """
        取消订阅
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否取消成功
        """
        if not self._connected or not self._pubsub:
            return False
        
        try:
            self._pubsub.unsubscribe(queue_name)
            
            # 停止对应线程
            if queue_name in self._subscriber_threads:
                del self._subscriber_threads[queue_name]
            
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Redis取消订阅失败: {e}")
            return False
    
    def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        auto_delete: bool = False
    ) -> bool:
        """
        声明队列（Redis中不需要显式声明）
        
        Args:
            queue_name: 队列名称
            durable: 是否持久化
            auto_delete: 是否自动删除
            
        Returns:
            是否声明成功
        """
        # Redis不需要显式声明队列，直接返回True
        return True
    
    def delete_queue(self, queue_name: str) -> bool:
        """
        删除队列
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否删除成功
        """
        if not self._connected or not self._redis:
            return False
        
        try:
            # 删除历史记录
            history_key = f"history:{queue_name}"
            self._redis.delete(history_key)
            
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Redis删除队列失败: {e}")
            return False
    
    def get_queue_info(self, queue_name: str) -> Dict[str, Any]:
        """
        获取队列信息
        
        Args:
            queue_name: 队列名称
            
        Returns:
            队列信息字典
        """
        if not self._connected or not self._redis:
            return {}
        
        try:
            history_key = f"history:{queue_name}"
            message_count = self._redis.llen(history_key)
            
            return {
                "queue_name": queue_name,
                "message_count": message_count,
                "type": "redis_pubsub",
                "connected": self._connected
            }
            
        except Exception as e:
            self._error_count += 1
            print(f"Redis获取队列信息失败: {e}")
            return {}
    
    def get_message_history(
        self,
        channel: str,
        count: int = 100
    ) -> List[Message]:
        """
        获取消息历史
        
        Args:
            channel: 频道名称
            count: 获取数量
            
        Returns:
            消息列表
        """
        if not self._connected or not self._redis:
            return []
        
        try:
            history_key = f"history:{channel}"
            messages_json = self._redis.lrange(history_key, 0, count - 1)
            
            messages = []
            for msg_json in messages_json:
                try:
                    msg = Message.from_json(msg_json)
                    messages.append(msg)
                except Exception:
                    continue
            
            return messages
            
        except Exception as e:
            self._error_count += 1
            print(f"Redis获取消息历史失败: {e}")
            return []
