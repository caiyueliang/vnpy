"""
Kafka消息队列实现

高吞吐量的消息队列实现，适合大数据量场景
"""

import json
import threading
from typing import Any, Callable, Dict, List, Optional

from .base import MessageQueue, QueueConfig, MessageType, Message


class KafkaQueue(MessageQueue):
    """
    Kafka消息队列实现
    
    提供高吞吐量的消息队列功能
    """
    
    def __init__(self, config: Optional[QueueConfig] = None) -> None:
        """Constructor"""
        if config is None:
            config = QueueConfig(port=9092)  # Kafka默认端口
        super().__init__(config)
        
        self._producer = None
        self._consumer = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._running = False
        
    def connect(self) -> bool:
        """
        连接Kafka
        
        Returns:
            是否连接成功
        """
        try:
            from kafka import KafkaProducer, KafkaConsumer
            
            # 创建生产者
            self._producer = KafkaProducer(
                bootstrap_servers=f"{self.config.host}:{self.config.port}",
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda v: v.encode('utf-8') if v else None,
                retries=self.config.retry_times,
                acks='all'
            )
            
            self._connected = True
            self._running = True
            
            return True
            
        except ImportError:
            print("kafka-python库未安装，请运行: pip install kafka-python")
            return False
        except Exception as e:
            print(f"Kafka连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        
        if self._consumer:
            self._consumer.close()
            
        if self._producer:
            self._producer.close()
            
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
            routing_key: 路由键（作为topic）
            exchange: 交换机名称（作为topic前缀）
            
        Returns:
            是否发布成功
        """
        if not self._connected or not self._producer:
            return False
        
        try:
            # 构建topic名称
            topic = f"{exchange}.{routing_key}" if routing_key else f"{exchange}.{message.msg_type.value}"
            
            # 发送消息
            future = self._producer.send(
                topic,
                key=message.msg_id,
                value=message.to_dict()
            )
            
            # 等待确认
            future.get(timeout=10)
            
            self._published_count += 1
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Kafka发布消息失败: {e}")
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
            queue_name: 队列名称（作为topic）
            msg_type: 消息类型
            callback: 回调函数
            auto_ack: 是否自动确认（Kafka中总是自动）
            
        Returns:
            是否订阅成功
        """
        if not self._connected:
            return False
        
        try:
            from kafka import KafkaConsumer
            
            # 注册回调
            self.register_callback(msg_type, callback)
            
            # 创建消费者
            self._consumer = KafkaConsumer(
                queue_name,
                bootstrap_servers=f"{self.config.host}:{self.config.port}",
                group_id=f"alphax-{queue_name}",
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                auto_offset_reset='latest'
            )
            
            # 启动消费线程
            def consume():
                while self._running:
                    try:
                        for msg in self._consumer:
                            if not self._running:
                                break
                            
                            try:
                                # 解析消息
                                message = Message.from_json(json.dumps(msg.value))
                                
                                # 触发回调
                                self._trigger_callbacks(message)
                                self._consumed_count += 1
                                
                            except Exception as e:
                                self._error_count += 1
                                print(f"Kafka消息处理失败: {e}")
                                
                    except Exception as e:
                        if self._running:
                            print(f"Kafka消费异常: {e}")
            
            self._consumer_thread = threading.Thread(target=consume, daemon=True)
            self._consumer_thread.start()
            
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Kafka订阅失败: {e}")
            return False
    
    def unsubscribe(self, queue_name: str) -> bool:
        """
        取消订阅
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否取消成功
        """
        if self._consumer:
            try:
                self._consumer.close()
                self._consumer = None
                return True
            except Exception as e:
                print(f"Kafka取消订阅失败: {e}")
                return False
        return True
    
    def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        auto_delete: bool = False
    ) -> bool:
        """
        声明队列（Kafka自动创建topic）
        
        Args:
            queue_name: 队列名称
            durable: 是否持久化
            auto_delete: 是否自动删除
            
        Returns:
            是否声明成功
        """
        # Kafka自动创建topic，无需显式声明
        return True
    
    def delete_queue(self, queue_name: str) -> bool:
        """
        删除队列（Kafka中删除topic）
        
        Args:
            queue_name: 队列名称
            
        Returns:
            是否删除成功
        """
        try:
            from kafka.admin import KafkaAdminClient, NewTopic
            
            admin_client = KafkaAdminClient(
                bootstrap_servers=f"{self.config.host}:{self.config.port}"
            )
            
            admin_client.delete_topics([queue_name])
            admin_client.close()
            
            return True
            
        except Exception as e:
            self._error_count += 1
            print(f"Kafka删除topic失败: {e}")
            return False
    
    def get_queue_info(self, queue_name: str) -> Dict[str, Any]:
        """
        获取队列信息
        
        Args:
            queue_name: 队列名称
            
        Returns:
            队列信息字典
        """
        try:
            from kafka.admin import KafkaAdminClient
            
            admin_client = KafkaAdminClient(
                bootstrap_servers=f"{self.config.host}:{self.config.port}"
            )
            
            # 获取topic信息
            topics = admin_client.describe_topics([queue_name])
            admin_client.close()
            
            if topics:
                topic_info = topics[0]
                return {
                    "queue_name": queue_name,
                    "partitions": len(topic_info["partitions"]),
                    "type": "kafka",
                    "connected": self._connected
                }
            
            return {
                "queue_name": queue_name,
                "error": "Topic not found",
                "type": "kafka",
                "connected": self._connected
            }
            
        except Exception as e:
            return {
                "queue_name": queue_name,
                "error": str(e),
                "type": "kafka",
                "connected": self._connected
            }
