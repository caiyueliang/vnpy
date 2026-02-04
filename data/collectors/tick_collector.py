"""
Tick数据(L2)采集器

采集A股市场Tick级别数据：
1. 实时Tick数据（买卖十档、成交明细）
2. 历史Tick数据
3. 逐笔成交数据
4. 委托队列数据

支持数据源：
- AKShare（免费，有限支持）
- Tushare（付费，完整支持）
- RQData（付费，完整支持）
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import time

import pandas as pd
import numpy as np

from .base import DataCollector, CollectorConfig, DataSource


class TickDataType(Enum):
    """Tick数据类型"""
    QUOTE = "quote"           # 行情快照（十档）
    TRADE = "trade"           # 成交数据
    ORDER = "order"           # 委托数据
    TICK = "tick"             # 合并Tick


@dataclass
class DepthLevel:
    """深度数据层级"""
    price: float              # 价格
    volume: int               # 数量
    order_count: int = 0      # 订单数（L2数据）


@dataclass
class TickData:
    """
    Tick数据结构

    包含完整的L2级别市场数据
    """
    # 基础信息
    symbol: str                           # 股票代码
    exchange: str                         # 交易所
    datetime: datetime                    # 时间戳
    data_type: TickDataType = TickDataType.TICK

    # 价格信息
    last_price: float = 0.0               # 最新价
    open_price: float = 0.0               # 开盘价
    high_price: float = 0.0               # 最高价
    low_price: float = 0.0                # 最低价
    pre_close: float = 0.0                # 昨收价

    # 成交量额
    volume: int = 0                       # 成交量
    turnover: float = 0.0                 # 成交额
    open_interest: int = 0                # 持仓量（期货）

    # 买卖盘（十档）
    bid_prices: List[float] = field(default_factory=lambda: [0.0] * 10)
    bid_volumes: List[int] = field(default_factory=lambda: [0] * 10)
    ask_prices: List[float] = field(default_factory=lambda: [0.0] * 10)
    ask_volumes: List[int] = field(default_factory=lambda: [0] * 10)

    # L2数据
    bid_order_counts: List[int] = field(default_factory=lambda: [0] * 10)
    ask_order_counts: List[int] = field(default_factory=lambda: [0] * 10)

    # 额外信息
    upper_limit: float = 0.0              # 涨停价
    lower_limit: float = 0.0              # 跌停价
    avg_price: float = 0.0                # 均价

    def get_spread(self) -> float:
        """获取买卖价差"""
        if self.bid_prices[0] > 0 and self.ask_prices[0] > 0:
            return self.ask_prices[0] - self.bid_prices[0]
        return 0.0

    def get_mid_price(self) -> float:
        """获取中间价"""
        if self.bid_prices[0] > 0 and self.ask_prices[0] > 0:
            return (self.bid_prices[0] + self.ask_prices[0]) / 2
        return self.last_price

    def get_bid_ask_imbalance(self) -> float:
        """
        获取买卖盘不平衡度

        Returns:
            -1.0 ~ 1.0，正值表示买盘强，负值表示卖盘强
        """
        total_bid = sum(self.bid_volumes)
        total_ask = sum(self.ask_volumes)
        total = total_bid + total_ask

        if total == 0:
            return 0.0

        return (total_bid - total_ask) / total


@dataclass
class TradeData:
    """逐笔成交数据"""
    symbol: str                           # 股票代码
    exchange: str                         # 交易所
    datetime: datetime                    # 成交时间
    trade_id: str = ""                    # 成交编号
    price: float = 0.0                    # 成交价格
    volume: int = 0                       # 成交量
    side: str = ""                        # 方向 (buy/sell)
    order_kind: str = ""                  # 订单类型
    bs_flag: str = ""                     # 内外盘标志


class TickCollector(DataCollector):
    """
    Tick数据(L2)采集器

    支持多种数据源获取Tick级别数据
    """

    def __init__(self, config: Optional[CollectorConfig] = None) -> None:
        """Constructor"""
        if config is None:
            config = CollectorConfig(source=DataSource.AKSHARE)
        super().__init__(config)

        self._ak = None
        self._ts = None
        self._rq = None

        # 实时订阅
        self._subscribed_symbols: set = set()
        self._tick_callbacks: List[Callable] = []
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        # 缓存
        self._tick_cache: Dict[str, TickData] = {}
        self._cache_lock = threading.Lock()

    def connect(self) -> bool:
        """
        连接数据源

        Returns:
            是否连接成功
        """
        try:
            if self.config.source == DataSource.AKSHARE:
                import akshare as ak
                self._ak = ak
                self._connected = True
                return True

            elif self.config.source == DataSource.TUSHARE:
                import tushare as ts
                self._ts = ts.pro_api(self.config.api_key)
                self._connected = True
                return True

            elif self.config.source == DataSource.RQDATA:
                import rqdatac as rq
                rq.init(
                    username=self.config.api_key,
                    password=self.config.api_secret
                )
                self._rq = rq
                self._connected = True
                return True

            else:
                print(f"不支持的数据源: {self.config.source}")
                return False

        except ImportError as e:
            print(f"数据源库未安装: {e}")
            return False
        except Exception as e:
            print(f"连接数据源失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        self.stop_realtime()
        self._connected = False
        self._ak = None
        self._ts = None
        self._rq = None

    def get_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """
        获取历史Tick数据

        Args:
            vt_symbol: 合约代码 (如 "000001.SZ")
            start: 开始时间
            end: 结束时间

        Returns:
            Tick数据列表
        """
        if not self._connected:
            return []

        try:
            self._requests_count += 1

            if self.config.source == DataSource.AKSHARE:
                ticks = self._get_tick_from_akshare(vt_symbol, start, end)
            elif self.config.source == DataSource.TUSHARE:
                ticks = self._get_tick_from_tushare(vt_symbol, start, end)
            elif self.config.source == DataSource.RQDATA:
                ticks = self._get_tick_from_rqdata(vt_symbol, start, end)
            else:
                ticks = []

            self._success_count += 1
            return ticks

        except Exception as e:
            self._error_count += 1
            print(f"获取Tick数据失败: {e}")
            return []

    def _get_tick_from_akshare(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """从AKShare获取Tick数据"""
        symbol, exchange = self._parse_vt_symbol(vt_symbol)

        # AKShare暂不支持历史Tick数据，只能获取当日分时数据
        if (end - start).days > 1:
            print("AKShare仅支持获取当日分时数据")
            return []

        try:
            # 获取分时数据
            df = self._ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period="1",
                adjust="qfq"
            )

            if df is None or df.empty:
                return []

            # 过滤时间范围
            df['日期'] = pd.to_datetime(df['日期'])
            df = df[(df['日期'] >= start) & (df['日期'] <= end)]

            ticks = []
            for _, row in df.iterrows():
                tick = TickData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=pd.to_datetime(row['日期']),
                    last_price=float(row['收盘']),
                    open_price=float(row['开盘']),
                    high_price=float(row['最高']),
                    low_price=float(row['最低']),
                    volume=int(row['成交量']),
                    turnover=float(row.get('成交额', 0))
                )
                ticks.append(tick)

            return ticks

        except Exception as e:
            print(f"AKShare获取Tick数据失败: {e}")
            return []

    def _get_tick_from_tushare(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """从Tushare获取Tick数据（需要付费权限）"""
        if not self._ts:
            return []

        symbol, exchange = self._parse_vt_symbol(vt_symbol)

        try:
            # Tushare的tick数据接口
            df = self._ts.pro_bar(
                ts_code=self._to_ts_code(symbol, exchange),
                freq='1min',
                start_date=start.strftime('%Y%m%d'),
                end_date=end.strftime('%Y%m%d')
            )

            if df is None or df.empty:
                return []

            ticks = []
            for _, row in df.iterrows():
                tick = TickData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=pd.to_datetime(row['trade_time']),
                    last_price=float(row['close']),
                    open_price=float(row['open']),
                    high_price=float(row['high']),
                    low_price=float(row['low']),
                    volume=int(row['vol']),
                    turnover=float(row.get('amount', 0))
                )
                ticks.append(tick)

            return ticks

        except Exception as e:
            print(f"Tushare获取Tick数据失败: {e}")
            return []

    def _get_tick_from_rqdata(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """从RQData获取Tick数据（需要付费权限）"""
        if not self._rq:
            return []

        try:
            symbol, exchange = self._parse_vt_symbol(vt_symbol)
            rq_symbol = f"{symbol}.{exchange}"

            # 获取Tick数据
            df = self._rq.get_price(
                rq_symbol,
                start_date=start,
                end_date=end,
                frequency='tick'
            )

            if df is None or df.empty:
                return []

            ticks = []
            for timestamp, row in df.iterrows():
                tick = TickData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=timestamp,
                    last_price=float(row.get('last', 0)),
                    open_price=float(row.get('open', 0)),
                    high_price=float(row.get('high', 0)),
                    low_price=float(row.get('low', 0)),
                    volume=int(row.get('volume', 0)),
                    turnover=float(row.get('total_turnover', 0)),
                    bid_prices=[float(row.get(f'bid_{i}', 0)) for i in range(1, 11)],
                    bid_volumes=[int(row.get(f'bid_volume_{i}', 0)) for i in range(1, 11)],
                    ask_prices=[float(row.get(f'ask_{i}', 0)) for i in range(1, 11)],
                    ask_volumes=[int(row.get(f'ask_volume_{i}', 0)) for i in range(1, 11)]
                )
                ticks.append(tick)

            return ticks

        except Exception as e:
            print(f"RQData获取Tick数据失败: {e}")
            return []

    def get_realtime_tick(self, vt_symbol: str) -> Optional[TickData]:
        """
        获取实时Tick数据

        Args:
            vt_symbol: 合约代码

        Returns:
            实时Tick数据
        """
        if not self._connected:
            return None

        try:
            self._requests_count += 1

            symbol, exchange = self._parse_vt_symbol(vt_symbol)

            if self.config.source == DataSource.AKSHARE:
                tick = self._get_realtime_from_akshare(symbol, exchange)
            else:
                tick = None

            if tick:
                self._success_count += 1
                # 更新缓存
                with self._cache_lock:
                    self._tick_cache[vt_symbol] = tick

            return tick

        except Exception as e:
            self._error_count += 1
            print(f"获取实时Tick失败: {e}")
            return None

    def _get_realtime_from_akshare(
        self,
        symbol: str,
        exchange: str
    ) -> Optional[TickData]:
        """从AKShare获取实时Tick"""
        try:
            # 获取实时行情
            df = self._ak.stock_zh_a_spot_em()
            df = df[df['代码'] == symbol]

            if df.empty:
                return None

            row = df.iloc[0]

            tick = TickData(
                symbol=symbol,
                exchange=exchange,
                datetime=datetime.now(),
                last_price=float(row.get('最新价', 0)),
                open_price=float(row.get('今开', 0)),
                high_price=float(row.get('最高', 0)),
                low_price=float(row.get('最低', 0)),
                pre_close=float(row.get('昨收', 0)),
                volume=int(row.get('成交量', 0)),
                turnover=float(row.get('成交额', 0)),
                bid_prices=[float(row.get('买一', 0)),
                           float(row.get('买二', 0)),
                           float(row.get('买三', 0)),
                           float(row.get('买四', 0)),
                           float(row.get('买五', 0))] + [0.0] * 5,
                bid_volumes=[int(row.get('买一量', 0)),
                            int(row.get('买二量', 0)),
                            int(row.get('买三量', 0)),
                            int(row.get('买四量', 0)),
                            int(row.get('买五量', 0))] + [0] * 5,
                ask_prices=[float(row.get('卖一', 0)),
                           float(row.get('卖二', 0)),
                           float(row.get('卖三', 0)),
                           float(row.get('卖四', 0)),
                           float(row.get('卖五', 0))] + [0.0] * 5,
                ask_volumes=[int(row.get('卖一量', 0)),
                            int(row.get('卖二量', 0)),
                            int(row.get('卖三量', 0)),
                            int(row.get('卖四量', 0)),
                            int(row.get('卖五量', 0))] + [0] * 5,
                upper_limit=float(row.get('最高', 0)) * 1.1,
                lower_limit=float(row.get('最低', 0)) * 0.9,
                avg_price=float(row.get('均价', 0))
            )

            return tick

        except Exception as e:
            print(f"AKShare获取实时Tick失败: {e}")
            return None

    def subscribe(self, vt_symbols: List[str]) -> bool:
        """
        订阅实时Tick数据

        Args:
            vt_symbols: 合约代码列表

        Returns:
            是否订阅成功
        """
        if not self._connected:
            return False

        self._subscribed_symbols.update(vt_symbols)
        return True

    def unsubscribe(self, vt_symbols: List[str]) -> None:
        """
        取消订阅

        Args:
            vt_symbols: 合约代码列表
        """
        for symbol in vt_symbols:
            self._subscribed_symbols.discard(symbol)

    def register_callback(self, callback: Callable[[TickData], None]) -> None:
        """
        注册Tick数据回调

        Args:
            callback: 回调函数，接收TickData参数
        """
        if callback not in self._tick_callbacks:
            self._tick_callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[TickData], None]) -> None:
        """注销回调"""
        if callback in self._tick_callbacks:
            self._tick_callbacks.remove(callback)

    def start_realtime(self, interval: float = 1.0) -> bool:
        """
        启动实时数据推送

        Args:
            interval: 轮询间隔（秒）

        Returns:
            是否启动成功
        """
        if self._running:
            return True

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_realtime_data,
            args=(interval,),
            daemon=True
        )
        self._thread.start()
        return True

    def stop_realtime(self) -> None:
        """停止实时数据推送"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _poll_realtime_data(self, interval: float) -> None:
        """轮询实时数据"""
        while self._running:
            try:
                for vt_symbol in list(self._subscribed_symbols):
                    tick = self.get_realtime_tick(vt_symbol)
                    if tick:
                        # 触发回调
                        for callback in self._tick_callbacks:
                            try:
                                callback(tick)
                            except Exception as e:
                                print(f"Tick回调执行失败: {e}")

                time.sleep(interval)

            except Exception as e:
                print(f"轮询实时数据失败: {e}")
                time.sleep(interval)

    def get_cached_tick(self, vt_symbol: str) -> Optional[TickData]:
        """
        获取缓存的Tick数据

        Args:
            vt_symbol: 合约代码

        Returns:
            缓存的Tick数据
        """
        with self._cache_lock:
            return self._tick_cache.get(vt_symbol)

    def get_all_cached_ticks(self) -> Dict[str, TickData]:
        """
        获取所有缓存的Tick数据

        Returns:
            合约代码到Tick数据的映射
        """
        with self._cache_lock:
            return self._tick_cache.copy()

    def get_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """
        获取K线数据（Tick采集器不支持）

        Note: Tick采集器专门用于采集Tick数据
        """
        print("Tick采集器不支持K线数据获取，请使用AKShareCollector")
        return []

    def _parse_vt_symbol(self, vt_symbol: str) -> tuple[str, str]:
        """
        解析vt_symbol

        Args:
            vt_symbol: 合约代码 (如 "000001.SZ")

        Returns:
            (symbol, exchange)
        """
        if "." in vt_symbol:
            symbol, exchange = vt_symbol.split(".")
            return symbol, exchange
        return vt_symbol, "SZ"

    def _to_ts_code(self, symbol: str, exchange: str) -> str:
        """转换为Tushare代码格式"""
        return f"{symbol}.{exchange.upper()}"

    def get_tick_statistics(self, vt_symbol: str) -> Dict:
        """
        获取Tick数据统计信息

        Args:
            vt_symbol: 合约代码

        Returns:
            统计信息字典
        """
        tick = self.get_cached_tick(vt_symbol)
        if not tick:
            return {}

        return {
            "symbol": tick.symbol,
            "last_price": tick.last_price,
            "spread": tick.get_spread(),
            "mid_price": tick.get_mid_price(),
            "imbalance": tick.get_bid_ask_imbalance(),
            "bid_volume_total": sum(tick.bid_volumes),
            "ask_volume_total": sum(tick.ask_volumes),
            "timestamp": tick.datetime
        }

    def resample_to_bar(
        self,
        ticks: List[TickData],
        interval: str = "1min"
    ) -> pd.DataFrame:
        """
        将Tick数据重采样为K线

        Args:
            ticks: Tick数据列表
            interval: 目标周期

        Returns:
            K线DataFrame
        """
        if not ticks:
            return pd.DataFrame()

        # 创建DataFrame
        data = []
        for tick in ticks:
            data.append({
                'datetime': tick.datetime,
                'open': tick.last_price,
                'high': tick.last_price,
                'low': tick.last_price,
                'close': tick.last_price,
                'volume': tick.volume,
                'turnover': tick.turnover
            })

        df = pd.DataFrame(data)
        df.set_index('datetime', inplace=True)

        # 重采样
        resampled = df.resample(interval).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'turnover': 'sum'
        }).dropna()

        return resampled
