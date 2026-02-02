"""
策略评估模块

实现策略绩效分析和风险评估
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """绩效指标"""
    # 收益指标
    total_return: float = 0.0               # 总收益率
    annual_return: float = 0.0              # 年化收益率
    daily_return_mean: float = 0.0          # 日均收益率
    daily_return_std: float = 0.0           # 日收益率标准差

    # 风险指标
    max_drawdown: float = 0.0               # 最大回撤
    max_drawdown_duration: int = 0          # 最大回撤持续时间
    volatility: float = 0.0                 # 波动率
    var_95: float = 0.0                     # 95% VaR

    # 风险调整收益
    sharpe_ratio: float = 0.0               # 夏普比率
    sortino_ratio: float = 0.0              # 索提诺比率
    calmar_ratio: float = 0.0               # 卡尔玛比率

    # 交易指标
    win_rate: float = 0.0                   # 胜率
    profit_loss_ratio: float = 0.0          # 盈亏比
    avg_win: float = 0.0                    # 平均盈利
    avg_loss: float = 0.0                   # 平均亏损
    max_consecutive_wins: int = 0           # 最大连续盈利次数
    max_consecutive_losses: int = 0         # 最大连续亏损次数

    # 其他指标
    total_trades: int = 0                   # 总交易次数
    turnover_rate: float = 0.0              # 换手率


def calculate_max_drawdown(returns: pd.Series) -> tuple[float, int]:
    """计算最大回撤和持续时间"""
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max

    max_dd = drawdown.min()

    # 计算最大回撤持续时间
    is_drawdown = drawdown < 0
    durations: list[int] = []
    current_duration = 0

    for in_dd in is_drawdown:
        if in_dd:
            current_duration += 1
        else:
            if current_duration > 0:
                durations.append(current_duration)
            current_duration = 0

    if current_duration > 0:
        durations.append(current_duration)

    max_duration = max(durations) if durations else 0

    return max_dd, max_duration


def calculate_consecutive_trades(trades: list[float]) -> tuple[int, int]:
    """计算最大连续盈利和亏损次数"""
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for pnl in trades:
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)

    return max_wins, max_losses


class PerformanceEvaluator:
    """
    策略绩效评估器

    评估指标符合项目规则文档要求：
    - 年化收益率 >= 50%
    - 夏普比率 >= 2.0
    - 最大回撤 <= 15%
    - 胜率 >= 55%
    - 盈亏比 >= 1.5
    """

    def __init__(self, risk_free_rate: float = 0.03) -> None:
        """Constructor"""
        self.risk_free_rate: float = risk_free_rate
        self.daily_rf: float = risk_free_rate / 252  # 日度无风险利率

        # 数据存储
        self.daily_returns: list[float] = []
        self.daily_pnl: list[float] = []
        self.trades: list[float] = []
        self.dates: list[datetime] = []
        self.portfolio_values: list[float] = []

    def add_daily_return(self, date: datetime, ret: float, pnl: float, portfolio_value: float) -> None:
        """添加每日收益数据"""
        self.dates.append(date)
        self.daily_returns.append(ret)
        self.daily_pnl.append(pnl)
        self.portfolio_values.append(portfolio_value)

    def add_trade(self, pnl: float) -> None:
        """添加交易盈亏"""
        self.trades.append(pnl)

    def calculate_metrics(self) -> PerformanceMetrics:
        """计算绩效指标"""
        metrics = PerformanceMetrics()

        if not self.daily_returns:
            return metrics

        returns: pd.Series = pd.Series(self.daily_returns)
        returns_values: np.ndarray = returns.to_numpy()

        # 基础收益指标
        metrics.total_return = float(np.prod(1 + returns_values) - 1)
        metrics.annual_return = float((1 + metrics.total_return) ** (252 / len(returns_values)) - 1)
        metrics.daily_return_mean = float(np.mean(returns_values))
        metrics.daily_return_std = float(np.std(returns_values))

        # 风险指标
        metrics.max_drawdown, metrics.max_drawdown_duration = calculate_max_drawdown(returns)
        metrics.volatility = metrics.daily_return_std * np.sqrt(252)
        metrics.var_95 = np.percentile(returns, 5)

        # 风险调整收益
        excess_return = metrics.daily_return_mean - self.daily_rf
        if metrics.daily_return_std > 0:
            metrics.sharpe_ratio = excess_return / metrics.daily_return_std * np.sqrt(252)

        # 索提诺比率（只考虑下行波动）
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            downside_std = downside_returns.std() * np.sqrt(252)
            metrics.sortino_ratio = metrics.annual_return / downside_std

        # 卡尔玛比率
        if metrics.max_drawdown < 0:
            metrics.calmar_ratio = metrics.annual_return / abs(metrics.max_drawdown)

        # 交易指标
        if self.trades:
            winning_trades = [t for t in self.trades if t > 0]
            losing_trades = [t for t in self.trades if t <= 0]

            metrics.total_trades = len(self.trades)
            metrics.win_rate = len(winning_trades) / len(self.trades) if self.trades else 0

            if winning_trades and losing_trades:
                metrics.avg_win = float(np.mean(winning_trades))
                metrics.avg_loss = float(abs(np.mean(losing_trades)))
                metrics.profit_loss_ratio = metrics.avg_win / metrics.avg_loss if metrics.avg_loss > 0 else 0

            metrics.max_consecutive_wins, metrics.max_consecutive_losses = calculate_consecutive_trades(self.trades)

        return metrics

    def evaluate_strategy(self) -> dict:
        """
        评估策略是否符合标准

        根据项目规则文档的评估标准
        """
        metrics = self.calculate_metrics()

        # 评估各项标准
        criteria = {
            "annual_return": {
                "value": metrics.annual_return,
                "threshold": 0.50,
                "passed": metrics.annual_return >= 0.50,
                "description": "年化收益率 >= 50%",
            },
            "sharpe_ratio": {
                "value": metrics.sharpe_ratio,
                "threshold": 2.0,
                "passed": metrics.sharpe_ratio >= 2.0,
                "description": "夏普比率 >= 2.0",
            },
            "max_drawdown": {
                "value": metrics.max_drawdown,
                "threshold": -0.15,
                "passed": metrics.max_drawdown >= -0.15,
                "description": "最大回撤 <= 15%",
            },
            "win_rate": {
                "value": metrics.win_rate,
                "threshold": 0.55,
                "passed": metrics.win_rate >= 0.55,
                "description": "胜率 >= 55%",
            },
            "profit_loss_ratio": {
                "value": metrics.profit_loss_ratio,
                "threshold": 1.5,
                "passed": metrics.profit_loss_ratio >= 1.5,
                "description": "盈亏比 >= 1.5",
            },
        }

        # 计算综合得分
        passed_count = sum(1 for c in criteria.values() if c["passed"])
        total_score = passed_count / len(criteria)

        return {
            "metrics": {
                "total_return": f"{metrics.total_return:.2%}",
                "annual_return": f"{metrics.annual_return:.2%}",
                "sharpe_ratio": f"{metrics.sharpe_ratio:.2f}",
                "max_drawdown": f"{metrics.max_drawdown:.2%}",
                "volatility": f"{metrics.volatility:.2%}",
                "win_rate": f"{metrics.win_rate:.2%}",
                "profit_loss_ratio": f"{metrics.profit_loss_ratio:.2f}",
                "total_trades": metrics.total_trades,
                "calmar_ratio": f"{metrics.calmar_ratio:.2f}",
                "sortino_ratio": f"{metrics.sortino_ratio:.2f}",
            },
            "criteria": criteria,
            "overall_score": total_score,
            "passed": total_score >= 0.8,  # 80%以上指标通过视为合格
        }

    def generate_report(self) -> str:
        """生成评估报告"""
        result = self.evaluate_strategy()
        metrics = result["metrics"]
        criteria = result["criteria"]

        report = []
        report.append("=" * 60)
        report.append("AlphaX 策略绩效评估报告")
        report.append("=" * 60)
        report.append("")

        report.append("【收益指标】")
        report.append(f"  总收益率: {metrics['total_return']}")
        report.append(f"  年化收益率: {metrics['annual_return']}")
        report.append("")

        report.append("【风险指标】")
        report.append(f"  最大回撤: {metrics['max_drawdown']}")
        report.append(f"  波动率: {metrics['volatility']}")
        report.append("")

        report.append("【风险调整收益】")
        report.append(f"  夏普比率: {metrics['sharpe_ratio']}")
        report.append(f"  索提诺比率: {metrics['sortino_ratio']}")
        report.append(f"  卡尔玛比率: {metrics['calmar_ratio']}")
        report.append("")

        report.append("【交易指标】")
        report.append(f"  总交易次数: {metrics['total_trades']}")
        report.append(f"  胜率: {metrics['win_rate']}")
        report.append(f"  盈亏比: {metrics['profit_loss_ratio']}")
        report.append("")

        report.append("【标准评估】")
        for name, criterion in criteria.items():
            status = "✓ 通过" if criterion["passed"] else "✗ 未通过"
            report.append(f"  {criterion['description']}: {status}")
            report.append(f"    实际值: {criterion['value']:.2%}" if "ratio" not in name else f"    实际值: {criterion['value']:.2f}")
        report.append("")

        report.append("【综合评估】")
        report.append(f"  综合得分: {result['overall_score']:.1%}")
        report.append(f"  评估结果: {'合格' if result['passed'] else '不合格'}")
        report.append("")
        report.append("=" * 60)

        return "\n".join(report)

    def get_return_series(self) -> pd.Series:
        """获取收益序列"""
        if not self.dates or not self.daily_returns:
            return pd.Series()
        return pd.Series(self.daily_returns, index=self.dates)

    def get_equity_curve(self) -> pd.Series:
        """获取权益曲线"""
        if not self.dates or not self.daily_returns:
            return pd.Series()
        returns = pd.Series(self.daily_returns, index=self.dates)
        return (1 + returns).cumprod()

    def get_drawdown_series(self) -> pd.Series:
        """获取回撤序列"""
        equity = self.get_equity_curve()
        if equity.empty:
            return pd.Series()
        running_max = equity.expanding().max()
        return (equity - running_max) / running_max
