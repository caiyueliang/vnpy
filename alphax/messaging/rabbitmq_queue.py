"""
RabbitMQ消息队列实现

完整的消息队列功能实现，支持：
- 交换机、队列、绑定管理
- 消息持久化
- 消息确认机制
- 死信队列
- 延迟队列
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .base import MessageQueue, QueueConfig, MessageType, Message


class RabbitMQQueue(MessageQueue):
    """
    RabbitMQ消息队列实现
    
    提供完整的消息队列功能
    """
    
    def __init__(self, config: Optional[QueueConfig] = None) -> None:
        """Constructor"""
        if config is None:
            config = QueueConfig(port=5672)
        super().__init__(config)
        
        self._connection = None
        self._channel = None
        self._consumer_tags: Dict[str, str] = {}
        
    def connect(self) -> bool:
        """
        连接RabbitMQ
        
        Returns:
            是否连接成功
        """
        try:
            import pika
            
            credentials = pika.PlainCredentials(
                self.config.username,
                self.config.password
            )
            
            parameters = pika.ConnectionParameters(
                host=self.config.host,
                port=self.config.port,
                virtual_host=self.config.virtual_host,
                credentials=credentials,
                connection_attempts=self.config.retry_times,
                retry_delay=self.config.retry_delay,
                heartbeat=self.config.heartbeat
            )
            
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            
            # 设置QoS
            self._channel.basic_qos(prefetch_count=self.config.prefetch_count)
            
            self._connected = True
            
            # 声明默认交换机
            self._declare_default_exchanges()
            
            return True
            
        except ImportError:
            print("pika库未安装，请运行: pip install pika")
            return False
        except Exception as e:
            print(f"RabbitMQ连接失败: {e}")
            return False
    
    def _declare_default_exchanges(self) -> None:
        """声明默认交换机"""
        if not self._channel:
            return
        
        try:
            # 声明topic交换机
            self._channel.exchange_declare(
                exchange="alphax.topic",
                exchange_type="topic",
                durable=True
            )
            
            # 声明direct交换机
            self._channel.exchange_declare(
                exchange="alphax.direct",
                exchange_type="direct",
                durable=True
            )
            
            # 声明fanout交换机（广播）
            self._channel.exchange_declare(
                exchange="alphax.fanout",
                exchange_type="fanout",
                durable=True
            )
            
        except Exception as e:
            print(f"声明默认交换机失败: {e}")
    
    def disconnect(self) -> None:
        """断开连接"""
        try:
            # 取消所有消费者
            for consumer_tag in self._consumer_tags.values():
                try:
                    self._channel.basic_cancel(consumer_tag)
                except:
                    pass
            
            if self._channel and self._channel.is_open:
                self._channel.close()
                
            if self._connection and self._connection.is_open:
                self._connection.close()
                
        except Exception as e:
            print(f"RabbitMQ断开连接失败: {e}")
        finally:
            self._connected = False
            self._channel = None
            self._connection = None
    
    def publish(
        self,
        message: Message,
        routing_key: str = "",
        exchange: str = "alphax.topic"
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
        if not self._connected or not self._channel:
            return False
        
        try:
            import pika
            
            # 如果没有指定routing_key，使用消息类型
            if not routing_key:
                routing_key = message.msg_type.value
            
            # 构建消息属性
            properties = pika.BasicProperties(
                message_id=message.msg_id,
                timestamp=int(message.timestamp.timestamp()),
                delivery_mode=2 if self.config.durable else 1,  # 持久化
                priority=message.priority,
                content_type="application/json"
            )
            
            # 发布消息
            self._channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=message.to_json(),
                properties=properties
            )
            
            self._published_count += 1
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"RabbitMQ发布消息失败: {e}")
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
        if not self._connected or not self._channel:
            return False
        
        try:
            # 声明队列
            self.declare_queue(queue_name, self.config.durable, self.config.auto_delete)
            
            # 绑定队列到交换机
            routing_key = msg_type.value
            self._channel.queue_bind(
                queue=queue_name,
                exchange="alphax.topic",
                routing_key=routing_key
            )
            
            # 注册回调
            self.register_callback(msg_type, callback)
            
            # 定义消息处理函数
            def message_handler(
                ch,
                method,
                properties,
                body
            ):
                try:
                    # 解析消息
                    msg = Message.from_json(body.decode('utf-8'))
                    
                    # 触发回调
                    self._trigger_callbacks(msg)
                    self._consumed_count += 1
                    
                    # 手动确认
                    if not auto_ack:
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        
                except Exception as e:
                    self._error_count += 1
                    print(f"RabbitMQ消息处理失败: {e}")
                    # 拒绝消息，重新入队
                    if not auto_ack:
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            
            # 开始消费
            consumer_tag = self._channel.basic_consume(
                queue=queue_name,
                on_message_callback=message_handler,
                auto_ack=auto_ack
            )
            
            self._consumer_tags[queue_name] = consumer_tag
            
            # 在单独线程中启动消费
            def consume():
                try:
                    self._channel.start_consuming()
                except Exception as e:
                    if self._connected:
                        print(f"RabbitMQ消费异常: {e}")
            
            thread = threading.Thread(target=consume, daemon=True)
            thread.start()
            
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"RabbitMQ订阅失败: {e}")
            return False
    
    def unsubscribe(self, queue_name: str) -> bool:
        """
        取消订阅
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否取消成功
        """
        if queue_name in self._consumer_tags:
            try:
                consumer_tag = self._consumer_tags[queue_name]
                self._channel.basic_cancel(consumer_tag)
                del self._consumer_tags[queue_name]
                return True
            except Exception as e:
                print(f"RabbitMQ取消订阅失败: {e}")
                return False
        return True
    
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
        if not self._connected or not self._channel:
            return False
        
        try:
            self._channel.queue_declare(
                queue=queue_name,
                durable=durable,
                auto_delete=auto_delete
            )
            return True
        except Exception as e:
            self._error_count += 1
            print(f"RabbitMQ声明队列失败: {e}")
            return False
    
    def delete_queue(self, queue_name: str) -> bool:
        """
        删除队列
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否删除成功
        """
        if not self._connected or not self._channel:
            return False
        
        try:
            self._channel.queue_delete(queue=queue_name)
            return True
        except Exception as e:
            self._error_count += 1
            print(f"RabbitMQ删除队列失败: {e}")
            return False
    
    def get_queue_info(self, queue_name: str) -> Dict[str, Any]:
        """
        获取队列信息
        
        Args:
            queue_name: 队列名称
            
        Returns:
            队列信息字典
        """
        if not self._connected or not self._channel:
            return {}
        
        try:
            result = self._channel.queue_declare(
                queue=queue_name,
                passive=True  # 只查询，不创建
            )
            
            return {
                "queue_name": queue_name,
                "message_count": result.method.message_count,
                "consumer_count": result.method.consumer_count,
                "type": "rabbitmq",
                "connected": self._connected
            }
        except Exception as e:
            # 队列不存在
            return {
                "queue_name": queue_name,
                "message_count": 0,
                "consumer_count": 0,
                "type": "rabbitmq",
                "connected": self._connected,
                "error": str(e)
            }
    
    def declare_delayed_queue(
        self,
        queue_name: str,
        delay_ms: int = 0
    ) -> bool:
        """
        声明延迟队列
        
        Args:
            queue_name: 队列名称
            delay_ms: 延迟时间（毫秒）
            
        Returns:
            是否声明成功
        """
        if not self._connected or not self._channel:
            return False
        
        try:
            # 声明延迟交换机
            args = {
                "x-delayed-type": "direct"
            }
            
            self._channel.exchange_declare(
                exchange="alphax.delayed",
                exchange_type="x-delayed-message",
                durable=True,
                arguments=args
            )
            
            # 声明队列
            self._channel.queue_declare(
                queue=queue_name,
                durable=True
            )
            
            # 绑定
            self._channel.queue_bind(
                queue=queue_name,
                exchange="alphax.delayed",
                routing_key=queue_name
            )
            
            return True
        except Exception as e:
            self._error_count += 1
            print(f"RabbitMQ声明延迟队列失败: {e}")
            return False
    
    def publish_delayed(
        self,
        message: Message,
        delay_ms: int,
        routing_key: str = ""
    ) -> bool:
        """
        发布延迟消息
        
        Args:
            message: 消息对象
            delay_ms: 延迟时间（毫秒）
            routing_key: 路由键
            
        Returns:
            是否发布成功
        """
        if not self._connected or not self._channel:
            return False
        
        try:
            import pika
            
            properties = pika.BasicProperties(
                message_id=message.msg_id,
                timestamp=int(message.timestamp.timestamp()),
                delivery_mode=2,
                headers={"x-delay": delay_ms}
            )
            
            self._channel.basic_publish(
                exchange="alphax.delayed",
                routing_key=routing_key or message.msg_type.value,
                body=message.to_json(),
                properties=properties
            )
            
            self._published_count += 1
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"RabbitMQ发布延迟消息失败: {e}")
            return False
