"""
风险管理模块

实现三级风控体系：
- Level 1: 账户级风控
- Level 2: 策略级风控
- Level 3: 交易级风控
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta

from collections import defaultdict

import numpy as np
import pandas as pd

from vnpy.trader.object import OrderData, TradeData
from vnpy.trader.constant import Direction


class RiskLevel(Enum):
    """风险等级"""
    NORMAL = 0          # 正常
    WARNING = 1         # 警告
    DANGER = 2          # 危险
    CRITICAL = 3        # 严重


@dataclass
class RiskLimits:
    """风险限制配置"""
    # 账户级限制
    max_daily_loss_pct: float = 0.05          # 单日最大亏损比例 5%
    max_total_loss_pct: float = 0.20          # 总账户最大亏损比例 20%
    max_single_position_pct: float = 0.20     # 单品种最大持仓比例 20%
    max_margin_ratio: float = 0.80            # 最大保证金比例 80%

    # 策略级限制
    max_strategy_drawdown_pct: float = 0.10   # 策略最大回撤 10%
    max_strategy_daily_loss_pct: float = 0.05 # 策略单日最大亏损 5%
    max_strategy_capital_pct: float = 0.30    # 策略最大资金使用比例 30%
    max_strategy_correlation: float = 0.80    # 策略最大相关性 80%

    # 交易级限制
    max_single_trade_loss_pct: float = 0.02   # 单笔交易最大亏损 2%
    max_order_size: int = 100000              # 单笔最大下单数量
    max_daily_orders: int = 1000              # 单日最大下单次数
    max_slippage_pct: float = 0.0005          # 最大滑点比例 0.05%
    min_liquidity_ratio: float = 0.05         # 最小流动性比例 5%


@dataclass
class RiskStatus:
    """风险状态"""
    level: RiskLevel = RiskLevel.NORMAL
    messages: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    blocked: bool = False


@dataclass
class StrategyRiskConfig:
    """策略风险配置"""
    strategy_name: str
    enabled: bool = True                      # 策略是否启用
    max_capital: float = 0.0                  # 策略最大资金
    max_drawdown_pct: float = 0.10            # 策略最大回撤比例
    max_daily_loss_pct: float = 0.05          # 策略单日最大亏损比例
    max_correlation: float = 0.80             # 策略最大相关性
    pause_until: datetime | None = None       # 暂停直到


@dataclass
class TradeRiskCheck:
    """交易风险检查配置"""
    vt_symbol: str
    direction: Direction
    volume: float
    price: float
    expected_price: float | None = None       # 预期成交价格（用于滑点检查）
    market_volume: float = 0.0                # 市场成交量（用于流动性检查）
    up_limit: float = 0.0                     # 涨停价
    down_limit: float = 0.0                   # 跌停价


class RiskManager:
    """
    风险管理器

    实现项目规则文档中的三级风控体系
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        """Constructor"""
        self.limits: RiskLimits = limits or RiskLimits()

        # 账户状态
        self.initial_capital: float = 0.0
        self.current_capital: float = 0.0
        self.daily_pnl: float = 0.0
        self.total_pnl: float = 0.0

        # 策略状态
        self.strategy_pnl: dict[str, float] = defaultdict(float)
        self.strategy_peak: dict[str, float] = defaultdict(float)
        self.strategy_drawdown: dict[str, float] = defaultdict(float)
        self.strategy_daily_pnl: dict[str, float] = defaultdict(float)
        self.strategy_capital: dict[str, float] = defaultdict(float)  # 策略占用资金
        self.strategy_returns: dict[str, list[float]] = defaultdict(list)  # 策略收益率序列

        # 策略风险配置
        self.strategy_configs: dict[str, StrategyRiskConfig] = {}

        # 交易统计
        self.daily_orders: int = 0
        self.daily_trades: int = 0
        self.last_trade_date: date = date.today()

        # 持仓状态
        self.positions: dict[str, float] = defaultdict(float)
        self.position_value: dict[str, float] = defaultdict(float)

        # 熔断状态
        self.circuit_breaker_level: int = 0  # 0=正常, 1=一级熔断, 2=二级熔断, 3=三级熔断
        self.circuit_breaker_until: datetime | None = None

        # 连续亏损统计
        self.consecutive_loss_days: int = 0
        self.last_loss_date: date | None = None

        # 滑点统计
        self.slippage_stats: dict[str, list[float]] = defaultdict(list)  # 各品种滑点统计

    def set_capital(self, initial: float, current: float) -> None:
        """设置资金"""
        self.initial_capital = initial
        self.current_capital = current
        self.total_pnl = current - initial

    def register_strategy(self, config: StrategyRiskConfig) -> None:
        """
        注册策略风险配置

        Args:
            config: 策略风险配置
        """
        self.strategy_configs[config.strategy_name] = config

    def enable_strategy(self, strategy_name: str) -> None:
        """启用策略"""
        if strategy_name in self.strategy_configs:
            self.strategy_configs[strategy_name].enabled = True
            self.strategy_configs[strategy_name].pause_until = None

    def disable_strategy(self, strategy_name: str, pause_days: int = 0) -> None:
        """
        禁用策略

        Args:
            strategy_name: 策略名称
            pause_days: 暂停天数，0表示永久禁用
        """
        if strategy_name in self.strategy_configs:
            self.strategy_configs[strategy_name].enabled = False
            if pause_days > 0:
                self.strategy_configs[strategy_name].pause_until = datetime.now() + timedelta(days=pause_days)

    def is_strategy_enabled(self, strategy_name: str) -> bool:
        """
        检查策略是否启用

        Args:
            strategy_name: 策略名称

        Returns:
            是否启用
        """
        if strategy_name not in self.strategy_configs:
            return True  # 未注册的策略默认启用

        config = self.strategy_configs[strategy_name]

        # 检查暂停时间
        if config.pause_until and datetime.now() < config.pause_until:
            return False

        # 如果暂停时间已过，自动恢复
        if config.pause_until and datetime.now() >= config.pause_until:
            config.enabled = True
            config.pause_until = None

        return config.enabled

    def update_pnl(self, pnl: float, strategy_name: str | None = None) -> RiskStatus:
        """更新盈亏"""
        self.daily_pnl += pnl
        self.total_pnl += pnl

        if strategy_name:
            self.strategy_pnl[strategy_name] += pnl
            self.strategy_daily_pnl[strategy_name] += pnl

            # 更新策略收益率序列
            if self.initial_capital > 0:
                daily_return = pnl / self.initial_capital
                self.strategy_returns[strategy_name].append(daily_return)
                # 保留最近252个交易日（约一年）的数据
                if len(self.strategy_returns[strategy_name]) > 252:
                    self.strategy_returns[strategy_name] = self.strategy_returns[strategy_name][-252:]

            # 更新策略峰值和回撤
            if self.strategy_pnl[strategy_name] > self.strategy_peak[strategy_name]:
                self.strategy_peak[strategy_name] = self.strategy_pnl[strategy_name]
            else:
                dd = self.strategy_peak[strategy_name] - self.strategy_pnl[strategy_name]
                self.strategy_drawdown[strategy_name] = dd

        # 更新连续亏损天数
        if pnl < 0:
            today = date.today()
            if self.last_loss_date != today:
                if self.last_loss_date and (today - self.last_loss_date).days == 1:
                    self.consecutive_loss_days += 1
                else:
                    self.consecutive_loss_days = 1
                self.last_loss_date = today

                # 检查三级熔断条件
                if self.consecutive_loss_days >= 3:
                    self._trigger_circuit_breaker(3)

        return self.check_risk()

    def check_risk(self) -> RiskStatus:
        """检查风险状态"""
        status = RiskStatus()

        # 检查熔断状态
        if self.circuit_breaker_until and datetime.now() < self.circuit_breaker_until:
            status.level = RiskLevel.CRITICAL
            status.messages.append(f"熔断中，直到 {self.circuit_breaker_until}")
            status.blocked = True
            return status

        # 检查日期切换
        today = date.today()
        if today != self.last_trade_date:
            self.daily_pnl = 0.0
            self.daily_orders = 0
            self.daily_trades = 0
            self.strategy_daily_pnl.clear()
            self.last_trade_date = today

        # Level 1: 账户级风控检查
        daily_loss_pct = abs(self.daily_pnl) / self.initial_capital if self.initial_capital > 0 else 0
        total_loss_pct = abs(self.total_pnl) / self.initial_capital if self.initial_capital > 0 else 0

        if daily_loss_pct >= self.limits.max_daily_loss_pct:
            status.level = RiskLevel.CRITICAL
            status.messages.append(f"单日亏损 {daily_loss_pct:.2%} 超过限制 {self.limits.max_daily_loss_pct:.2%}")
            self._trigger_circuit_breaker(1)

        if total_loss_pct >= self.limits.max_total_loss_pct:
            status.level = RiskLevel.CRITICAL
            status.messages.append(f"总亏损 {total_loss_pct:.2%} 超过限制 {self.limits.max_total_loss_pct:.2%}")
            self._trigger_circuit_breaker(2)

        # Level 2: 策略级风控检查
        for strategy_name, config in self.strategy_configs.items():
            # 检查策略是否启用
            if not self.is_strategy_enabled(strategy_name):
                continue

            # 检查策略回撤
            drawdown = self.strategy_drawdown.get(strategy_name, 0)
            dd_pct = drawdown / self.initial_capital if self.initial_capital > 0 else 0
            max_dd = config.max_drawdown_pct if config.max_drawdown_pct > 0 else self.limits.max_strategy_drawdown_pct

            if dd_pct >= max_dd:
                if RiskLevel.DANGER.value > status.level.value:
                    status.level = RiskLevel.DANGER
                status.messages.append(f"策略 {strategy_name} 回撤 {dd_pct:.2%} 超过限制 {max_dd:.2%}")
                self.disable_strategy(strategy_name, pause_days=1)

            # 检查策略单日亏损
            daily_loss = abs(self.strategy_daily_pnl.get(strategy_name, 0))
            daily_loss_pct = daily_loss / self.initial_capital if self.initial_capital > 0 else 0
            max_daily_loss = config.max_daily_loss_pct if config.max_daily_loss_pct > 0 else self.limits.max_strategy_daily_loss_pct

            if daily_loss_pct >= max_daily_loss:
                if RiskLevel.DANGER.value > status.level.value:
                    status.level = RiskLevel.DANGER
                status.messages.append(f"策略 {strategy_name} 单日亏损 {daily_loss_pct:.2%} 超过限制 {max_daily_loss:.2%}")
                self.disable_strategy(strategy_name, pause_days=1)

            # 检查策略资金使用
            capital_used = self.strategy_capital.get(strategy_name, 0)
            capital_pct = capital_used / self.current_capital if self.current_capital > 0 else 0
            max_capital = config.max_capital / self.current_capital if config.max_capital > 0 and self.current_capital > 0 else self.limits.max_strategy_capital_pct

            if capital_pct > max_capital:
                if RiskLevel.WARNING.value > status.level.value:
                    status.level = RiskLevel.WARNING
                status.messages.append(f"策略 {strategy_name} 资金使用 {capital_pct:.2%} 超过限制 {max_capital:.2%}")

        # 检查策略相关性
        correlation_violations = self.check_strategy_correlation()
        if correlation_violations:
            if RiskLevel.WARNING.value > status.level.value:
                status.level = RiskLevel.WARNING
            for msg in correlation_violations:
                status.messages.append(msg)

        # Level 3: 交易级风控检查
        if self.daily_orders >= self.limits.max_daily_orders:
            if RiskLevel.WARNING.value > status.level.value:
                status.level = RiskLevel.WARNING
            status.messages.append(f"单日订单数 {self.daily_orders} 超过限制")

        status.blocked = status.level in (RiskLevel.DANGER, RiskLevel.CRITICAL)
        return status

    def check_strategy_correlation(self) -> list[str]:
        """
        检查策略间相关性

        Returns:
            违规信息列表
        """
        violations = []

        # 获取有收益率数据的策略
        strategies_with_returns = {
            name: returns for name, returns in self.strategy_returns.items()
            if len(returns) >= 30  # 至少需要30天数据
        }

        if len(strategies_with_returns) < 2:
            return violations

        # 计算相关性矩阵
        strategy_names = list(strategies_with_returns.keys())
        returns_matrix = np.array([
            strategies_with_returns[name][-60:]  # 使用最近60天数据
            for name in strategy_names
        ])

        # 确保长度一致
        min_len = min(len(r) for r in returns_matrix)
        returns_matrix = np.array([r[-min_len:] for r in returns_matrix])

        # 计算相关性
        correlation_matrix = np.corrcoef(returns_matrix)

        # 检查相关性是否超过阈值
        for i in range(len(strategy_names)):
            for j in range(i + 1, len(strategy_names)):
                corr = correlation_matrix[i, j]
                threshold = self.limits.max_strategy_correlation

                # 使用两个策略中更严格的阈值
                config_i = self.strategy_configs.get(strategy_names[i])
                config_j = self.strategy_configs.get(strategy_names[j])
                if config_i and config_i.max_correlation > 0:
                    threshold = min(threshold, config_i.max_correlation)
                if config_j and config_j.max_correlation > 0:
                    threshold = min(threshold, config_j.max_correlation)

                if abs(corr) >= threshold:
                    violations.append(
                        f"策略 {strategy_names[i]} 和 {strategy_names[j]} 相关性 {corr:.2%} 超过阈值 {threshold:.2%}"
                    )

        return violations

    def check_order(self, vt_symbol: str, direction: Direction, volume: float, price: float) -> RiskStatus:
        """检查订单风险"""
        status = RiskStatus()

        # 检查熔断
        if self.circuit_breaker_until and datetime.now() < self.circuit_breaker_until:
            status.level = RiskLevel.CRITICAL
            status.messages.append("熔断中，禁止新开仓")
            status.blocked = True
            return status

        # 检查单笔订单数量
        if volume > self.limits.max_order_size:
            status.level = RiskLevel.CRITICAL
            status.messages.append(f"订单数量 {volume} 超过限制 {self.limits.max_order_size}")
            status.blocked = True
            return status

        # 检查持仓集中度
        order_value = volume * price
        position_value = self.position_value.get(vt_symbol, 0)
        if direction == Direction.LONG:
            position_value += order_value
        else:
            position_value -= order_value

        position_pct = abs(position_value) / self.current_capital if self.current_capital > 0 else 0
        if position_pct > self.limits.max_single_position_pct:
            status.level = RiskLevel.DANGER
            status.messages.append(f"品种 {vt_symbol} 持仓比例 {position_pct:.2%} 超过限制")
            status.blocked = True
            return status

        return status

    def check_trade_risk(self, trade_check: TradeRiskCheck) -> RiskStatus:
        """
        检查交易级风险（滑点、涨跌停、流动性）

        Args:
            trade_check: 交易风险检查配置

        Returns:
            风险状态
        """
        status = RiskStatus()

        # 1. 涨跌停保护
        if trade_check.direction == Direction.LONG:
            # 买入时检查是否涨停
            if trade_check.up_limit > 0 and trade_check.price >= trade_check.up_limit:
                status.level = RiskLevel.CRITICAL
                status.messages.append(f"品种 {trade_check.vt_symbol} 已涨停，禁止买入")
                status.blocked = True
                return status
        else:
            # 卖出时检查是否跌停
            if trade_check.down_limit > 0 and trade_check.price <= trade_check.down_limit:
                status.level = RiskLevel.CRITICAL
                status.messages.append(f"品种 {trade_check.vt_symbol} 已跌停，禁止卖出")
                status.blocked = True
                return status

        # 2. 滑点检查
        if trade_check.expected_price and trade_check.expected_price > 0:
            slippage = abs(trade_check.price - trade_check.expected_price) / trade_check.expected_price

            # 记录滑点统计
            self.slippage_stats[trade_check.vt_symbol].append(slippage)
            if len(self.slippage_stats[trade_check.vt_symbol]) > 100:
                self.slippage_stats[trade_check.vt_symbol] = self.slippage_stats[trade_check.vt_symbol][-100:]

            if slippage > self.limits.max_slippage_pct:
                status.level = RiskLevel.WARNING
                status.messages.append(
                    f"品种 {trade_check.vt_symbol} 滑点 {slippage:.4%} 超过阈值 {self.limits.max_slippage_pct:.4%}"
                )

        # 3. 流动性检查
        if trade_check.market_volume > 0:
            liquidity_ratio = trade_check.volume / trade_check.market_volume
            if liquidity_ratio > self.limits.min_liquidity_ratio:
                status.level = RiskLevel.DANGER
                status.messages.append(
                    f"品种 {trade_check.vt_symbol} 流动性不足，订单占比 {liquidity_ratio:.2%} 超过阈值 {self.limits.min_liquidity_ratio:.2%}"
                )
                status.blocked = True
                return status

        return status

    def get_average_slippage(self, vt_symbol: str, window: int = 20) -> float:
        """
        获取平均滑点

        Args:
            vt_symbol: 合约代码
            window: 窗口大小

        Returns:
            平均滑点
        """
        slippages = self.slippage_stats.get(vt_symbol, [])
        if not slippages:
            return 0.0
        return np.mean(slippages[-window:])

    def update_strategy_capital(self, strategy_name: str, capital: float) -> None:
        """
        更新策略占用资金

        Args:
            strategy_name: 策略名称
            capital: 占用资金
        """
        self.strategy_capital[strategy_name] = capital

    def update_order(self, order: OrderData) -> None:
        """更新订单统计"""
        self.daily_orders += 1

    def update_trade(self, trade: TradeData) -> None:
        """更新成交统计"""
        self.daily_trades += 1

        # 更新持仓
        if trade.direction == Direction.LONG:
            self.positions[trade.vt_symbol] += trade.volume
        else:
            self.positions[trade.vt_symbol] -= trade.volume

    def update_position_value(self, vt_symbol: str, value: float) -> None:
        """更新持仓市值"""
        self.position_value[vt_symbol] = value

    def _trigger_circuit_breaker(self, level: int) -> None:
        """触发熔断机制"""
        self.circuit_breaker_level = level

        if level == 1:
            # 一级熔断：暂停当日新开仓
            self.circuit_breaker_until = datetime.now().replace(hour=23, minute=59, second=59)
        elif level == 2:
            # 二级熔断：清仓所有头寸
            self.circuit_breaker_until = datetime.now().replace(hour=23, minute=59, second=59)
        elif level == 3:
            # 三级熔断：暂停交易一周
            from datetime import timedelta
            self.circuit_breaker_until = datetime.now() + timedelta(days=7)

    def reset_circuit_breaker(self) -> None:
        """重置熔断状态"""
        self.circuit_breaker_level = 0
        self.circuit_breaker_until = None

    def get_risk_report(self) -> dict:
        """获取风险报告"""
        daily_loss_pct = abs(self.daily_pnl) / self.initial_capital if self.initial_capital > 0 else 0
        total_loss_pct = abs(self.total_pnl) / self.initial_capital if self.initial_capital > 0 else 0

        return {
            "capital": {
                "initial": self.initial_capital,
                "current": self.current_capital,
                "daily_pnl": self.daily_pnl,
                "total_pnl": self.total_pnl,
            },
            "risk_ratios": {
                "daily_loss": daily_loss_pct,
                "total_loss": total_loss_pct,
                "max_daily_loss_limit": self.limits.max_daily_loss_pct,
                "max_total_loss_limit": self.limits.max_total_loss_pct,
            },
            "circuit_breaker": {
                "level": self.circuit_breaker_level,
                "until": self.circuit_breaker_until,
            },
            "trading_stats": {
                "daily_orders": self.daily_orders,
                "daily_trades": self.daily_trades,
            },
            "positions": dict(self.positions),
        }
