"""
组合策略

实现多种资产配置和组合管理策略：
1. 风险平价策略 - 基于风险贡献度进行资产配置
2. 因子轮动策略 - 基于因子表现进行动态调仓
3. 智能资产配置策略 - 基于市场状态的动态配置
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate, StrategyConfig


@dataclass
class PortfolioConfig(StrategyConfig):
    """组合策略配置"""
    # 再平衡参数
    rebalance_period: int = 20           # 再平衡周期（交易日）
    rebalance_threshold: float = 0.05    # 再平衡阈值（权重偏离）

    # 风险平价参数
    risk_lookback: int = 60              # 风险计算回看周期
    target_volatility: float = 0.15      # 目标波动率（年化15%）

    # 因子轮动参数
    factor_lookback: int = 20            # 因子表现回看周期
    top_n_factors: int = 3               # 选择前N个因子

    # 资产配置参数
    max_asset_weight: float = 0.40       # 单资产最大权重
    min_asset_weight: float = 0.05       # 单资产最小权重


class RiskParityStrategy(StrategyTemplate):
    """
    风险平价策略

    基于风险贡献度进行资产配置，使每个资产对组合总风险的贡献相等。
    这样可以避免单一资产的风险过度集中，实现真正的风险分散。

    策略逻辑：
    1. 计算各资产的历史波动率（风险）
    2. 计算风险平价权重：w_i ∝ 1/σ_i
    3. 定期再平衡以维持风险平价
    4. 根据目标波动率调整整体杠杆

    参考：Edward Qian, "Risk Parity Portfolios"
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
        self.config = PortfolioConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in PortfolioConfig.__dataclass_fields__}
        )

        # 目标权重
        self.target_weights: dict[str, float] = {}
        self.current_weights: dict[str, float] = {}

        # 再平衡计数
        self.days_since_rebalance: int = 0

        # 收益率历史
        self.returns_history: dict[str, list[float]] = {s: [] for s in vt_symbols}

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("风险平价策略初始化完成")

        # 初始化等权重
        n = len(self.vt_symbols)
        for vt_symbol in self.vt_symbols:
            self.target_weights[vt_symbol] = 1.0 / n
            self.current_weights[vt_symbol] = 0.0

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("风险平价策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("风险平价策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 更新历史数据
        for vt_symbol, bar in bars.items():
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.risk_lookback + 1:
                self.history_bars[vt_symbol].pop(0)

            # 计算日收益率
            if len(self.history_bars[vt_symbol]) >= 2:
                prev_close = self.history_bars[vt_symbol][-2].close_price
                curr_close = bar.close_price
                daily_return = (curr_close - prev_close) / prev_close
                self.returns_history[vt_symbol].append(daily_return)

                if len(self.returns_history[vt_symbol]) > self.config.risk_lookback:
                    self.returns_history[vt_symbol].pop(0)

        # 检查是否需要再平衡
        self.days_since_rebalance += 1

        if self.days_since_rebalance >= self.config.rebalance_period:
            if len(self.history_bars[self.vt_symbols[0]]) >= self.config.risk_lookback:
                self._calculate_risk_parity_weights()
                self._rebalance_portfolio(bars)
                self.days_since_rebalance = 0

    def _calculate_risk_parity_weights(self) -> None:
        """计算风险平价权重"""
        # 计算各资产的波动率
        volatilities = {}
        for vt_symbol in self.vt_symbols:
            returns = self.returns_history.get(vt_symbol, [])
            if len(returns) >= 20:
                vol = np.std(returns) * np.sqrt(252)  # 年化波动率
                volatilities[vt_symbol] = max(vol, 0.001)  # 防止除零
            else:
                volatilities[vt_symbol] = 0.20  # 默认波动率

        # 计算风险平价权重：w_i ∝ 1/σ_i
        inv_vols = {s: 1.0 / v for s, v in volatilities.items()}
        total_inv_vol = sum(inv_vols.values())

        for vt_symbol in self.vt_symbols:
            self.target_weights[vt_symbol] = inv_vols[vt_symbol] / total_inv_vol

        # 根据目标波动率调整杠杆
        portfolio_vol = self._calculate_portfolio_volatility()
        if portfolio_vol > 0:
            leverage = self.config.target_volatility / portfolio_vol
            leverage = min(leverage, 1.5)  # 最大1.5倍杠杆
            for vt_symbol in self.vt_symbols:
                self.target_weights[vt_symbol] *= leverage

        self.write_log(f"风险平价权重计算完成: {self.target_weights}")

    def _calculate_portfolio_volatility(self) -> float:
        """计算组合波动率"""
        returns_matrix = []
        for vt_symbol in self.vt_symbols:
            returns = self.returns_history.get(vt_symbol, [])
            if len(returns) >= 20:
                returns_matrix.append(returns[-20:])

        if not returns_matrix:
            return 0.15

        # 确保长度一致
        min_len = min(len(r) for r in returns_matrix)
        returns_matrix = np.array([r[-min_len:] for r in returns_matrix])

        # 计算协方差矩阵
        cov_matrix = np.cov(returns_matrix)

        # 计算组合波动率
        weights = np.array([self.target_weights.get(s, 0) for s in self.vt_symbols])
        portfolio_var = np.dot(weights.T, np.dot(cov_matrix, weights))
        portfolio_vol = np.sqrt(portfolio_var) * np.sqrt(252)

        return portfolio_vol

    def _rebalance_portfolio(self, bars: dict[str, BarData]) -> None:
        """
        再平衡组合

        Args:
            bars: K线数据字典
        """
        total_value = self._get_total_portfolio_value(bars)

        for vt_symbol in self.vt_symbols:
            if vt_symbol not in bars:
                continue

            bar = bars[vt_symbol]
            current_position = self.get_position(vt_symbol)
            current_value = current_position * bar.close_price
            current_weight = current_value / total_value if total_value > 0 else 0

            target_weight = self.target_weights.get(vt_symbol, 0)
            target_value = total_value * target_weight

            # 计算需要调整的仓位
            delta_value = target_value - current_value
            delta_position = delta_value / bar.close_price if bar.close_price > 0 else 0

            # 执行交易
            if abs(delta_position) > 1:  # 最小交易单位
                if delta_position > 0:
                    self.buy(vt_symbol, bar.close_price, delta_position)
                else:
                    self.sell(vt_symbol, bar.close_price, abs(delta_position))

                self.write_log(f"再平衡: {vt_symbol}, 当前权重{current_weight:.2%}, 目标权重{target_weight:.2%}")

            self.current_weights[vt_symbol] = target_weight

    def _get_total_portfolio_value(self, bars: dict[str, BarData]) -> float:
        """获取组合总价值"""
        total = 0.0
        for vt_symbol in self.vt_symbols:
            position = self.get_position(vt_symbol)
            if vt_symbol in bars:
                total += position * bars[vt_symbol].close_price
        return max(total, 100000)  # 默认10万初始资金


class FactorRotationStrategy(StrategyTemplate):
    """
    因子轮动策略

    基于因子表现进行动态调仓，选择近期表现最好的因子对应的股票进行配置。

    策略逻辑：
    1. 计算各因子的近期表现（IC、收益率等）
    2. 选择表现最好的N个因子
    3. 根据因子得分选择股票
    4. 定期轮动调整持仓

    支持的因子：
    - 价值因子：PE、PB、PS等
    - 成长因子：营收增长率、净利润增长率等
    - 质量因子：ROE、毛利率等
    - 动量因子：价格动量、收益动量等
    - 波动率因子：历史波动率、Beta等
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
        self.config = PortfolioConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in PortfolioConfig.__dataclass_fields__}
        )

        # 因子定义
        self.factors = {
            "momentum": self._calculate_momentum_score,
            "value": self._calculate_value_score,
            "quality": self._calculate_quality_score,
            "low_volatility": self._calculate_low_volatility_score,
        }

        # 因子表现历史
        self.factor_performance: dict[str, list[float]] = {f: [] for f in self.factors}

        # 当前持仓
        self.holdings: list[str] = []
        self.days_since_rotation: int = 0

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("因子轮动策略初始化完成")
        self.write_log(f"可用因子: {list(self.factors.keys())}")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("因子轮动策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("因子轮动策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 更新历史数据
        for vt_symbol, bar in bars.items():
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.factor_lookback * 3:
                self.history_bars[vt_symbol].pop(0)

        # 检查是否需要轮动
        self.days_since_rotation += 1

        if self.days_since_rotation >= self.config.rebalance_period:
            if len(self.history_bars[self.vt_symbols[0]]) >= self.config.factor_lookback:
                self._update_factor_performance()
                self._rotate_portfolio(bars)
                self.days_since_rotation = 0

    def _update_factor_performance(self) -> None:
        """更新因子表现"""
        for factor_name, factor_func in self.factors.items():
            # 计算因子得分
            scores = {}
            for vt_symbol in self.vt_symbols:
                score = factor_func(vt_symbol)
                if score is not None:
                    scores[vt_symbol] = score

            if not scores:
                continue

            # 计算因子IC（简化版：因子得分与未来收益的相关性）
            # 实际应用中应该使用更复杂的IC计算
            ic = np.mean(list(scores.values()))
            self.factor_performance[factor_name].append(ic)

            if len(self.factor_performance[factor_name]) > self.config.factor_lookback:
                self.factor_performance[factor_name].pop(0)

    def _rotate_portfolio(self, bars: dict[str, BarData]) -> None:
        """
        轮动组合

        Args:
            bars: K线数据字典
        """
        # 选择表现最好的因子
        factor_returns = {}
        for factor_name, performance in self.factor_performance.items():
            if len(performance) >= 5:
                factor_returns[factor_name] = np.mean(performance[-5:])
            else:
                factor_returns[factor_name] = 0

        # 排序并选择前N个因子
        sorted_factors = sorted(factor_returns.items(), key=lambda x: x[1], reverse=True)
        top_factors = [f[0] for f in sorted_factors[:self.config.top_n_factors]]

        self.write_log(f"选择因子: {top_factors}")

        # 根据因子得分选择股票
        stock_scores = {}
        for vt_symbol in self.vt_symbols:
            total_score = 0
            for factor_name in top_factors:
                score = self.factors[factor_name](vt_symbol)
                if score is not None:
                    total_score += score

            if total_score > 0:
                stock_scores[vt_symbol] = total_score

        # 选择得分最高的股票
        sorted_stocks = sorted(stock_scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = [s[0] for s in sorted_stocks[:5]]  # 选择前5只股票

        self.write_log(f"选择股票: {top_stocks}")

        # 调整持仓
        self._adjust_holdings(top_stocks, bars)

    def _adjust_holdings(self, target_stocks: list[str], bars: dict[str, BarData]) -> None:
        """
        调整持仓

        Args:
            target_stocks: 目标持仓股票
            bars: K线数据字典
        """
        # 卖出不在目标列表中的股票
        for vt_symbol in self.holdings:
            if vt_symbol not in target_stocks:
                position = self.get_position(vt_symbol)
                if position > 0 and vt_symbol in bars:
                    self.sell(vt_symbol, bars[vt_symbol].close_price, position)
                    self.write_log(f"卖出: {vt_symbol}")

        # 买入目标股票
        position_per_stock = 100  # 每只股票仓位
        for vt_symbol in target_stocks:
            if vt_symbol in bars:
                current_position = self.get_position(vt_symbol)
                if current_position < position_per_stock:
                    self.buy(vt_symbol, bars[vt_symbol].close_price, position_per_stock - current_position)
                    self.write_log(f"买入: {vt_symbol}")

        self.holdings = target_stocks

    def _calculate_momentum_score(self, vt_symbol: str) -> float | None:
        """计算动量因子得分"""
        bars = self.history_bars.get(vt_symbol, [])
        if len(bars) < 20:
            return None

        # 计算20日收益率
        returns = (bars[-1].close_price - bars[-20].close_price) / bars[-20].close_price
        return returns

    def _calculate_value_score(self, vt_symbol: str) -> float | None:
        """计算价值因子得分（简化版，实际需要财务数据）"""
        # 这里简化处理，实际应该使用PE、PB等估值指标
        bars = self.history_bars.get(vt_symbol, [])
        if len(bars) < 60:
            return None

        # 使用价格位置作为价值代理（价格越低，价值越高）
        high_60d = max(b.high_price for b in bars[-60:])
        low_60d = min(b.low_price for b in bars[-60:])
        current = bars[-1].close_price

        if high_60d > low_60d:
            price_position = (current - low_60d) / (high_60d - low_60d)
            return 1 - price_position  # 价格越低，得分越高
        return None

    def _calculate_quality_score(self, vt_symbol: str) -> float | None:
        """计算质量因子得分（简化版）"""
        bars = self.history_bars.get(vt_symbol, [])
        if len(bars) < 20:
            return None

        # 使用收益稳定性作为质量代理
        returns = []
        for i in range(1, len(bars)):
            ret = (bars[i].close_price - bars[i-1].close_price) / bars[i-1].close_price
            returns.append(ret)

        if len(returns) >= 10:
            sharpe = np.mean(returns) / (np.std(returns) + 1e-6)
            return sharpe
        return None

    def _calculate_low_volatility_score(self, vt_symbol: str) -> float | None:
        """计算低波动因子得分"""
        bars = self.history_bars.get(vt_symbol, [])
        if len(bars) < 20:
            return None

        # 计算20日波动率
        returns = []
        for i in range(1, min(21, len(bars))):
            ret = (bars[-i].close_price - bars[-i-1].close_price) / bars[-i-1].close_price
            returns.append(ret)

        volatility = np.std(returns) if returns else 0.01
        return 1.0 / (volatility + 0.01)  # 波动率越低，得分越高


class SmartAssetAllocationStrategy(StrategyTemplate):
    """
    智能资产配置策略

    基于市场状态进行动态资产配置，根据宏观经济指标、市场情绪等因素
    调整股票、债券、现金等资产的配置比例。

    策略逻辑：
    1. 识别当前市场状态（牛市/熊市/震荡市）
    2. 根据市场状态调整资产配置
    3. 牛市增配股票，熊市增配债券/现金
    4. 定期评估和调整

    市场状态判断：
    - 趋势指标：均线排列、价格位置
    - 波动率指标：VIX、历史波动率
    - 情绪指标：成交量、资金流向
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
        self.config = PortfolioConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in PortfolioConfig.__dataclass_fields__}
        )

        # 资产配置比例
        self.asset_allocation = {
            "stocks": 0.60,      # 股票
            "bonds": 0.30,       # 债券
            "cash": 0.10,        # 现金
        }

        # 市场状态
        self.market_state: str = "neutral"  # bull/bear/neutral
        self.market_state_score: float = 0.0

        # 再平衡计数
        self.days_since_rebalance: int = 0

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("智能资产配置策略初始化完成")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("智能资产配置策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("智能资产配置策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 更新历史数据
        for vt_symbol, bar in bars.items():
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > 60:
                self.history_bars[vt_symbol].pop(0)

        # 评估市场状态
        self._assess_market_state(bars)

        # 调整资产配置
        self._adjust_asset_allocation()

        # 检查是否需要再平衡
        self.days_since_rebalance += 1
        if self.days_since_rebalance >= self.config.rebalance_period:
            self._rebalance_portfolio(bars)
            self.days_since_rebalance = 0

    def _assess_market_state(self, bars: dict[str, BarData]) -> None:
        """
        评估市场状态

        Args:
            bars: K线数据字典
        """
        # 使用第一个标的作为市场代表（如沪深300ETF）
        if not self.vt_symbols:
            return

        vt_symbol = self.vt_symbols[0]
        bars_list = self.history_bars.get(vt_symbol, [])

        if len(bars_list) < 60:
            return

        # 趋势得分（-1到1）
        ma20 = np.mean([b.close_price for b in bars_list[-20:]])
        ma60 = np.mean([b.close_price for b in bars_list[-60:]])
        current = bars_list[-1].close_price

        trend_score = 0.0
        if ma20 > ma60:
            trend_score += 0.3
        if current > ma20:
            trend_score += 0.3

        # 波动率得分（低波动=正面）
        returns = []
        for i in range(1, min(21, len(bars_list))):
            ret = (bars_list[-i].close_price - bars_list[-i-1].close_price) / bars_list[-i-1].close_price
            returns.append(ret)

        volatility = np.std(returns) * np.sqrt(252) if returns else 0.2
        vol_score = max(0, 1 - volatility / 0.3) * 0.4  # 波动率低于30%得高分

        # 综合得分
        self.market_state_score = trend_score + vol_score

        # 判断市场状态
        if self.market_state_score > 0.5:
            new_state = "bull"
        elif self.market_state_score < 0.2:
            new_state = "bear"
        else:
            new_state = "neutral"

        if new_state != self.market_state:
            self.write_log(f"市场状态变化: {self.market_state} -> {new_state}, 得分: {self.market_state_score:.2f}")
            self.market_state = new_state

    def _adjust_asset_allocation(self) -> None:
        """调整资产配置"""
        if self.market_state == "bull":
            # 牛市：增配股票
            self.asset_allocation = {
                "stocks": 0.80,
                "bonds": 0.15,
                "cash": 0.05,
            }
        elif self.market_state == "bear":
            # 熊市：增配债券和现金
            self.asset_allocation = {
                "stocks": 0.30,
                "bonds": 0.40,
                "cash": 0.30,
            }
        else:  # neutral
            # 震荡市：均衡配置
            self.asset_allocation = {
                "stocks": 0.50,
                "bonds": 0.35,
                "cash": 0.15,
            }

    def _rebalance_portfolio(self, bars: dict[str, BarData]) -> None:
        """
        再平衡组合

        Args:
            bars: K线数据字典
        """
        # 简化版：假设所有vt_symbols都是股票
        # 实际应用中应该包含债券ETF、货币基金等

        stock_weight = self.asset_allocation["stocks"]
        total_value = self._get_total_portfolio_value(bars)
        target_stock_value = total_value * stock_weight

        # 平均分配到各股票
        stock_count = len(self.vt_symbols)
        value_per_stock = target_stock_value / stock_count if stock_count > 0 else 0

        for vt_symbol in self.vt_symbols:
            if vt_symbol not in bars:
                continue

            bar = bars[vt_symbol]
            current_position = self.get_position(vt_symbol)
            current_value = current_position * bar.close_price

            target_position = value_per_stock / bar.close_price if bar.close_price > 0 else 0
            delta = target_position - current_position

            if abs(delta) > 1:
                if delta > 0:
                    self.buy(vt_symbol, bar.close_price, delta)
                else:
                    self.sell(vt_symbol, bar.close_price, abs(delta))

                self.write_log(f"再平衡: {vt_symbol}, 目标仓位{target_position:.0f}, 当前{current_position:.0f}")

    def _get_total_portfolio_value(self, bars: dict[str, BarData]) -> float:
        """获取组合总价值"""
        total = 0.0
        for vt_symbol in self.vt_symbols:
            position = self.get_position(vt_symbol)
            if vt_symbol in bars:
                total += position * bars[vt_symbol].close_price
        return max(total, 100000)
