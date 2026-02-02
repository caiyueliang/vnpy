"""
数据库管理器

统一管理时序数据库、关系数据库和缓存
"""

from dataclasses import dataclass
from typing import Any

from vnpy.trader.object import BarData, TickData


@dataclass
class DBConfig:
    """数据库配置"""
    # InfluxDB配置
    influxdb_host: str = "localhost"
    influxdb_port: int = 8086
    influxdb_database: str = "vnpy_market_data"
    influxdb_username: str = ""
    influxdb_password: str = ""

    # PostgreSQL配置
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_database: str = "vnpy_trading"
    postgres_username: str = "vnpy"
    postgres_password: str = "vnpy"

    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""


class DatabaseManager:
    """
    数据库管理器

    统一管理多种数据库连接，提供统一的数据访问接口
    """

    def __init__(self, config: DBConfig | None = None) -> None:
        """Constructor"""
        self.config: DBConfig = config or DBConfig()

        # 数据库连接实例
        self._timeseries_db: Any = None
        self._relational_db: Any = None
        self._cache_db: Any = None

        # 连接状态
        self._connected: bool = False

    def connect(self) -> bool:
        """
        连接所有数据库

        Returns:
            是否全部连接成功
        """
        try:
            # 初始化时序数据库
            from .timeseries import TimeSeriesDB
            self._timeseries_db = TimeSeriesDB(self.config)
            ts_connected = self._timeseries_db.connect()

            # 初始化关系数据库
            from .relational import RelationalDB
            self._relational_db = RelationalDB(self.config)
            rel_connected = self._relational_db.connect()

            # 初始化缓存数据库
            from .cache import CacheDB
            self._cache_db = CacheDB(self.config)
            cache_connected = self._cache_db.connect()

            self._connected = ts_connected and rel_connected and cache_connected

            return self._connected

        except Exception as e:
            print(f"数据库连接失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开所有数据库连接"""
        if self._timeseries_db:
            self._timeseries_db.disconnect()
        if self._relational_db:
            self._relational_db.disconnect()
        if self._cache_db:
            self._cache_db.disconnect()
        self._connected = False

    def save_bar_data(self, bars: list[BarData]) -> bool:
        """
        保存K线数据

        Args:
            bars: K线数据列表

        Returns:
            是否保存成功
        """
        if not self._connected or not self._timeseries_db:
            return False
        return self._timeseries_db.save_bar_data(bars)

    def load_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: Any,
        end: Any
    ) -> list[BarData]:
        """
        加载K线数据

        Args:
            vt_symbol: 合约代码
            interval: 时间周期
            start: 开始时间
            end: 结束时间

        Returns:
            K线数据列表
        """
        if not self._connected or not self._timeseries_db:
            return []
        return self._timeseries_db.load_bar_data(vt_symbol, interval, start, end)

    def save_tick_data(self, ticks: list[TickData]) -> bool:
        """
        保存Tick数据

        Args:
            ticks: Tick数据列表

        Returns:
            是否保存成功
        """
        if not self._connected or not self._timeseries_db:
            return False
        return self._timeseries_db.save_tick_data(ticks)

    def load_tick_data(
        self,
        vt_symbol: str,
        start: Any,
        end: Any
    ) -> list[TickData]:
        """
        加载Tick数据

        Args:
            vt_symbol: 合约代码
            start: 开始时间
            end: 结束时间

        Returns:
            Tick数据列表
        """
        if not self._connected or not self._timeseries_db:
            return []
        return self._timeseries_db.load_tick_data(vt_symbol, start, end)

    def cache_set(self, key: str, value: Any, expire: int = 3600) -> bool:
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒）

        Returns:
            是否设置成功
        """
        if not self._connected or not self._cache_db:
            return False
        return self._cache_db.set(key, value, expire)

    def cache_get(self, key: str) -> Any:
        """
        获取缓存

        Args:
            key: 缓存键

        Returns:
            缓存值
        """
        if not self._connected or not self._cache_db:
            return None
        return self._cache_db.get(key)

    def cache_delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        if not self._connected or not self._cache_db:
            return False
        return self._cache_db.delete(key)

    def execute_sql(self, sql: str, params: tuple = ()) -> list:
        """
        执行SQL语句

        Args:
            sql: SQL语句
            params: 参数

        Returns:
            查询结果
        """
        if not self._connected or not self._relational_db:
            return []
        return self._relational_db.execute(sql, params)

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected

    def get_stats(self) -> dict:
        """获取数据库统计信息"""
        stats = {
            "connected": self._connected,
            "timeseries": {},
            "relational": {},
            "cache": {},
        }

        if self._timeseries_db:
            stats["timeseries"] = self._timeseries_db.get_stats()
        if self._relational_db:
            stats["relational"] = self._relational_db.get_stats()
        if self._cache_db:
            stats["cache"] = self._cache_db.get_stats()

        return stats
