"""
均值回归策略

包含三种均值回归策略：
1. 统计套利策略 - 基于价格序列的均值回归
2. 配对交易策略 - 基于协整关系的配对交易
3. 波动率回归策略 - 基于波动率的均值回归
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate, StrategyConfig


@dataclass
class MeanReversionConfig(StrategyConfig):
    """均值回归策略配置"""
    # 统计套利参数
    lookback_period: int = 20                 # 回看周期
    entry_zscore: float = 2.0                 # 入场Z-Score阈值
    exit_zscore: float = 0.5                  # 出场Z-Score阈值

    # 配对交易参数
    hedge_ratio: float = 1.0                  # 对冲比例
    coint_threshold: float = 0.05             # 协整检验阈值

    # 波动率参数
    vol_lookback: int = 20                    # 波动率回看周期
    vol_percentile: float = 0.8               # 波动率分位数阈值

    # 仓位管理
    position_scale: float = 0.5               # 仓位缩放因子


class StatisticalArbitrageStrategy(StrategyTemplate):
    """
    统计套利策略

    基于价格序列的均值回归特性，当价格偏离均值达到一定程度时，
    预期价格会回归均值，从而产生交易机会。

    策略逻辑：
    1. 计算价格的移动平均（均值）
    2. 计算价格的标准差
    3. 计算Z-Score = (价格 - 均值) / 标准差
    4. 当Z-Score > 入场阈值时，做空（预期回归）
    5. 当Z-Score < -入场阈值时，做多（预期回归）
    6. 当|Z-Score| < 出场阈值时，平仓
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = MeanReversionConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in MeanReversionConfig.__dataclass_fields__}
        )

        # 策略状态
        self.zscore: float = 0.0
        self.mean_price: float = 0.0
        self.std_price: float = 0.0

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("统计套利策略初始化完成")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("统计套利策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("统计套利策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.lookback_period * 2:
                self.history_bars[vt_symbol].pop(0)

            # 计算统计指标
            self._calculate_statistics(vt_symbol)

            # 生成交易信号
            self._generate_signals(vt_symbol, bar)

    def _calculate_statistics(self, vt_symbol: str) -> None:
        """
        计算统计指标

        Args:
            vt_symbol: 合约代码
        """
        bars = self.history_bars[vt_symbol]
        if len(bars) < self.config.lookback_period:
            return

        # 获取收盘价序列
        closes = np.array([bar.close_price for bar in bars[-self.config.lookback_period:]])

        # 计算均值和标准差
        self.mean_price = np.mean(closes)
        self.std_price = np.std(closes)

        # 计算Z-Score
        if self.std_price > 0:
            current_price = bars[-1].close_price
            self.zscore = (current_price - self.mean_price) / self.std_price
        else:
            self.zscore = 0.0

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        if self.std_price == 0:
            return

        position = self.get_position(vt_symbol)

        # 入场信号
        if position == 0:
            # Z-Score过高，做空（预期回归均值）
            if self.zscore > self.config.entry_zscore:
                volume = self._calculate_position_size(vt_symbol)
                self.short(vt_symbol, bar.close_price, volume)
                self.write_log(f"做空信号: Z-Score={self.zscore:.2f}, 价格={bar.close_price}")

            # Z-Score过低，做多（预期回归均值）
            elif self.zscore < -self.config.entry_zscore:
                volume = self._calculate_position_size(vt_symbol)
                self.buy(vt_symbol, bar.close_price, volume)
                self.write_log(f"做多信号: Z-Score={self.zscore:.2f}, 价格={bar.close_price}")

        # 出场信号
        elif position > 0:  # 多头持仓
            if self.zscore > -self.config.exit_zscore:
                self.sell(vt_symbol, bar.close_price, abs(position))
                self.write_log(f"平多信号: Z-Score={self.zscore:.2f}, 价格={bar.close_price}")

        elif position < 0:  # 空头持仓
            if self.zscore < self.config.exit_zscore:
                self.cover(vt_symbol, bar.close_price, abs(position))
                self.write_log(f"平空信号: Z-Score={self.zscore:.2f}, 价格={bar.close_price}")

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """
        计算仓位大小

        Args:
            vt_symbol: 合约代码

        Returns:
            仓位大小
        """
        # 基于ATR计算仓位
        atr = self.calculate_atr(vt_symbol, 14)
        if atr == 0:
            return 100  # 默认仓位

        # 根据风险计算仓位
        risk_amount = self.config.risk_per_trade * 100000  # 假设账户10万
        position_size = risk_amount / atr * self.config.position_scale

        # 限制最大仓位
        max_position = self.config.max_position * 1000  # 假设每手1000股
        return min(position_size, max_position)


class PairsTradingStrategy(StrategyTemplate):
    """
    配对交易策略

    基于两只股票之间的协整关系进行交易。当价差偏离历史均值时，
    做多被低估的股票，做空被高估的股票，预期价差回归时获利。

    策略逻辑：
    1. 检验两只股票的协整关系
    2. 计算最优对冲比例（hedge ratio）
    3. 计算价差序列 = 股票A - hedge_ratio * 股票B
    4. 当价差 > 均值 + 入场阈值*标准差时，做空价差
    5. 当价差 < 均值 - 入场阈值*标准差时，做多价差
    6. 当价差回归均值附近时，平仓
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        if len(vt_symbols) != 2:
            raise ValueError("配对交易策略需要两个交易标的")

        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = MeanReversionConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in MeanReversionConfig.__dataclass_fields__}
        )

        # 配对股票
        self.symbol_a = vt_symbols[0]
        self.symbol_b = vt_symbols[1]

        # 协整关系
        self.hedge_ratio: float = self.config.hedge_ratio
        self.coint_pvalue: float = 1.0
        self.is_cointegrated: bool = False

        # 价差统计
        self.spread_mean: float = 0.0
        self.spread_std: float = 0.0
        self.current_spread: float = 0.0
        self.zscore: float = 0.0

        # 持仓状态
        self.spread_position: int = 0  # 1=多价差, -1=空价差, 0=无持仓

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log(f"配对交易策略初始化: {self.symbol_a} - {self.symbol_b}")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("配对交易策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("配对交易策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 确保两个标的都有数据
        if self.symbol_a not in bars or self.symbol_b not in bars:
            return

        # 更新历史数据
        self.history_bars[self.symbol_a].append(bars[self.symbol_a])
        self.history_bars[self.symbol_b].append(bars[self.symbol_b])

        if len(self.history_bars[self.symbol_a]) > self.config.lookback_period * 3:
            self.history_bars[self.symbol_a].pop(0)
        if len(self.history_bars[self.symbol_b]) > self.config.lookback_period * 3:
            self.history_bars[self.symbol_b].pop(0)

        # 检查数据量
        if len(self.history_bars[self.symbol_a]) < self.config.lookback_period:
            return

        # 计算协整关系和价差
        self._calculate_cointegration()
        self._calculate_spread()

        # 生成交易信号
        self._generate_signals(bars)

    def _calculate_cointegration(self) -> None:
        """计算协整关系"""
        prices_a = np.array([bar.close_price for bar in self.history_bars[self.symbol_a]])
        prices_b = np.array([bar.close_price for bar in self.history_bars[self.symbol_b]])

        if len(prices_a) < self.config.lookback_period or len(prices_b) < self.config.lookback_period:
            return

        # 使用最近的数据
        prices_a = prices_a[-self.config.lookback_period:]
        prices_b = prices_b[-self.config.lookback_period:]

        # 计算对冲比例（线性回归）
        slope, intercept, r_value, p_value, std_err = stats.linregress(prices_b, prices_a)
        self.hedge_ratio = slope

        # 协整检验（简化版）
        spread = prices_a - self.hedge_ratio * prices_b
        adf_result = self._adf_test(spread)
        self.coint_pvalue = adf_result
        self.is_cointegrated = adf_result < self.config.coint_threshold

    def _adf_test(self, series: np.ndarray) -> float:
        """
        ADF单位根检验（简化版）

        Args:
            series: 时间序列

        Returns:
            p-value
        """
        # 简化版ADF检验，实际使用应调用statsmodels
        diff = np.diff(series)
        lag = series[:-1] - np.mean(series)

        if np.sum(lag ** 2) == 0:
            return 1.0

        slope = np.sum(lag * diff) / np.sum(lag ** 2)
        residuals = diff - slope * lag
        std_err = np.std(residuals)

        if std_err == 0:
            return 1.0

        t_stat = slope / std_err
        # 简化的p-value估计
        p_value = 1 - stats.norm.cdf(abs(t_stat))
        return p_value

    def _calculate_spread(self) -> None:
        """计算价差"""
        price_a = self.history_bars[self.symbol_a][-1].close_price
        price_b = self.history_bars[self.symbol_b][-1].close_price

        # 计算当前价差
        self.current_spread = price_a - self.hedge_ratio * price_b

        # 计算历史价差统计
        prices_a = np.array([bar.close_price for bar in self.history_bars[self.symbol_a][-self.config.lookback_period:]])
        prices_b = np.array([bar.close_price for bar in self.history_bars[self.symbol_b][-self.config.lookback_period:]])

        spread_series = prices_a - self.hedge_ratio * prices_b
        self.spread_mean = np.mean(spread_series)
        self.spread_std = np.std(spread_series)

        # 计算Z-Score
        if self.spread_std > 0:
            self.zscore = (self.current_spread - self.spread_mean) / self.spread_std
        else:
            self.zscore = 0.0

    def _generate_signals(self, bars: dict[str, BarData]) -> None:
        """
        生成交易信号

        Args:
            bars: K线数据字典
        """
        if not self.is_cointegrated:
            return

        bar_a = bars[self.symbol_a]
        bar_b = bars[self.symbol_b]

        position_a = self.get_position(self.symbol_a)
        position_b = self.get_position(self.symbol_b)

        # 计算仓位
        volume = self._calculate_position_size()
        volume_b = volume * self.hedge_ratio

        # 入场信号
        if position_a == 0 and position_b == 0:
            # 价差过高，做空价差（做空A，做多B）
            if self.zscore > self.config.entry_zscore:
                self.short(self.symbol_a, bar_a.close_price, volume)
                self.buy(self.symbol_b, bar_b.close_price, volume_b)
                self.spread_position = -1
                self.write_log(f"做空价差: Z={self.zscore:.2f}, 价差={self.current_spread:.2f}")

            # 价差过低，做多价差（做多A，做空B）
            elif self.zscore < -self.config.entry_zscore:
                self.buy(self.symbol_a, bar_a.close_price, volume)
                self.short(self.symbol_b, bar_b.close_price, volume_b)
                self.spread_position = 1
                self.write_log(f"做多价差: Z={self.zscore:.2f}, 价差={self.current_spread:.2f}")

        # 出场信号
        elif abs(self.zscore) < self.config.exit_zscore:
            if position_a > 0:
                self.sell(self.symbol_a, bar_a.close_price, position_a)
            elif position_a < 0:
                self.cover(self.symbol_a, bar_a.close_price, abs(position_a))

            if position_b > 0:
                self.sell(self.symbol_b, bar_b.close_price, position_b)
            elif position_b < 0:
                self.cover(self.symbol_b, bar_b.close_price, abs(position_b))

            self.spread_position = 0
            self.write_log(f"平仓: Z={self.zscore:.2f}")

    def _calculate_position_size(self) -> float:
        """
        计算仓位大小

        Returns:
            仓位大小
        """
        # 简化版仓位计算
        return 100 * self.config.position_scale


class VolatilityMeanReversionStrategy(StrategyTemplate):
    """
    波动率回归策略

    基于波动率的均值回归特性。当波动率异常升高时，预期波动率会回归正常水平，
    可以通过期权或波动率衍生品进行交易。

    在股票策略中，可以利用波动率与价格的关系：
    - 高波动率往往伴随着价格过度反应，之后可能回归
    - 低波动率可能预示着即将发生大的价格变动

    策略逻辑：
    1. 计算历史波动率（如20日 realized volatility）
    2. 计算波动率的分位数或Z-Score
    3. 当波动率处于高位时，预期价格震荡收敛，适合区间交易
    4. 当波动率处于低位时，预期价格即将突破，适合趋势跟踪
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = MeanReversionConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in MeanReversionConfig.__dataclass_fields__}
        )

        # 波动率状态
        self.current_vol: float = 0.0
        self.vol_percentile: float = 0.5
        self.vol_zscore: float = 0.0
        self.vol_mean: float = 0.0
        self.vol_std: float = 0.0

        # 价格状态
        self.price_trend: float = 0.0

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("波动率回归策略初始化完成")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("波动率回归策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("波动率回归策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.vol_lookback * 3:
                self.history_bars[vt_symbol].pop(0)

            # 计算波动率指标
            self._calculate_volatility(vt_symbol)

            # 生成交易信号
            self._generate_signals(vt_symbol, bar)

    def _calculate_volatility(self, vt_symbol: str) -> None:
        """
        计算波动率指标

        Args:
            vt_symbol: 合约代码
        """
        bars = self.history_bars[vt_symbol]
        if len(bars) < self.config.vol_lookback + 1:
            return

        # 计算收益率序列
        returns = []
        for i in range(1, len(bars)):
            ret = (bars[i].close_price - bars[i-1].close_price) / bars[i-1].close_price
            returns.append(ret)

        returns = np.array(returns)

        # 计算当前波动率（年化）
        if len(returns) >= self.config.vol_lookback:
            recent_returns = returns[-self.config.vol_lookback:]
            self.current_vol = np.std(recent_returns) * np.sqrt(252)

            # 计算历史波动率统计
            if len(returns) >= self.config.vol_lookback * 2:
                hist_vols = []
                for i in range(self.config.vol_lookback, len(returns)):
                    vol = np.std(returns[i-self.config.vol_lookback:i]) * np.sqrt(252)
                    hist_vols.append(vol)

                hist_vols = np.array(hist_vols)
                self.vol_mean = np.mean(hist_vols)
                self.vol_std = np.std(hist_vols)

                # 计算波动率Z-Score
                if self.vol_std > 0:
                    self.vol_zscore = (self.current_vol - self.vol_mean) / self.vol_std
                else:
                    self.vol_zscore = 0.0

                # 计算波动率分位数
                self.vol_percentile = np.sum(hist_vols < self.current_vol) / len(hist_vols)

        # 计算价格趋势
        if len(bars) >= 20:
            closes = [b.close_price for b in bars[-20:]]
            self.price_trend = (closes[-1] - closes[0]) / closes[0]

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        if self.vol_mean == 0:
            return

        position = self.get_position(vt_symbol)

        # 高波动率状态 - 预期均值回归，进行反向交易
        if self.vol_percentile > self.config.vol_percentile:
            if position == 0:
                # 价格上涨伴随高波动，做空
                if self.price_trend > 0.02:  # 2%涨幅
                    volume = self._calculate_position_size(vt_symbol)
                    self.short(vt_symbol, bar.close_price, volume)
                    self.write_log(f"高波动做空: 波动率={self.current_vol:.2%}, 趋势={self.price_trend:.2%}")

                # 价格下跌伴随高波动，做多
                elif self.price_trend < -0.02:
                    volume = self._calculate_position_size(vt_symbol)
                    self.buy(vt_symbol, bar.close_price, volume)
                    self.write_log(f"高波动做多: 波动率={self.current_vol:.2%}, 趋势={self.price_trend:.2%}")

            # 波动率回归正常，平仓
            elif self.vol_percentile < 0.6:
                if position > 0:
                    self.sell(vt_symbol, bar.close_price, position)
                elif position < 0:
                    self.cover(vt_symbol, bar.close_price, abs(position))
                self.write_log(f"波动率回归平仓: 波动率={self.current_vol:.2%}")

        # 低波动率状态 - 预期突破，可以小仓位试多或观望
        elif self.vol_percentile < 0.2:
            # 低波动率时减少交易，等待突破信号
            pass

        # 正常波动率状态，按趋势交易
        else:
            # 如果有持仓，检查是否需要平仓
            if position != 0:
                # 简单止盈止损
                entry_bars = [b for b in self.history_bars[vt_symbol] if b.datetime <= bar.datetime]
                if len(entry_bars) > 5:  # 持仓超过5根K线
                    if position > 0 and self.price_trend < 0:
                        self.sell(vt_symbol, bar.close_price, position)
                    elif position < 0 and self.price_trend > 0:
                        self.cover(vt_symbol, bar.close_price, abs(position))

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """
        计算仓位大小

        Args:
            vt_symbol: 合约代码

        Returns:
            仓位大小
        """
        # 根据波动率调整仓位
        if self.current_vol > 0:
            # 波动率越高，仓位越小
            vol_adjustment = 0.2 / max(self.current_vol, 0.2)
        else:
            vol_adjustment = 1.0

        base_size = 100
        return base_size * vol_adjustment * self.config.position_scale
