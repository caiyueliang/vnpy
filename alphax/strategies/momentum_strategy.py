"""
多因子动量策略

结合多个动量因子产生交易信号：
1. 价格动量：N日收益率
2. 成交量动量：成交量变化率
3. 波动率调整动量：收益率/波动率
4. 趋势强度：ADX指标
"""

from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate


class MomentumFactor:
    """动量因子计算类"""

    @staticmethod
    def price_momentum(prices: List[float], period: int = 20) -> float:
        """
        计算价格动量（N日收益率）

        Args:
            prices: 价格列表
            period: 计算周期

        Returns:
            动量值
        """
        if len(prices) < period + 1:
            return 0.0

        current_price = prices[-1]
        past_price = prices[-(period + 1)]

        if past_price == 0:
            return 0.0

        return (current_price - past_price) / past_price

    @staticmethod
    def volume_momentum(volumes: List[float], period: int = 20) -> float:
        """
        计算成交量动量

        Args:
            volumes: 成交量列表
            period: 计算周期

        Returns:
            成交量动量值
        """
        if len(volumes) < period + 1:
            return 0.0

        current_volume = volumes[-1]
        avg_volume = sum(volumes[-(period + 1):-1]) / period

        if avg_volume == 0:
            return 0.0

        return (current_volume - avg_volume) / avg_volume

    @staticmethod
    def volatility_adjusted_momentum(
        prices: List[float],
        period: int = 20
    ) -> float:
        """
        计算波动率调整动量

        Args:
            prices: 价格列表
            period: 计算周期

        Returns:
            波动率调整动量值
        """
        if len(prices) < period + 1:
            return 0.0

        # 计算收益率
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] != 0:
                ret = (prices[i] - prices[i - 1]) / prices[i - 1]
                returns.append(ret)

        if len(returns) < period:
            return 0.0

        # 计算平均收益率和标准差
        recent_returns = returns[-period:]
        mean_return = np.mean(recent_returns)
        std_return = np.std(recent_returns)

        if std_return == 0:
            return 0.0

        # 夏普比率风格的动量
        return mean_return / std_return

    @staticmethod
    def trend_strength(prices: List[float], period: int = 14) -> float:
        """
        计算趋势强度（简化版ADX）

        Args:
            prices: 价格列表
            period: 计算周期

        Returns:
            趋势强度值 (0-100)
        """
        if len(prices) < period + 1:
            return 50.0

        # 计算价格变化的方向一致性
        directions = []
        for i in range(1, len(prices)):
            if prices[i] > prices[i - 1]:
                directions.append(1)
            elif prices[i] < prices[i - 1]:
                directions.append(-1)
            else:
                directions.append(0)

        if len(directions) < period:
            return 50.0

        recent_directions = directions[-period:]

        # 计算方向一致性
        positive_count = sum(1 for d in recent_directions if d > 0)
        negative_count = sum(1 for d in recent_directions if d < 0)

        total = positive_count + negative_count
        if total == 0:
            return 50.0

        # 归一化到0-100
        strength = abs(positive_count - negative_count) / total * 100

        return strength


