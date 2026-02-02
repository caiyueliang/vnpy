"""
策略模板

提供策略开发的基础框架
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from vnpy.trader.object import BarData, TickData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str = "Strategy"                  # 策略名称
    vt_symbols: list[str] = None            # 交易合约列表
    interval: str = "d"                     # 时间周期

    # 仓位配置
    max_position: float = 0.3               # 最大仓位
    risk_per_trade: float = 0.02            # 单笔风险

    # 信号配置
    confidence_threshold: float = 0.6       # 信号置信度阈值

    def __post_init__(self):
        if self.vt_symbols is None:
            self.vt_symbols = []


class StrategyTemplate(ABC):
    """
    策略模板基类

    所有策略必须继承此类并实现相关方法
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        self.backtest_engine = backtest_engine
        self.strategy_name = strategy_name
        self.vt_symbols = vt_symbols

        # 配置参数
        self.config = StrategyConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in StrategyConfig.__dataclass_fields__}
        )

        # 策略状态
        self.inited: bool = False
        self.trading: bool = False

        # 数据缓存
        self.bars: dict[str, BarData] = {}
        self.ticks: dict[str, TickData] = {}
        self.history_bars: dict[str, list[BarData]] = {s: [] for s in vt_symbols}

        # 持仓状态
        self.positions: dict[str, float] = {s: 0.0 for s in vt_symbols}

        # 更新配置
        self.on_init_setting(setting)

    def on_init_setting(self, setting: dict) -> None:
        """
        初始化策略参数

        Args:
            setting: 参数字典
        """
        for key, value in setting.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def on_init(self) -> None:
        """策略初始化回调"""
        self.inited = True
        self.on_strategy_init()

    def on_start(self) -> None:
        """策略启动回调"""
        self.trading = True
        self.on_strategy_start()

    def on_stop(self) -> None:
        """策略停止回调"""
        self.trading = False
        self.on_strategy_stop()

    @abstractmethod
    def on_strategy_init(self) -> None:
        """子类实现：策略初始化"""
        pass

    @abstractmethod
    def on_strategy_start(self) -> None:
        """子类实现：策略启动"""
        pass

    @abstractmethod
    def on_strategy_stop(self) -> None:
        """子类实现：策略停止"""
        pass

    @abstractmethod
    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典 {vt_symbol: BarData}
        """
        pass

    def on_ticks(self, ticks: dict[str, TickData]) -> None:
        """
        Tick数据回调

        Args:
            ticks: Tick数据字典 {vt_symbol: TickData}
        """
        self.ticks = ticks

    def on_order(self, order: OrderData) -> None:
        """
        订单回调

        Args:
            order: 订单数据
        """
        pass

    def on_trade(self, trade: TradeData) -> None:
        """
        成交回调

        Args:
            trade: 成交数据
        """
        # 更新持仓
        if trade.direction == Direction.LONG:
            self.positions[trade.vt_symbol] += trade.volume
        else:
            self.positions[trade.vt_symbol] -= trade.volume

    # ========== 交易接口 ==========

    def buy(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        买入开仓

        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量

        Returns:
            订单ID
        """
        if self.backtest_engine:
            return self.backtest_engine.buy(vt_symbol, price, volume)
        return ""

    def sell(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        卖出平仓

        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量

        Returns:
            订单ID
        """
        if self.backtest_engine:
            return self.backtest_engine.sell(vt_symbol, price, volume)
        return ""

    def short(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        卖出开仓

        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量

        Returns:
            订单ID
        """
        if self.backtest_engine:
            return self.backtest_engine.short(vt_symbol, price, volume)
        return ""

    def cover(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        买入平仓

        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量

        Returns:
            订单ID
        """
        if self.backtest_engine:
            return self.backtest_engine.cover(vt_symbol, price, volume)
        return ""

    def cancel_order(self, vt_orderid: str) -> None:
        """
        撤销订单

        Args:
            vt_orderid: 订单ID
        """
        pass

    def cancel_all(self) -> None:
        """撤销所有订单"""
        pass

    # ========== 工具方法 ==========

    def get_position(self, vt_symbol: str) -> float:
        """
        获取持仓数量

        Args:
            vt_symbol: 合约代码

        Returns:
            持仓数量
        """
        return self.positions.get(vt_symbol, 0.0)

    def get_bars(self, vt_symbol: str, n: int = 1) -> list[BarData]:
        """
        获取历史K线

        Args:
            vt_symbol: 合约代码
            n: 获取数量

        Returns:
            K线列表
        """
        bars = self.history_bars.get(vt_symbol, [])
        return bars[-n:] if len(bars) >= n else bars

    def calculate_atr(self, vt_symbol: str, period: int = 14) -> float:
        """
        计算ATR

        Args:
            vt_symbol: 合约代码
            period: 周期

        Returns:
            ATR值
        """
        bars = self.get_bars(vt_symbol, period + 1)
        if len(bars) < period + 1:
            return 0.0

        tr_values = []
        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1]

            tr1 = bar.high_price - bar.low_price
            tr2 = abs(bar.high_price - prev_bar.close_price)
            tr3 = abs(bar.low_price - prev_bar.close_price)

            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)

        return sum(tr_values) / len(tr_values) if tr_values else 0.0

    def calculate_ma(self, vt_symbol: str, period: int = 20) -> float:
        """
        计算移动平均线

        Args:
            vt_symbol: 合约代码
            period: 周期

        Returns:
            MA值
        """
        bars = self.get_bars(vt_symbol, period)
        if len(bars) < period:
            return 0.0

        closes = [bar.close_price for bar in bars]
        return sum(closes) / len(closes)

    def write_log(self, msg: str) -> None:
        """
        记录日志

        Args:
            msg: 日志消息
        """
        print(f"[{self.strategy_name}] {msg}")

    def get_current_datetime(self) -> datetime:
        """获取当前时间"""
        if self.backtest_engine:
            return self.backtest_engine.datetime
        return datetime.now()
