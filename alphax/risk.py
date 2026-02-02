"""
风险管理模块

实现三级风控体系：
- Level 1: 账户级风控
- Level 2: 策略级风控
- Level 3: 交易级风控
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, date

from collections import defaultdict

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

    # 交易级限制
    max_single_trade_loss_pct: float = 0.02   # 单笔交易最大亏损 2%
    max_order_size: int = 100000              # 单笔最大下单数量
    max_daily_orders: int = 1000              # 单日最大下单次数


@dataclass
class RiskStatus:
    """风险状态"""
    level: RiskLevel = RiskLevel.NORMAL
    messages: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    blocked: bool = False


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

    def set_capital(self, initial: float, current: float) -> None:
        """设置资金"""
        self.initial_capital = initial
        self.current_capital = current
        self.total_pnl = current - initial

    def update_pnl(self, pnl: float, strategy_name: str | None = None) -> RiskStatus:
        """更新盈亏"""
        self.daily_pnl += pnl
        self.total_pnl += pnl

        if strategy_name:
            self.strategy_pnl[strategy_name] += pnl
            # 更新策略峰值和回撤
            if self.strategy_pnl[strategy_name] > self.strategy_peak[strategy_name]:
                self.strategy_peak[strategy_name] = self.strategy_pnl[strategy_name]
            else:
                dd = self.strategy_peak[strategy_name] - self.strategy_pnl[strategy_name]
                self.strategy_drawdown[strategy_name] = dd

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
        for strategy_name, drawdown in self.strategy_drawdown.items():
            dd_pct = drawdown / self.initial_capital if self.initial_capital > 0 else 0
            if dd_pct >= self.limits.max_strategy_drawdown_pct:
                if RiskLevel.DANGER.value > status.level.value:
                    status.level = RiskLevel.DANGER
                status.messages.append(f"策略 {strategy_name} 回撤 {dd_pct:.2%} 超过限制")

        # Level 3: 交易级风控检查
        if self.daily_orders >= self.limits.max_daily_orders:
            if RiskLevel.WARNING.value > status.level.value:
                status.level = RiskLevel.WARNING
            status.messages.append(f"单日订单数 {self.daily_orders} 超过限制")

        status.blocked = status.level in (RiskLevel.DANGER, RiskLevel.CRITICAL)
        return status

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
