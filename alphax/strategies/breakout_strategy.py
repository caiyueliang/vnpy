"""
突破策略

基于价格突破关键水平位产生交易信号：
1. 通道突破：突破N日高低点
2. 波动率突破：基于ATR的突破
3. 成交量确认突破：放量突破
4. 假突破过滤：避免震荡行情中的假信号
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate


class BreakoutType(Enum):
    """突破类型"""
    CHANNEL = "channel"           # 通道突破
    VOLATILITY = "volatility"     # 波动率突破
    VOLUME = "volume"             # 成交量突破


class BreakoutFilter:
    """突破过滤器"""

    @staticmethod
    def is_valid_channel_breakout(
        bars: List[BarData],
        current_price: float,
        lookback: int,
        breakout_direction: int
    ) -> bool:
        """
        验证是否为有效通道突破

        Args:
            bars: K线数据列表
            current_price: 当前价格
            lookback: 回看周期
            breakout_direction: 突破方向 (1=向上突破, -1=向下突破)

        Returns:
            是否有效突破
        """
        if len(bars) < lookback:
            return False

        recent_bars = bars[-lookback:]

        if breakout_direction == 1:
            # 向上突破
            highest_high = max(b.high_price for b in recent_bars)
            return current_price > highest_high
        else:
            # 向下突破
            lowest_low = min(b.low_price for b in recent_bars)
            return current_price < lowest_low

    @staticmethod
    def is_volume_confirmed(
        bars: List[BarData],
        volume_threshold: float = 1.5
    ) -> bool:
        """
        检查成交量是否确认突破

        Args:
            bars: K线数据列表
            volume_threshold: 成交量阈值（相对于平均成交量的倍数）

        Returns:
            是否成交量确认
        """
        if len(bars) < 2:
            return False

        current_volume = bars[-1].volume
        avg_volume = sum(b.volume for b in bars[:-1]) / (len(bars) - 1)

        if avg_volume == 0:
            return False

        return current_volume >= avg_volume * volume_threshold

    @staticmethod
    def is_trend_aligned(
        bars: List[BarData],
        breakout_direction: int,
        trend_period: int = 20
    ) -> bool:
        """
        检查突破是否与趋势方向一致

        Args:
            bars: K线数据列表
            breakout_direction: 突破方向
            trend_period: 趋势周期

        Returns:
            是否与趋势一致
        """
        if len(bars) < trend_period:
            return True  # 数据不足，默认可交易

        # 计算简单移动平均线
        recent_bars = bars[-trend_period:]
        sma = sum(b.close_price for b in recent_bars) / trend_period

        current_price = bars[-1].close_price

        if breakout_direction == 1:
            # 向上突破应该发生在价格高于均线时
            return current_price > sma
        else:
            # 向下突破应该发生在价格低于均线时
            return current_price < sma

    @staticmethod
    def is_not_whipsaw(
        bars: List[BarData],
        lookback: int = 5
    ) -> bool:
        """
        检查是否为假突破（whipsaw）

        Args:
            bars: K线数据列表
            lookback: 回看周期

        Returns:
            是否不是假突破
        """
        if len(bars) < lookback + 1:
            return True

        # 检查近期是否有频繁的突破和反转
        recent_bars = bars[-(lookback + 1):-1]
        price_range = max(b.high_price for b in recent_bars) - min(b.low_price for b in recent_bars)

        if price_range == 0:
            return True

        # 计算近期波动率
        avg_range = sum(b.high_price - b.low_price for b in recent_bars) / len(recent_bars)

        # 如果波动率过大，可能是震荡行情
        return avg_range <= price_range * 0.5


class BreakoutStrategy(StrategyTemplate):
    """
    突破策略

    基于价格突破产生交易信号，包含多种突破类型：
    - 通道突破：突破N日高低点
    - 波动率突破：基于ATR的动态通道
    - 成交量确认：放量突破增加可靠性

    风险控制：
    - 假突破过滤
    - 趋势一致性检查
    - 动态止损
    """

    # 策略参数
    breakout_type: str = "channel"      # 突破类型: channel/volatility/volume
    channel_period: int = 20            # 通道周期
    atr_period: int = 14                # ATR周期
    atr_multiplier: float = 2.0         # ATR倍数

    # 过滤参数
    use_volume_filter: bool = True      # 使用成交量过滤
    volume_threshold: float = 1.5       # 成交量阈值
    use_trend_filter: bool = True       # 使用趋势过滤
    trend_period: int = 20              # 趋势周期
    use_whipsaw_filter: bool = True     # 使用假突破过滤

    # 入场参数
    breakout_threshold: float = 0.001   # 突破阈值（价格需要突破多少比例）

    # 出场参数
    use_trailing_stop: bool = True      # 使用移动止损
    trailing_stop_atr_mult: float = 3.0 # 移动止损ATR倍数

    def __init__(self, backtest_engine, strategy_name, vt_symbols, setting):
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 过滤器
        self.breakout_filter = BreakoutFilter()

        # 通道数据
        self.channel_high: Dict[str, float] = {s: 0.0 for s in vt_symbols}
        self.channel_low: Dict[str, float] = {s: 0.0 for s in vt_symbols}

        # ATR数据
        self.atr_values: Dict[str, float] = {s: 0.0 for s in vt_symbols}

        # 入场价格（用于计算移动止损）
        self.entry_price: Dict[str, float] = {s: 0.0 for s in vt_symbols}
        self.highest_since_entry: Dict[str, float] = {s: 0.0 for s in vt_symbols}
        self.lowest_since_entry: Dict[str, float] = {s: float('inf') for s in vt_symbols}

        # 信号状态
        self.signal: Dict[str, int] = {s: 0 for s in vt_symbols}

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log(
            f"策略初始化 - 突破类型:{self.breakout_type}, "
            f"通道周期:{self.channel_period}"
        )

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)

            # 检查数据是否足够
            min_period = max(self.channel_period, self.atr_period, self.trend_period)
            if len(self.history_bars[vt_symbol]) < min_period:
                continue

            # 更新技术指标
            self._update_indicators(vt_symbol)

            # 获取当前持仓
            pos = self.get_position(vt_symbol)

            # 检查止损
            if pos != 0 and self.use_trailing_stop:
                if self._check_trailing_stop(vt_symbol, bar, pos):
                    continue

            # 生成交易信号
            if pos == 0:
                self._check_entry_signals(vt_symbol, bar)

    def _update_indicators(self, vt_symbol: str) -> None:
        """
        更新技术指标

        Args:
            vt_symbol: 合约代码
        """
        bars = self.history_bars[vt_symbol]

        # 更新通道
        recent_bars = bars[-self.channel_period:]
        self.channel_high[vt_symbol] = max(b.high_price for b in recent_bars)
        self.channel_low[vt_symbol] = min(b.low_price for b in recent_bars)

        # 更新ATR
        self.atr_values[vt_symbol] = self.calculate_atr(vt_symbol, self.atr_period)

    def _check_entry_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        检查入场信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        bars = self.history_bars[vt_symbol]

        # 向上突破检查
        upper_level = self._get_upper_level(vt_symbol)
        breakout_up = bar.close_price > upper_level * (1 + self.breakout_threshold)

        # 向下突破检查
        lower_level = self._get_lower_level(vt_symbol)
        breakout_down = bar.close_price < lower_level * (1 - self.breakout_threshold)

        # 应用过滤器
        if breakout_up:
            if self._apply_filters(bars, bar.close_price, 1):
                self._enter_long(vt_symbol, bar)

        elif breakout_down:
            if self._apply_filters(bars, bar.close_price, -1):
                self._enter_short(vt_symbol, bar)

    def _get_upper_level(self, vt_symbol: str) -> float:
        """获取上边界"""
        if self.breakout_type == "volatility":
            atr = self.atr_values.get(vt_symbol, 0)
            return self.channel_high[vt_symbol] + atr * self.atr_multiplier
        return self.channel_high[vt_symbol]

    def _get_lower_level(self, vt_symbol: str) -> float:
        """获取下边界"""
        if self.breakout_type == "volatility":
            atr = self.atr_values.get(vt_symbol, 0)
            return self.channel_low[vt_symbol] - atr * self.atr_multiplier
        return self.channel_low[vt_symbol]

    def _apply_filters(
        self,
        bars: List[BarData],
        current_price: float,
        direction: int
    ) -> bool:
        """
        应用过滤器

        Args:
            bars: K线数据
            current_price: 当前价格
            direction: 方向 (1=多, -1=空)

        Returns:
            是否通过过滤
        """
        # 通道突破验证
        if not self.breakout_filter.is_valid_channel_breakout(
            bars, current_price, self.channel_period, direction
        ):
            return False

        # 成交量过滤
        if self.use_volume_filter:
            if not self.breakout_filter.is_volume_confirmed(bars, self.volume_threshold):
                return False

        # 趋势过滤
        if self.use_trend_filter:
            if not self.breakout_filter.is_trend_aligned(bars, direction, self.trend_period):
                return False

        # 假突破过滤
        if self.use_whipsaw_filter:
            if not self.breakout_filter.is_not_whipsaw(bars):
                return False

        return True

    def _enter_long(self, vt_symbol: str, bar: BarData) -> None:
        """开多仓"""
        target_volume = self._calculate_position_size(vt_symbol, bar.close_price)

        if target_volume > 0:
            self.buy(vt_symbol, bar.close_price, target_volume)
            self.write_log(
                f"{vt_symbol} 突破做多 @ {bar.close_price}, "
                f"数量:{target_volume}, 上轨:{self.channel_high[vt_symbol]:.2f}"
            )

            # 记录入场信息
            self.entry_price[vt_symbol] = bar.close_price
            self.highest_since_entry[vt_symbol] = bar.close_price
            self.signal[vt_symbol] = 1

    def _enter_short(self, vt_symbol: str, bar: BarData) -> None:
        """开空仓"""
        target_volume = self._calculate_position_size(vt_symbol, bar.close_price)

        if target_volume > 0:
            self.short(vt_symbol, bar.close_price, target_volume)
            self.write_log(
                f"{vt_symbol} 突破做空 @ {bar.close_price}, "
                f"数量:{target_volume}, 下轨:{self.channel_low[vt_symbol]:.2f}"
            )

            # 记录入场信息
            self.entry_price[vt_symbol] = bar.close_price
            self.lowest_since_entry[vt_symbol] = bar.close_price
            self.signal[vt_symbol] = -1

    def _check_trailing_stop(
        self,
        vt_symbol: str,
        bar: BarData,
        pos: float
    ) -> bool:
        """
        检查移动止损

        Args:
            vt_symbol: 合约代码
            bar: K线数据
            pos: 持仓

        Returns:
            是否触发止损
        """
        atr = self.atr_values.get(vt_symbol, 0)
        if atr == 0:
            return False

        if pos > 0:
            # 多头移动止损
            self.highest_since_entry[vt_symbol] = max(
                self.highest_since_entry[vt_symbol],
                bar.high_price
            )

            stop_price = self.highest_since_entry[vt_symbol] - atr * self.trailing_stop_atr_mult

            if bar.close_price < stop_price:
                self.sell(vt_symbol, bar.close_price, pos)
                self.write_log(
                    f"{vt_symbol} 移动止损平仓 @ {bar.close_price}, "
                    f"最高价:{self.highest_since_entry[vt_symbol]:.2f}, "
                    f"止损价:{stop_price:.2f}"
                )
                self.signal[vt_symbol] = 0
                return True

        elif pos < 0:
            # 空头移动止损
            self.lowest_since_entry[vt_symbol] = min(
                self.lowest_since_entry[vt_symbol],
                bar.low_price
            )

            stop_price = self.lowest_since_entry[vt_symbol] + atr * self.trailing_stop_atr_mult

            if bar.close_price > stop_price:
                self.cover(vt_symbol, bar.close_price, abs(pos))
                self.write_log(
                    f"{vt_symbol} 移动止损平仓 @ {bar.close_price}, "
                    f"最低价:{self.lowest_since_entry[vt_symbol]:.2f}, "
                    f"止损价:{stop_price:.2f}"
                )
                self.signal[vt_symbol] = 0
                return True

        return False

    def _calculate_position_size(self, vt_symbol: str, price: float) -> float:
        """
        计算仓位大小

        Args:
            vt_symbol: 合约代码
            price: 当前价格

        Returns:
            目标仓位数量
        """
        if price <= 0:
            return 0.0

        # 基于ATR计算仓位（风险平价）
        atr = self.atr_values.get(vt_symbol, price * 0.02)  # 默认2%波动
        risk_per_share = atr * self.trailing_stop_atr_mult

        if risk_per_share <= 0:
            return 0.0

        # 单笔交易风险金额（2%资金）
        risk_amount = self.backtest_engine.config.initial_capital * 0.02

        # 计算股数
        volume = risk_amount / risk_per_share

        # 取整
        volume = int(volume / 100) * 100

        return max(volume, 100)

    def get_breakout_info(self, vt_symbol: str) -> Dict:
        """
        获取突破信息

        Args:
            vt_symbol: 合约代码

        Returns:
            突破信息字典
        """
        return {
            "channel_high": self.channel_high.get(vt_symbol, 0.0),
            "channel_low": self.channel_low.get(vt_symbol, 0.0),
            "atr": self.atr_values.get(vt_symbol, 0.0),
            "upper_level": self._get_upper_level(vt_symbol),
            "lower_level": self._get_lower_level(vt_symbol),
            "entry_price": self.entry_price.get(vt_symbol, 0.0),
            "highest_since_entry": self.highest_since_entry.get(vt_symbol, 0.0),
            "lowest_since_entry": self.lowest_since_entry.get(vt_symbol, float('inf')),
            "current_signal": self.signal.get(vt_symbol, 0),
        }
