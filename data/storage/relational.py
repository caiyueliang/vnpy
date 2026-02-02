"""
关系数据库模块

封装PostgreSQL用于存储交易相关数据
"""

from datetime import datetime
from typing import Any


class RelationalDB:
    """
    关系数据库

    用于存储交易记录、账户信息、策略配置等
    支持PostgreSQL和SQLite（作为fallback）
    """

    def __init__(self, config: Any) -> None:
        """Constructor"""
        self.config = config
        self._connection: Any = None
        self._cursor: Any = None
        self._connected: bool = False

        # 统计信息
        self._queries_executed: int = 0

    def connect(self) -> bool:
        """
        连接关系数据库

        优先使用PostgreSQL，如不可用则使用SQLite
        """
        try:
            # 尝试连接PostgreSQL
            import psycopg2

            self._connection = psycopg2.connect(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_username,
                password=self.config.postgres_password
            )
            self._cursor = self._connection.cursor()
            self._connected = True

            # 初始化表结构
            self._init_postgres_tables()

            return True

        except ImportError:
            print("PostgreSQL客户端未安装，使用SQLite作为fallback")
            return self._connect_sqlite()

        except Exception as e:
            print(f"PostgreSQL连接失败: {e}，使用SQLite作为fallback")
            return self._connect_sqlite()

    def _connect_sqlite(self) -> bool:
        """连接SQLite作为fallback"""
        try:
            import sqlite3

            self._connection = sqlite3.connect("data/trading_data.db", check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._cursor = self._connection.cursor()
            self._connected = True

            # 初始化表结构
            self._init_sqlite_tables()

            return True

        except Exception as e:
            print(f"SQLite连接失败: {e}")
            return False

    def _init_postgres_tables(self) -> None:
        """初始化PostgreSQL表结构"""
        # 交易记录表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                trade_id VARCHAR(50) UNIQUE NOT NULL,
                vt_symbol VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                offset VARCHAR(10) NOT NULL,
                price DECIMAL(18, 4) NOT NULL,
                volume DECIMAL(18, 4) NOT NULL,
                pnl DECIMAL(18, 4),
                commission DECIMAL(18, 4),
                trade_time TIMESTAMP NOT NULL,
                strategy_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 订单记录表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_id VARCHAR(50) UNIQUE NOT NULL,
                vt_symbol VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                offset VARCHAR(10) NOT NULL,
                order_type VARCHAR(20) NOT NULL,
                price DECIMAL(18, 4),
                volume DECIMAL(18, 4) NOT NULL,
                traded DECIMAL(18, 4) DEFAULT 0,
                status VARCHAR(20) NOT NULL,
                order_time TIMESTAMP NOT NULL,
                strategy_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 持仓记录表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id SERIAL PRIMARY KEY,
                vt_symbol VARCHAR(50) UNIQUE NOT NULL,
                direction VARCHAR(10) NOT NULL,
                volume DECIMAL(18, 4) NOT NULL,
                price DECIMAL(18, 4) NOT NULL,
                pnl DECIMAL(18, 4) DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 账户资金表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS account (
                id SERIAL PRIMARY KEY,
                balance DECIMAL(18, 4) NOT NULL,
                available DECIMAL(18, 4) NOT NULL,
                frozen DECIMAL(18, 4) DEFAULT 0,
                margin DECIMAL(18, 4) DEFAULT 0,
                commission DECIMAL(18, 4) DEFAULT 0,
                pnl DECIMAL(18, 4) DEFAULT 0,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 策略配置表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                class_name VARCHAR(100) NOT NULL,
                vt_symbols TEXT NOT NULL,
                setting JSONB,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 每日收益表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_returns (
                id SERIAL PRIMARY KEY,
                date DATE UNIQUE NOT NULL,
                starting_balance DECIMAL(18, 4) NOT NULL,
                ending_balance DECIMAL(18, 4) NOT NULL,
                total_pnl DECIMAL(18, 4) NOT NULL,
                commission DECIMAL(18, 4) DEFAULT 0,
                slippage DECIMAL(18, 4) DEFAULT 0,
                return_pct DECIMAL(8, 4) NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(vt_symbol)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(trade_time)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(vt_symbol)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_time ON orders(order_time)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_returns_date ON daily_returns(date)")

        self._connection.commit()

    def _init_sqlite_tables(self) -> None:
        """初始化SQLite表结构"""
        # 交易记录表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE NOT NULL,
                vt_symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                offset TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                pnl REAL,
                commission REAL,
                trade_time TIMESTAMP NOT NULL,
                strategy_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 订单记录表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                vt_symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                offset TEXT NOT NULL,
                order_type TEXT NOT NULL,
                price REAL,
                volume REAL NOT NULL,
                traded REAL DEFAULT 0,
                status TEXT NOT NULL,
                order_time TIMESTAMP NOT NULL,
                strategy_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 持仓记录表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vt_symbol TEXT UNIQUE NOT NULL,
                direction TEXT NOT NULL,
                volume REAL NOT NULL,
                price REAL NOT NULL,
                pnl REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 账户资金表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL NOT NULL,
                available REAL NOT NULL,
                frozen REAL DEFAULT 0,
                margin REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                pnl REAL DEFAULT 0,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 策略配置表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                class_name TEXT NOT NULL,
                vt_symbols TEXT NOT NULL,
                setting TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 每日收益表
        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE NOT NULL,
                starting_balance REAL NOT NULL,
                ending_balance REAL NOT NULL,
                total_pnl REAL NOT NULL,
                commission REAL DEFAULT 0,
                slippage REAL DEFAULT 0,
                return_pct REAL NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(vt_symbol)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(trade_time)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(vt_symbol)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_time ON orders(order_time)")
        self._cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_returns_date ON daily_returns(date)")

        self._connection.commit()

    def disconnect(self) -> None:
        """断开连接"""
        if self._cursor:
            self._cursor.close()
        if self._connection:
            self._connection.close()
        self._connected = False

    def execute(self, sql: str, params: tuple = ()) -> list:
        """
        执行SQL语句

        Args:
            sql: SQL语句
            params: 参数

        Returns:
            查询结果
        """
        try:
            self._cursor.execute(sql, params)

            if sql.strip().upper().startswith("SELECT"):
                results = self._cursor.fetchall()
                self._queries_executed += 1
                return results
            else:
                self._connection.commit()
                self._queries_executed += 1
                return []

        except Exception as e:
            self._connection.rollback()
            print(f"SQL执行失败: {e}")
            return []

    def insert_trade(self, trade_data: dict) -> bool:
        """
        插入交易记录

        Args:
            trade_data: 交易数据字典

        Returns:
            是否插入成功
        """
        try:
            sql = """
                INSERT INTO trades
                (trade_id, vt_symbol, direction, offset, price, volume, pnl, commission, trade_time, strategy_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                trade_data.get("trade_id"),
                trade_data.get("vt_symbol"),
                trade_data.get("direction"),
                trade_data.get("offset"),
                trade_data.get("price"),
                trade_data.get("volume"),
                trade_data.get("pnl", 0),
                trade_data.get("commission", 0),
                trade_data.get("trade_time"),
                trade_data.get("strategy_name", "")
            )

            self._cursor.execute(sql, params)
            self._connection.commit()
            return True

        except Exception as e:
            self._connection.rollback()
            print(f"插入交易记录失败: {e}")
            return False

    def insert_order(self, order_data: dict) -> bool:
        """
        插入订单记录

        Args:
            order_data: 订单数据字典

        Returns:
            是否插入成功
        """
        try:
            sql = """
                INSERT INTO orders
                (order_id, vt_symbol, direction, offset, order_type, price, volume, status, order_time, strategy_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                order_data.get("order_id"),
                order_data.get("vt_symbol"),
                order_data.get("direction"),
                order_data.get("offset"),
                order_data.get("order_type"),
                order_data.get("price"),
                order_data.get("volume"),
                order_data.get("status"),
                order_data.get("order_time"),
                order_data.get("strategy_name", "")
            )

            self._cursor.execute(sql, params)
            self._connection.commit()
            return True

        except Exception as e:
            self._connection.rollback()
            print(f"插入订单记录失败: {e}")
            return False

    def update_position(self, position_data: dict) -> bool:
        """
        更新持仓记录

        Args:
            position_data: 持仓数据字典

        Returns:
            是否更新成功
        """
        try:
            # 先检查是否存在
            self._cursor.execute(
                "SELECT id FROM positions WHERE vt_symbol = ?",
                (position_data.get("vt_symbol"),)
            )
            result = self._cursor.fetchone()

            if result:
                # 更新
                sql = """
                    UPDATE positions
                    SET direction = ?, volume = ?, price = ?, pnl = ?, updated_at = ?
                    WHERE vt_symbol = ?
                """
                params = (
                    position_data.get("direction"),
                    position_data.get("volume"),
                    position_data.get("price"),
                    position_data.get("pnl", 0),
                    datetime.now(),
                    position_data.get("vt_symbol")
                )
            else:
                # 插入
                sql = """
                    INSERT INTO positions
                    (vt_symbol, direction, volume, price, pnl)
                    VALUES (?, ?, ?, ?, ?)
                """
                params = (
                    position_data.get("vt_symbol"),
                    position_data.get("direction"),
                    position_data.get("volume"),
                    position_data.get("price"),
                    position_data.get("pnl", 0)
                )

            self._cursor.execute(sql, params)
            self._connection.commit()
            return True

        except Exception as e:
            self._connection.rollback()
            print(f"更新持仓记录失败: {e}")
            return False

    def record_daily_return(self, return_data: dict) -> bool:
        """
        记录每日收益

        Args:
            return_data: 收益数据字典

        Returns:
            是否记录成功
        """
        try:
            sql = """
                INSERT OR REPLACE INTO daily_returns
                (date, starting_balance, ending_balance, total_pnl, commission, slippage, return_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                return_data.get("date"),
                return_data.get("starting_balance"),
                return_data.get("ending_balance"),
                return_data.get("total_pnl"),
                return_data.get("commission", 0),
                return_data.get("slippage", 0),
                return_data.get("return_pct")
            )

            self._cursor.execute(sql, params)
            self._connection.commit()
            return True

        except Exception as e:
            self._connection.rollback()
            print(f"记录每日收益失败: {e}")
            return False

    def get_trades(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        strategy_name: str | None = None,
        vt_symbol: str | None = None
    ) -> list[dict]:
        """
        获取交易记录

        Args:
            start_date: 开始日期
            end_date: 结束日期
            strategy_name: 策略名称
            vt_symbol: 合约代码

        Returns:
            交易记录列表
        """
        sql = "SELECT * FROM trades WHERE 1=1"
        params = []

        if start_date:
            sql += " AND trade_time >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND trade_time <= ?"
            params.append(end_date)
        if strategy_name:
            sql += " AND strategy_name = ?"
            params.append(strategy_name)
        if vt_symbol:
            sql += " AND vt_symbol = ?"
            params.append(vt_symbol)

        sql += " ORDER BY trade_time DESC"

        self._cursor.execute(sql, params)
        rows = self._cursor.fetchall()

        return [dict(row) for row in rows]

    def get_daily_returns(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None
    ) -> list[dict]:
        """
        获取每日收益记录

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            每日收益记录列表
        """
        sql = "SELECT * FROM daily_returns WHERE 1=1"
        params = []

        if start_date:
            sql += " AND date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND date <= ?"
            params.append(end_date)

        sql += " ORDER BY date ASC"

        self._cursor.execute(sql, params)
        rows = self._cursor.fetchall()

        return [dict(row) for row in rows]

    def get_positions(self) -> list[dict]:
        """
        获取当前持仓

        Returns:
            持仓列表
        """
        self._cursor.execute("SELECT * FROM positions WHERE volume != 0")
        rows = self._cursor.fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = {
            "connected": self._connected,
            "queries_executed": self._queries_executed,
        }

        if self._connected:
            try:
                # 获取各表记录数
                self._cursor.execute("SELECT COUNT(*) FROM trades")
                stats["total_trades"] = self._cursor.fetchone()[0]

                self._cursor.execute("SELECT COUNT(*) FROM orders")
                stats["total_orders"] = self._cursor.fetchone()[0]

                self._cursor.execute("SELECT COUNT(*) FROM positions")
                stats["total_positions"] = self._cursor.fetchone()[0]

                self._cursor.execute("SELECT COUNT(*) FROM daily_returns")
                stats["total_daily_records"] = self._cursor.fetchone()[0]

            except Exception as e:
                print(f"获取统计信息失败: {e}")

        return stats
