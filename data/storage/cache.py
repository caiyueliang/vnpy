"""
缓存数据库模块

封装Redis用于高速缓存
"""

import json
import pickle
from typing import Any


class CacheDB:
    """
    缓存数据库

    用于高速缓存实时数据、计算结果等
    支持Redis和内存字典（作为fallback）
    """

    def __init__(self, config: Any) -> None:
        """Constructor"""
        self.config = config
        self._client: Any = None
        self._memory_cache: dict = {}
        self._connected: bool = False
        self._use_redis: bool = False

        # 统计信息
        self._hits: int = 0
        self._misses: int = 0
        self._sets: int = 0
        self._deletes: int = 0

    def connect(self) -> bool:
        """
        连接缓存数据库

        优先使用Redis，如不可用则使用内存缓存
        """
        try:
            # 尝试连接Redis
            import redis

            self._client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                password=self.config.redis_password or None,
                decode_responses=False
            )

            # 测试连接
            self._client.ping()

            self._connected = True
            self._use_redis = True
            return True

        except ImportError:
            print("Redis客户端未安装，使用内存缓存作为fallback")
            self._use_memory_cache()
            return True

        except Exception as e:
            print(f"Redis连接失败: {e}，使用内存缓存作为fallback")
            self._use_memory_cache()
            return True

    def _use_memory_cache(self) -> None:
        """使用内存缓存"""
        self._client = None
        self._memory_cache = {}
        self._connected = True
        self._use_redis = False

    def disconnect(self) -> None:
        """断开连接"""
        if self._client and self._use_redis:
            self._client.close()
        self._connected = False

    def set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒）

        Returns:
            是否设置成功
        """
        try:
            if self._use_redis:
                # 使用pickle序列化
                serialized = pickle.dumps(value)
                self._client.setex(key, expire, serialized)
            else:
                # 内存缓存
                self._memory_cache[key] = {
                    "value": value,
                    "expire": expire
                }

            self._sets += 1
            return True

        except Exception as e:
            print(f"设置缓存失败: {e}")
            return False

    def get(self, key: str) -> Any:
        """
        获取缓存

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回None
        """
        try:
            if self._use_redis:
                data = self._client.get(key)
                if data:
                    self._hits += 1
                    return pickle.loads(data)
                else:
                    self._misses += 1
                    return None
            else:
                if key in self._memory_cache:
                    self._hits += 1
                    return self._memory_cache[key]["value"]
                else:
                    self._misses += 1
                    return None

        except Exception as e:
            print(f"获取缓存失败: {e}")
            return None

    def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        try:
            if self._use_redis:
                self._client.delete(key)
            else:
                if key in self._memory_cache:
                    del self._memory_cache[key]

            self._deletes += 1
            return True

        except Exception as e:
            print(f"删除缓存失败: {e}")
            return False

    def exists(self, key: str) -> bool:
        """
        检查键是否存在

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        try:
            if self._use_redis:
                return bool(self._client.exists(key))
            else:
                return key in self._memory_cache

        except Exception as e:
            print(f"检查缓存失败: {e}")
            return False

    def expire(self, key: str, seconds: int) -> bool:
        """
        设置过期时间

        Args:
            key: 缓存键
            seconds: 过期秒数

        Returns:
            是否设置成功
        """
        try:
            if self._use_redis:
                return bool(self._client.expire(key, seconds))
            else:
                if key in self._memory_cache:
                    self._memory_cache[key]["expire"] = seconds
                    return True
                return False

        except Exception as e:
            print(f"设置过期时间失败: {e}")
            return False

    def ttl(self, key: str) -> int:
        """
        获取剩余过期时间

        Args:
            key: 缓存键

        Returns:
            剩余秒数，-1表示永不过期，-2表示不存在
        """
        try:
            if self._use_redis:
                return self._client.ttl(key)
            else:
                if key in self._memory_cache:
                    return self._memory_cache[key].get("expire", -1)
                return -2

        except Exception as e:
            print(f"获取TTL失败: {e}")
            return -2

    def keys(self, pattern: str = "*") -> list[str]:
        """
        获取匹配的键列表

        Args:
            pattern: 匹配模式

        Returns:
            键列表
        """
        try:
            if self._use_redis:
                return [k.decode() if isinstance(k, bytes) else k for k in self._client.keys(pattern)]
            else:
                import fnmatch
                return [k for k in self._memory_cache.keys() if fnmatch.fnmatch(k, pattern)]

        except Exception as e:
            print(f"获取键列表失败: {e}")
            return []

    def clear(self) -> bool:
        """
        清空缓存

        Returns:
            是否清空成功
        """
        try:
            if self._use_redis:
                self._client.flushdb()
            else:
                self._memory_cache.clear()

            return True

        except Exception as e:
            print(f"清空缓存失败: {e}")
            return False

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = {
            "connected": self._connected,
            "use_redis": self._use_redis,
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "deletes": self._deletes,
        }

        if self._hits + self._misses > 0:
            stats["hit_rate"] = self._hits / (self._hits + self._misses)
        else:
            stats["hit_rate"] = 0

        if not self._use_redis:
            stats["memory_keys"] = len(self._memory_cache)

        return stats