class MultiFactorMomentumStrategy(StrategyTemplate):
    """
    多因子动量策略

    综合多个动量因子产生交易信号：
    - 价格动量：反映价格趋势
    - 成交量动量：确认趋势强度
    - 波动率调整动量：风险调整后收益
    - 趋势强度：过滤震荡行情

    信号生成逻辑：
    1. 计算各因子得分
    2. 加权合成综合得分
    3. 根据得分阈值产生买卖信号
    """

    # 策略参数
    lookback_period: int = 20           # 回看周期
    price_momentum_weight: float = 0.4   # 价格动量权重
    volume_momentum_weight: float = 0.2  # 成交量动量权重
    vol_adj_momentum_weight: float = 0.3 # 波动率调整动量权重
    trend_strength_weight: float = 0.1   # 趋势强度权重

    long_threshold: float = 0.3          # 做多阈值
    short_threshold: float = -0.3        # 做空阈值
    exit_threshold: float = 0.05         # 平仓阈值

    def __init__(self, backtest_engine, strategy_name, vt_symbols, setting):
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 因子计算器
        self.factor_calculator = MomentumFactor()

        # 因子历史数据
        self.factor_history: Dict[str, List[float]] = {s: [] for s in vt_symbols}

        # 综合得分
        self.composite_score: Dict[str, float] = {s: 0.0 for s in vt_symbols}

        # 信号状态
        self.signal: Dict[str, int] = {s: 0 for s in vt_symbols}

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log(
            f"策略初始化 - 回看周期:{self.lookback_period}, "
            f"做多阈值:{self.long_threshold}, 做空阈值:{self.short_threshold}"
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
            if len(self.history_bars[vt_symbol]) < self.lookback_period + 1:
                continue

            # 计算综合得分
            score = self._calculate_composite_score(vt_symbol)
            self.composite_score[vt_symbol] = score

            # 记录因子历史
            self.factor_history[vt_symbol].append(score)

            # 获取当前持仓
            pos = self.get_position(vt_symbol)

            # 生成交易信号
            self._generate_signal(vt_symbol, bar, score, pos)

    def _calculate_composite_score(self, vt_symbol: str) -> float:
        """
        计算综合动量得分

        Args:
            vt_symbol: 合约代码

        Returns:
            综合得分 (-1 到 1)
        """
        bars = self.history_bars[vt_symbol]

        # 提取价格和成交量数据
        prices = [bar.close_price for bar in bars]
        volumes = [bar.volume for bar in bars]

        # 计算各因子
        price_mom = self.factor_calculator.price_momentum(
            prices, self.lookback_period
        )
        volume_mom = self.factor_calculator.volume_momentum(
            volumes, self.lookback_period
        )
        vol_adj_mom = self.factor_calculator.volatility_adjusted_momentum(
            prices, self.lookback_period
        )
        trend_str = self.factor_calculator.trend_strength(
            prices, self.lookback_period
        )

        # 标准化因子到 -1 到 1 范围
        price_mom_norm = np.tanh(price_mom * 5)  # 缩放并限制范围
        volume_mom_norm = np.tanh(volume_mom * 2)
        vol_adj_mom_norm = np.tanh(vol_adj_mom * 2)
        trend_str_norm = (trend_str - 50) / 50  # 转换到 -1 到 1

        # 加权合成
        composite_score = (
            price_mom_norm * self.price_momentum_weight +
            volume_mom_norm * self.volume_momentum_weight +
            vol_adj_mom_norm * self.vol_adj_momentum_weight +
            trend_str_norm * self.trend_strength_weight
        )

        return composite_score

    def _generate_signal(
        self,
        vt_symbol: str,
        bar: BarData,
        score: float,
        pos: float
    ) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
            score: 综合得分
            pos: 当前持仓
        """
        # 多头信号
        if score > self.long_threshold:
            if pos <= 0:
                # 平空仓，开多仓
                if pos < 0:
                    self.cover(vt_symbol, bar.close_price, abs(pos))
                    self.write_log(f"{vt_symbol} 平空仓 @ {bar.close_price}")

                # 计算目标仓位
                target_volume = self._calculate_position_size(
                    vt_symbol, bar.close_price, score
                )

                if target_volume > 0:
                    self.buy(vt_symbol, bar.close_price, target_volume)
                    self.write_log(
                        f"{vt_symbol} 买入开仓 @ {bar.close_price}, "
                        f"数量:{target_volume}, 得分:{score:.3f}"
                    )

                self.signal[vt_symbol] = 1

        # 空头信号
        elif score < self.short_threshold:
            if pos >= 0:
                # 平多仓，开空仓
                if pos > 0:
                    self.sell(vt_symbol, bar.close_price, pos)
                    self.write_log(f"{vt_symbol} 卖出平仓 @ {bar.close_price}")

                # 计算目标仓位
                target_volume = self._calculate_position_size(
                    vt_symbol, bar.close_price, abs(score)
                )

                if target_volume > 0:
                    self.short(vt_symbol, bar.close_price, target_volume)
                    self.write_log(
                        f"{vt_symbol} 卖出开仓 @ {bar.close_price}, "
                        f"数量:{target_volume}, 得分:{score:.3f}"
                    )

                self.signal[vt_symbol] = -1

        # 平仓信号（得分回归中性区域）
        elif abs(score) < self.exit_threshold:
            if pos != 0:
                if pos > 0:
                    self.sell(vt_symbol, bar.close_price, pos)
                    self.write_log(
                        f"{vt_symbol} 卖出平仓(信号衰减) @ {bar.close_price}, "
                        f"得分:{score:.3f}"
                    )
                else:
                    self.cover(vt_symbol, bar.close_price, abs(pos))
                    self.write_log(
                        f"{vt_symbol} 买入平仓(信号衰减) @ {bar.close_price}, "
                        f"得分:{score:.3f}"
                    )

                self.signal[vt_symbol] = 0

    def _calculate_position_size(
        self,
        vt_symbol: str,
        price: float,
        signal_strength: float
    ) -> float:
        """
        计算仓位大小

        基于信号强度动态调整仓位

        Args:
            vt_symbol: 合约代码
            price: 当前价格
            signal_strength: 信号强度 (0-1)

        Returns:
            目标仓位数量
        """
        if price <= 0:
            return 0.0

        # 基础仓位（10%资金）
        base_capital = self.backtest_engine.config.initial_capital * 0.1

        # 根据信号强度调整仓位
        # 信号越强，仓位越大
        position_multiplier = min(signal_strength * 2, 1.5)  # 最大1.5倍
        adjusted_capital = base_capital * max(position_multiplier, 0.5)  # 最小0.5倍

        # 计算数量
        volume = adjusted_capital / price

        # 取整（假设股票为100股一手）
        volume = int(volume / 100) * 100

        return max(volume, 100)  # 至少100股

    def get_factor_report(self, vt_symbol: str) -> Dict:
        """
        获取因子报告

        Args:
            vt_symbol: 合约代码

        Returns:
            因子报告字典
        """
        bars = self.history_bars.get(vt_symbol, [])
        if len(bars) < self.lookback_period + 1:
            return {}

        prices = [bar.close_price for bar in bars]
        volumes = [bar.volume for bar in bars]

        return {
            "price_momentum": self.factor_calculator.price_momentum(
                prices, self.lookback_period
            ),
            "volume_momentum": self.factor_calculator.volume_momentum(
                volumes, self.lookback_period
            ),
            "volatility_adjusted_momentum": (
                self.factor_calculator.volatility_adjusted_momentum(
                    prices, self.lookback_period
                )
            ),
            "trend_strength": self.factor_calculator.trend_strength(
                prices, self.lookback_period
            ),
            "composite_score": self.composite_score.get(vt_symbol, 0.0),
            "current_signal": self.signal.get(vt_symbol, 0),
        }
