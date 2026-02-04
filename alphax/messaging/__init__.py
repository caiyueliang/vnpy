"""
消息队列系统模块

提供统一的消息队列接口，支持：
- RabbitMQ
- Kafka
- Redis Pub/Sub（降级方案）

用于系统间异步通信、事件驱动架构
"""

from .base import MessageQueue, QueueConfig, MessageType, Message
from .rabbitmq_queue import RabbitMQQueue
from .kafka_queue import KafkaQueue
from .redis_queue import RedisQueue
from .message_bus import MessageBus

__all__ = [
    "MessageQueue",
    "QueueConfig",
    "MessageType",
    "Message",
    "RabbitMQQueue",
    "KafkaQueue",
    "RedisQueue",
    "MessageBus",
]
