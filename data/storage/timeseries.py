"""
时序数据库模块

封装InfluxDB用于存储行情数据
"""

from datetime import datetime
from typing import Any

from vnpy.trader.object import BarData, TickData
from vnpy.trader.constant import Exchange, Interval


class TimeSeriesDB:
    """
    时序数据库

    用于存储Tick和K线行情数据
    支持InfluxDB和SQLite（作为fallback）
    """

    def __init__(self, config: Any) -> None:
        """Constructor"""
        self.config = config
        self._client: Any = None
        self._write_api: Any = None
        self._query_api: Any = None
        self._connected: bool = False

        # 统计信息
        self._bars_saved: int = 0
        self._ticks_saved: int = 0
        self._bars_loaded: int = 0
        self._ticks_loaded: int = 0

    def connect(self) -> bool:
        """
        连接时序数据库

        优先使用InfluxDB，如不可用则使用SQLite
        """
        try:
            # 尝试连接InfluxDB
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS

            url = f"http://{self.config.influxdb_host}:{self.config.influxdb_port}"
            self._client = InfluxDBClient(
                url=url,
                token=f"{self.config.influxdb_username}:{self.config.influxdb_password}",
                org="-"
            )

            # 测试连接
            self._client.ping()

            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            self._query_api = self._client.query_api()
            self._connected = True

            # 确保数据库存在
            self._ensure_database()

            return True

        except ImportError:
            print("InfluxDB客户端未安装，使用SQLite作为fallback")
            return self._connect_sqlite()

        except Exception as e:
            print(f"InfluxDB连接失败: {e}，使用SQLite作为fallback")
            return self._connect_sqlite()

    def _connect_sqlite(self) -> bool:
        """连接SQLite作为fallback"""
        try:
            import sqlite3

            self._client = sqlite3.connect("data/market_data.db", check_same_thread=False)
            self._connected = True
            self._init_sqlite_tables()
            return True

        except Exception as e:
            print(f"SQLite连接失败: {e}")
            return False

    def _init_sqlite_tables(self) -> None:
        """初始化SQLite表结构"""
        cursor = self._client.cursor()

        # K线数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bar_data (
                vt_symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                datetime TIMESTAMP NOT NULL,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume REAL,
                turnover REAL,
                open_interest REAL,
                PRIMARY KEY (vt_symbol, interval, datetime)
            )
        """)

        # Tick数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tick_data (
                vt_symbol TEXT NOT NULL,
                datetime TIMESTAMP NOT NULL,
                last_price REAL,
                volume REAL,
                turnover REAL,
                bid_price_1 REAL,
                bid_volume_1 REAL,
                ask_price_1 REAL,
                ask_volume_1 REAL,
                PRIMARY KEY (vt_symbol, datetime)
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bar_symbol ON bar_data(vt_symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bar_datetime ON bar_data(datetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tick_symbol ON tick_data(vt_symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tick_datetime ON tick_data(datetime)")

        self._client.commit()

    def _ensure_database(self) -> None:
        """确保InfluxDB数据库存在"""
        try:
            from influxdb_client import BucketRetentionRules

            buckets_api = self._client.buckets_api()
            buckets = buckets_api.find_buckets().buckets

            bucket_names = [b.name for b in buckets]
            if self.config.influxdb_database not in bucket_names:
                buckets_api.create_bucket(
                    bucket_name=self.config.influxdb_database,
                    retention_rules=BucketRetentionRules(
                        type="expire",
                        every_seconds=0  # 永不过期
                    )
                )
        except Exception as e:
            print(f"创建数据库失败: {e}")

    def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            if hasattr(self._client, 'close'):
                self._client.close()
        self._connected = False

    def save_bar_data(self, bars: list[BarData]) -> bool:
        """
        保存K线数据

        Args:
            bars: K线数据列表

        Returns:
            是否保存成功
        """
        if not bars:
            return True

        try:
            if hasattr(self._client, 'write_api'):
                return self._save_bar_influxdb(bars)
            else:
                return self._save_bar_sqlite(bars)

        except Exception as e:
            print(f"保存K线数据失败: {e}")
            return False

    def _save_bar_influxdb(self, bars: list[BarData]) -> bool:
        """使用InfluxDB保存K线数据"""
        from influxdb_client import Point

        points = []
        for bar in bars:
            point = Point("bar_data") \
                .tag("vt_symbol", bar.vt_symbol) \
                .tag("interval", bar.interval.value) \
                .tag("exchange", bar.exchange.value) \
                .field("open_price", bar.open_price) \
                .field("high_price", bar.high_price) \
                .field("low_price", bar.low_price) \
                .field("close_price", bar.close_price) \
                .field("volume", bar.volume) \
                .field("turnover", bar.turnover) \
                .field("open_interest", bar.open_interest) \
                .time(bar.datetime)
            points.append(point)

        self._write_api.write(
            bucket=self.config.influxdb_database,
            record=points
        )

        self._bars_saved += len(bars)
        return True

    def _save_bar_sqlite(self, bars: list[BarData]) -> bool:
        """使用SQLite保存K线数据"""
        cursor = self._client.cursor()

        data = [
            (
                bar.vt_symbol,
                bar.interval.value,
                bar.datetime,
                bar.open_price,
                bar.high_price,
                bar.low_price,
                bar.close_price,
                bar.volume,
                bar.turnover,
                bar.open_interest
            )
            for bar in bars
        ]

        cursor.executemany(
            """
            INSERT OR REPLACE INTO bar_data
            (vt_symbol, interval, datetime, open_price, high_price, low_price, close_price, volume, turnover, open_interest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data
        )

        self._client.commit()
        self._bars_saved += len(bars)
        return True

    def load_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
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
        try:
            if hasattr(self._client, 'write_api'):
                return self._load_bar_influxdb(vt_symbol, interval, start, end)
            else:
                return self._load_bar_sqlite(vt_symbol, interval, start, end)

        except Exception as e:
            print(f"加载K线数据失败: {e}")
            return []

    def _load_bar_influxdb(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> list[BarData]:
        """从InfluxDB加载K线数据"""
        query = f'''
        from(bucket: "{self.config.influxdb_database}")
            |> range(start: {start.isoformat()}, stop: {end.isoformat()})
            |> filter(fn: (r) => r._measurement == "bar_data")
            |> filter(fn: (r) => r.vt_symbol == "{vt_symbol}")
            |> filter(fn: (r) => r.interval == "{interval}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        tables = self._query_api.query(query)

        bars = []
        for table in tables:
            for record in table.records:
                bar = BarData(
                    symbol=vt_symbol.split(".")[0],
                    exchange=Exchange(record.values.get("exchange", "UNKNOWN")),
                    datetime=record.get_time(),
                    interval=Interval(interval),
                    volume=record.values.get("volume", 0),
                    turnover=record.values.get("turnover", 0),
                    open_interest=record.values.get("open_interest", 0),
                    open_price=record.values.get("open_price", 0),
                    high_price=record.values.get("high_price", 0),
                    low_price=record.values.get("low_price", 0),
                    close_price=record.values.get("close_price", 0),
                    gateway_name="DB"
                )
                bars.append(bar)

        self._bars_loaded += len(bars)
        return sorted(bars, key=lambda x: x.datetime)

    def _load_bar_sqlite(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> list[BarData]:
        """从SQLite加载K线数据"""
        cursor = self._client.cursor()

        cursor.execute(
            """
            SELECT * FROM bar_data
            WHERE vt_symbol = ? AND interval = ? AND datetime >= ? AND datetime <= ?
            ORDER BY datetime
            """,
            (vt_symbol, interval, start, end)
        )

        bars = []
        for row in cursor.fetchall():
            bar = BarData(
                symbol=vt_symbol.split(".")[0],
                exchange=Exchange(row[0].split(".")[1]) if "." in row[0] else Exchange.SSE,
                datetime=datetime.fromisoformat(row[2]),
                interval=Interval(interval),
                volume=row[7],
                turnover=row[8],
                open_interest=row[9],
                open_price=row[3],
                high_price=row[4],
                low_price=row[5],
                close_price=row[6],
                gateway_name="DB"
            )
            bars.append(bar)

        self._bars_loaded += len(bars)
        return bars

    def save_tick_data(self, ticks: list[TickData]) -> bool:
        """
        保存Tick数据

        Args:
            ticks: Tick数据列表

        Returns:
            是否保存成功
        """
        if not ticks:
            return True

        try:
            if hasattr(self._client, 'write_api'):
                return self._save_tick_influxdb(ticks)
            else:
                return self._save_tick_sqlite(ticks)

        except Exception as e:
            print(f"保存Tick数据失败: {e}")
            return False

    def _save_tick_influxdb(self, ticks: list[TickData]) -> bool:
        """使用InfluxDB保存Tick数据"""
        from influxdb_client import Point

        points = []
        for tick in ticks:
            point = Point("tick_data") \
                .tag("vt_symbol", tick.vt_symbol) \
                .tag("exchange", tick.exchange.value) \
                .field("last_price", tick.last_price) \
                .field("volume", tick.volume) \
                .field("turnover", tick.turnover) \
                .field("bid_price_1", tick.bid_price_1) \
                .field("bid_volume_1", tick.bid_volume_1) \
                .field("ask_price_1", tick.ask_price_1) \
                .field("ask_volume_1", tick.ask_volume_1) \
                .time(tick.datetime)
            points.append(point)

        self._write_api.write(
            bucket=self.config.influxdb_database,
            record=points
        )

        self._ticks_saved += len(ticks)
        return True

    def _save_tick_sqlite(self, ticks: list[TickData]) -> bool:
        """使用SQLite保存Tick数据"""
        cursor = self._client.cursor()

        data = [
            (
                tick.vt_symbol,
                tick.datetime,
                tick.last_price,
                tick.volume,
                tick.turnover,
                tick.bid_price_1,
                tick.bid_volume_1,
                tick.ask_price_1,
                tick.ask_volume_1
            )
            for tick in ticks
        ]

        cursor.executemany(
            """
            INSERT OR REPLACE INTO tick_data
            (vt_symbol, datetime, last_price, volume, turnover, bid_price_1, bid_volume_1, ask_price_1, ask_volume_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data
        )

        self._client.commit()
        self._ticks_saved += len(ticks)
        return True

    def load_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
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
        try:
            if hasattr(self._client, 'write_api'):
                return self._load_tick_influxdb(vt_symbol, start, end)
            else:
                return self._load_tick_sqlite(vt_symbol, start, end)

        except Exception as e:
            print(f"加载Tick数据失败: {e}")
            return []

    def _load_tick_influxdb(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> list[TickData]:
        """从InfluxDB加载Tick数据"""
        query = f'''
        from(bucket: "{self.config.influxdb_database}")
            |> range(start: {start.isoformat()}, stop: {end.isoformat()})
            |> filter(fn: (r) => r._measurement == "tick_data")
            |> filter(fn: (r) => r.vt_symbol == "{vt_symbol}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        tables = self._query_api.query(query)

        ticks = []
        for table in tables:
            for record in table.records:
                tick = TickData(
                    symbol=vt_symbol.split(".")[0],
                    exchange=Exchange(record.values.get("exchange", "UNKNOWN")),
                    datetime=record.get_time(),
                    last_price=record.values.get("last_price", 0),
                    volume=record.values.get("volume", 0),
                    turnover=record.values.get("turnover", 0),
                    bid_price_1=record.values.get("bid_price_1", 0),
                    bid_volume_1=record.values.get("bid_volume_1", 0),
                    ask_price_1=record.values.get("ask_price_1", 0),
                    ask_volume_1=record.values.get("ask_volume_1", 0),
                    gateway_name="DB"
                )
                ticks.append(tick)

        self._ticks_loaded += len(ticks)
        return sorted(ticks, key=lambda x: x.datetime)

    def _load_tick_sqlite(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> list[TickData]:
        """从SQLite加载Tick数据"""
        cursor = self._client.cursor()

        cursor.execute(
            """
            SELECT * FROM tick_data
            WHERE vt_symbol = ? AND datetime >= ? AND datetime <= ?
            ORDER BY datetime
            """,
            (vt_symbol, start, end)
        )

        ticks = []
        for row in cursor.fetchall():
            tick = TickData(
                symbol=vt_symbol.split(".")[0],
                exchange=Exchange(row[0].split(".")[1]) if "." in row[0] else Exchange.SSE,
                datetime=datetime.fromisoformat(row[1]),
                last_price=row[2],
                volume=row[3],
                turnover=row[4],
                bid_price_1=row[5],
                bid_volume_1=row[6],
                ask_price_1=row[7],
                ask_volume_1=row[8],
                gateway_name="DB"
            )
            ticks.append(tick)

        self._ticks_loaded += len(ticks)
        return ticks

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "connected": self._connected,
            "bars_saved": self._bars_saved,
            "ticks_saved": self._ticks_saved,
            "bars_loaded": self._bars_loaded,
            "ticks_loaded": self._ticks_loaded,
        }
