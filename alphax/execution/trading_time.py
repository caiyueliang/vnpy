"""
交易时间控制系统

控制交易时间，避开开盘和收盘的高波动时段。
"""

from datetime import datetime, time, timedelta
from typing import Optional, List, Tuple, Dict
from enum import Enum
import pandas as pd


class TradingSession(Enum):
    """交易时段"""
    PRE_MARKET = "pre_market"          # 盘前
    OPEN_AUCTION = "open_auction"      # 开盘集合竞价
    OPEN_FIRST_15 = "open_first_15"    # 开盘后15分钟
    MORNING_SESSION = "morning_session" # 上午交易时段
    NOON_BREAK = "noon_break"          # 午休
    AFTERNOON_SESSION = "afternoon_session"  # 下午交易时段
    CLOSE_LAST_15 = "close_last_15"    # 收盘前15分钟
    CLOSE_AUCTION = "close_auction"    # 收盘集合竞价
    POST_MARKET = "post_market"        # 盘后


class TradingTimeController:
    """
    交易时间控制器

    管理A股交易时间，支持避开高波动时段。
    """

    # A股交易时间定义
    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(15, 0)
    MORNING_END = time(11, 30)
    AFTERNOON_START = time(13, 0)

    # 集合竞价时间
    OPEN_AUCTION_START = time(9, 15)
    OPEN_AUCTION_END = time(9, 25)
    CLOSE_AUCTION_START = time(14, 57)
    CLOSE_AUCTION_END = time(15, 0)

    def __init__(
        self,
        avoid_open_minutes: int = 15,
        avoid_close_minutes: int = 15,
        avoid_noon_break: bool = True,
        enable_auction: bool = False
    ):
        """
        初始化交易时间控制器

        Args:
            avoid_open_minutes: 开盘后避免交易的分钟数
            avoid_close_minutes: 收盘前避免交易的分钟数
            avoid_noon_break: 是否避开午休时段
            enable_auction: 是否允许集合竞价交易
        """
        self.avoid_open_minutes = avoid_open_minutes
        self.avoid_close_minutes = avoid_close_minutes
        self.avoid_noon_break = avoid_noon_break
        self.enable_auction = enable_auction

        # 计算避开时段
        self._calculate_avoid_periods()

    def _calculate_avoid_periods(self) -> None:
        """计算需要避开的时段"""
        self.avoid_periods: List[Tuple[time, time]] = []

        # 开盘避开时段
        if self.avoid_open_minutes > 0:
            avoid_start = self.MARKET_OPEN
            avoid_end = (
                datetime.combine(datetime.today(), self.MARKET_OPEN) +
                timedelta(minutes=self.avoid_open_minutes)
            ).time()
            self.avoid_periods.append((avoid_start, avoid_end))

        # 收盘避开时段
        if self.avoid_close_minutes > 0:
            avoid_start = (
                datetime.combine(datetime.today(), self.MARKET_CLOSE) -
                timedelta(minutes=self.avoid_close_minutes)
            ).time()
            avoid_end = self.MARKET_CLOSE
            self.avoid_periods.append((avoid_start, avoid_end))

        # 午休时段
        if self.avoid_noon_break:
            self.avoid_periods.append((self.MORNING_END, self.AFTERNOON_START))

        # 集合竞价时段（如果不允许）
        if not self.enable_auction:
            self.avoid_periods.append((self.OPEN_AUCTION_START, self.OPEN_AUCTION_END))
            self.avoid_periods.append((self.CLOSE_AUCTION_START, self.CLOSE_AUCTION_END))

    def is_trading_time(self, dt: Optional[datetime] = None) -> bool:
        """
        检查当前是否为可交易时间

        Args:
            dt: 检查的时间，None表示当前时间

        Returns:
            是否可交易
        """
        if dt is None:
            dt = datetime.now()

        current_time = dt.time()

        # 检查是否在交易时段内
        if not self._is_market_open(current_time):
            return False

        # 检查是否在避开时段内
        for avoid_start, avoid_end in self.avoid_periods:
            if avoid_start <= current_time <= avoid_end:
                return False

        return True

    def _is_market_open(self, t: time) -> bool:
        """检查时间是否在交易时段内"""
        # 上午时段
        if self.MARKET_OPEN <= t <= self.MORNING_END:
            return True
        # 下午时段
        if self.AFTERNOON_START <= t <= self.MARKET_CLOSE:
            return True
        return False

    def get_current_session(self, dt: Optional[datetime] = None) -> TradingSession:
        """
        获取当前交易时段

        Args:
            dt: 检查的时间，None表示当前时间

        Returns:
            交易时段
        """
        if dt is None:
            dt = datetime.now()

        current_time = dt.time()

        # 盘前
        if current_time < self.OPEN_AUCTION_START:
            return TradingSession.PRE_MARKET

        # 开盘集合竞价
        if self.OPEN_AUCTION_START <= current_time <= self.OPEN_AUCTION_END:
            return TradingSession.OPEN_AUCTION

        # 开盘后15分钟
        open_15_end = (
            datetime.combine(datetime.today(), self.MARKET_OPEN) +
            timedelta(minutes=15)
        ).time()
        if self.MARKET_OPEN <= current_time <= open_15_end:
            return TradingSession.OPEN_FIRST_15

        # 上午时段
        if open_15_end < current_time < self.MORNING_END:
            return TradingSession.MORNING_SESSION

        # 午休
        if self.MORNING_END <= current_time <= self.AFTERNOON_START:
            return TradingSession.NOON_BREAK

        # 下午时段
        close_15_start = (
            datetime.combine(datetime.today(), self.MARKET_CLOSE) -
            timedelta(minutes=15)
        ).time()
        if self.AFTERNOON_START <= current_time < close_15_start:
            return TradingSession.AFTERNOON_SESSION

        # 收盘前15分钟
        if close_15_start <= current_time < self.CLOSE_AUCTION_START:
            return TradingSession.CLOSE_LAST_15

        # 收盘集合竞价
        if self.CLOSE_AUCTION_START <= current_time <= self.CLOSE_AUCTION_END:
            return TradingSession.CLOSE_AUCTION

        # 盘后
        return TradingSession.POST_MARKET

    def get_next_trading_time(self, dt: Optional[datetime] = None) -> Optional[datetime]:
        """
        获取下一个可交易时间

        Args:
            dt: 当前时间，None表示当前时间

        Returns:
            下一个可交易时间
        """
        if dt is None:
            dt = datetime.now()

        current_time = dt.time()
        current_date = dt.date()

        # 如果在开盘前
        if current_time < self.MARKET_OPEN:
            # 如果有开盘避开时段，加上避开时间
            if self.avoid_open_minutes > 0:
                return datetime.combine(
                    current_date,
                    self.MARKET_OPEN
                ) + timedelta(minutes=self.avoid_open_minutes)
            return datetime.combine(current_date, self.MARKET_OPEN)

        # 如果在上午交易时段
        if self.MARKET_OPEN <= current_time < self.MORNING_END:
            # 检查是否在避开时段
            avoid_end = (
                datetime.combine(datetime.today(), self.MARKET_OPEN) +
                timedelta(minutes=self.avoid_open_minutes)
            ).time()
            if current_time < avoid_end:
                return datetime.combine(current_date, avoid_end)
            return dt  # 当前就是可交易时间

        # 如果在午休
        if self.MORNING_END <= current_time <= self.AFTERNOON_START:
            if self.avoid_noon_break:
                return datetime.combine(current_date, self.AFTERNOON_START)
            return dt

        # 如果在下午交易时段
        if self.AFTERNOON_START <= current_time < self.MARKET_CLOSE:
            # 检查是否在收盘避开时段
            avoid_start = (
                datetime.combine(datetime.today(), self.MARKET_CLOSE) -
                timedelta(minutes=self.avoid_close_minutes)
            ).time()
            if current_time >= avoid_start:
                return None  # 今天不再交易
            return dt  # 当前就是可交易时间

        # 如果已经收盘
        return None  # 今天不再交易

    def get_trading_window(
        self,
        dt: Optional[datetime] = None
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        获取当日剩余交易时间窗口

        Args:
            dt: 当前时间，None表示当前时间

        Returns:
            (开始时间, 结束时间)，如果今天不再交易则返回(None, None)
        """
        if dt is None:
            dt = datetime.now()

        current_time = dt.time()
        current_date = dt.date()

        # 如果已经收盘
        if current_time > self.MARKET_CLOSE:
            return None, None

        # 计算开始时间
        start_time = None

        # 如果在开盘前
        if current_time < self.MARKET_OPEN:
            if self.avoid_open_minutes > 0:
                start_time = datetime.combine(
                    current_date, self.MARKET_OPEN
                ) + timedelta(minutes=self.avoid_open_minutes)
            else:
                start_time = datetime.combine(current_date, self.MARKET_OPEN)
        # 如果在避开时段内
        elif not self.is_trading_time(dt):
            next_time = self.get_next_trading_time(dt)
            if next_time is None:
                return None, None
            start_time = next_time
        else:
            start_time = dt

        # 计算结束时间
        if self.avoid_close_minutes > 0:
            end_time = datetime.combine(
                current_date, self.MARKET_CLOSE
            ) - timedelta(minutes=self.avoid_close_minutes)
        else:
            end_time = datetime.combine(current_date, self.MARKET_CLOSE)

        # 如果开始时间已经过了结束时间
        if start_time >= end_time:
            return None, None

        return start_time, end_time

    def filter_trading_times(
        self,
        timestamps: pd.DatetimeIndex
    ) -> pd.DatetimeIndex:
        """
        过滤出可交易的时间点

        Args:
            timestamps: 时间戳列表

        Returns:
            可交易的时间戳
        """
        mask = [self.is_trading_time(ts) for ts in timestamps]
        return timestamps[mask]

    def get_config(self) -> Dict[str, any]:
        """
        获取当前配置

        Returns:
            配置字典
        """
        return {
            'avoid_open_minutes': self.avoid_open_minutes,
            'avoid_close_minutes': self.avoid_close_minutes,
            'avoid_noon_break': self.avoid_noon_break,
            'enable_auction': self.enable_auction,
            'avoid_periods': [
                (start.strftime('%H:%M'), end.strftime('%H:%M'))
                for start, end in self.avoid_periods
            ]
        }

    def set_config(
        self,
        avoid_open_minutes: Optional[int] = None,
        avoid_close_minutes: Optional[int] = None,
        avoid_noon_break: Optional[bool] = None,
        enable_auction: Optional[bool] = None
    ) -> None:
        """
        更新配置

        Args:
            avoid_open_minutes: 开盘后避免交易的分钟数
            avoid_close_minutes: 收盘前避免交易的分钟数
            avoid_noon_break: 是否避开午休时段
            enable_auction: 是否允许集合竞价交易
        """
        if avoid_open_minutes is not None:
            self.avoid_open_minutes = avoid_open_minutes
        if avoid_close_minutes is not None:
            self.avoid_close_minutes = avoid_close_minutes
        if avoid_noon_break is not None:
            self.avoid_noon_break = avoid_noon_break
        if enable_auction is not None:
            self.enable_auction = enable_auction

        # 重新计算避开时段
        self._calculate_avoid_periods()


class TradingTimeFilter:
    """
    交易时间过滤器

    用于在策略中过滤交易信号。
    """

    def __init__(self, controller: Optional[TradingTimeController] = None):
        """
        初始化过滤器

        Args:
            controller: 交易时间控制器，None则使用默认配置
        """
        self.controller = controller or TradingTimeController()

    def filter_signal(self, signal: Dict, timestamp: datetime) -> Optional[Dict]:
        """
        过滤交易信号

        Args:
            signal: 交易信号
            timestamp: 信号时间戳

        Returns:
            如果可交易返回信号，否则返回None
        """
        if self.controller.is_trading_time(timestamp):
            return signal
        return None

    def filter_signals(
        self,
        signals: List[Dict],
        timestamps: List[datetime]
    ) -> List[Dict]:
        """
        批量过滤交易信号

        Args:
            signals: 交易信号列表
            timestamps: 对应的时间戳列表

        Returns:
            过滤后的信号列表
        """
        filtered = []
        for signal, timestamp in zip(signals, timestamps):
            if self.controller.is_trading_time(timestamp):
                filtered.append(signal)
        return filtered
