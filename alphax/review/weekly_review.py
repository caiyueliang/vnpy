"""
周度评估工具

提供策略的周度表现评估和参数微调功能。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json


@dataclass
class WeeklyMetrics:
    """周度指标"""
    week_start: datetime
    week_end: datetime
    total_return: float
    benchmark_return: float
    alpha: float
    beta: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    volatility: float
    trade_count: int


@dataclass
class StrategyWeeklyReview:
    """策略周度复盘结果"""
    strategy_name: str
    metrics: WeeklyMetrics
    signal_quality: Dict[str, float]
    parameter_sensitivity: Dict[str, Any]
    recommendations: List[str]


class WeeklyReview:
    """
    周度评估工具

    对策略进行周度表现评估，提供参数微调建议。
    """

    def __init__(
        self,
        benchmark_return: float = 0.0,
        risk_free_rate: float = 0.03
    ):
        """
        初始化周度评估

        Args:
            benchmark_return: 基准周收益率
            risk_free_rate: 无风险利率（年化）
        """
        self.benchmark_return = benchmark_return
        self.risk_free_rate = risk_free_rate

    def review(
        self,
        strategy_name: str,
        trades: pd.DataFrame,
        daily_returns: pd.Series,
        signals: Optional[pd.DataFrame] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> StrategyWeeklyReview:
        """
        执行周度复盘

        Args:
            strategy_name: 策略名称
            trades: 交易记录DataFrame
            daily_returns: 日收益率序列
            signals: 信号记录DataFrame（可选）
            parameters: 当前参数（可选）

        Returns:
            周度复盘结果
        """
        # 计算周度指标
        metrics = self._calculate_weekly_metrics(daily_returns, trades)

        # 评估信号质量
        signal_quality = self._evaluate_signal_quality(signals, daily_returns)

        # 参数敏感性分析
        parameter_sensitivity = self._analyze_parameter_sensitivity(
            parameters, daily_returns
        )

        # 生成建议
        recommendations = self._generate_recommendations(
            metrics, signal_quality, parameter_sensitivity
        )

        return StrategyWeeklyReview(
            strategy_name=strategy_name,
            metrics=metrics,
            signal_quality=signal_quality,
            parameter_sensitivity=parameter_sensitivity,
            recommendations=recommendations
        )

    def _calculate_weekly_metrics(
        self,
        daily_returns: pd.Series,
        trades: pd.DataFrame
    ) -> WeeklyMetrics:
        """
        计算周度指标

        Args:
            daily_returns: 日收益率
            trades: 交易记录

        Returns:
            周度指标
        """
        # 时间范围
        if isinstance(daily_returns.index, pd.DatetimeIndex):
            week_start = daily_returns.index[0]
            week_end = daily_returns.index[-1]
        else:
            week_start = datetime.now() - timedelta(days=7)
            week_end = datetime.now()

        # 总收益
        total_return = (1 + daily_returns).prod() - 1

        # Alpha和Beta（简化计算）
        benchmark_return = self.benchmark_return
        alpha = total_return - benchmark_return
        beta = 1.0  # 简化假设

        # 夏普比率（周度）
        excess_returns = daily_returns - self.risk_free_rate / 252
        sharpe_ratio = (
            excess_returns.mean() / (excess_returns.std() + 1e-6) * np.sqrt(252)
        )

        # 最大回撤
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # 胜率
        win_rate = (daily_returns > 0).mean()

        # 盈亏比
        avg_gain = daily_returns[daily_returns > 0].mean()
        avg_loss = abs(daily_returns[daily_returns < 0].mean())
        profit_loss_ratio = avg_gain / (avg_loss + 1e-6)

        # 波动率（年化）
        volatility = daily_returns.std() * np.sqrt(252)

        # 交易次数
        trade_count = len(trades)

        return WeeklyMetrics(
            week_start=week_start,
            week_end=week_end,
            total_return=total_return,
            benchmark_return=benchmark_return,
            alpha=alpha,
            beta=beta,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            volatility=volatility,
            trade_count=trade_count
        )

    def _evaluate_signal_quality(
        self,
        signals: Optional[pd.DataFrame],
        daily_returns: pd.Series
    ) -> Dict[str, float]:
        """
        评估信号质量

        Args:
            signals: 信号记录
            daily_returns: 日收益率

        Returns:
            信号质量指标
        """
        if signals is None or len(signals) == 0:
            return {
                'signal_accuracy': 0.0,
                'signal_coverage': 0.0,
                'signal_consistency': 0.0,
                'signal_timing': 0.0
            }

        # 信号准确率
        if 'direction' in signals.columns and 'actual_return' in signals.columns:
            correct = (
                (signals['direction'] == 1) & (signals['actual_return'] > 0) |
                (signals['direction'] == -1) & (signals['actual_return'] < 0)
            ).sum()
            signal_accuracy = correct / len(signals)
        else:
            signal_accuracy = 0.5

        # 信号覆盖率
        signal_coverage = len(signals) / len(daily_returns)

        # 信号一致性（信号方向变化的频率）
        if 'direction' in signals.columns:
            direction_changes = signals['direction'].diff().abs().sum()
            signal_consistency = 1 - (direction_changes / (len(signals) - 1 + 1e-6))
        else:
            signal_consistency = 0.5

        # 信号时效性（信号与收益的时滞相关性）
        signal_timing = 0.5  # 简化计算

        return {
            'signal_accuracy': signal_accuracy,
            'signal_coverage': signal_coverage,
            'signal_consistency': signal_consistency,
            'signal_timing': signal_timing
        }

    def _analyze_parameter_sensitivity(
        self,
        parameters: Optional[Dict[str, Any]],
        daily_returns: pd.Series
    ) -> Dict[str, Any]:
        """
        分析参数敏感性

        Args:
            parameters: 当前参数
            daily_returns: 日收益率

        Returns:
            参数敏感性分析结果
        """
        if parameters is None:
            return {}

        sensitivity = {}

        # 对每个数值参数进行敏感性分析
        for param_name, param_value in parameters.items():
            if isinstance(param_value, (int, float)) and param_value != 0:
                # 测试参数变化±10%的影响
                variations = [-0.1, 0, 0.1]
                results = []

                for var in variations:
                    # 模拟不同参数值的表现（简化）
                    adjusted_value = param_value * (1 + var)
                    # 假设参数调整对收益的影响（实际应重新回测）
                    simulated_return = daily_returns.mean() * (1 + var * 0.5)
                    results.append({
                        'param_value': adjusted_value,
                        'simulated_return': simulated_return
                    })

                # 计算敏感性
                returns = [r['simulated_return'] for r in results]
                sensitivity[param_name] = {
                    'current_value': param_value,
                    'sensitivity_score': np.std(returns) / (abs(np.mean(returns)) + 1e-6),
                    'recommended_direction': 'increase' if returns[-1] > returns[0] else 'decrease'
                }

        return sensitivity

    def _generate_recommendations(
        self,
        metrics: WeeklyMetrics,
        signal_quality: Dict[str, float],
        parameter_sensitivity: Dict[str, Any]
    ) -> List[str]:
        """
        生成改进建议

        Args:
            metrics: 周度指标
            signal_quality: 信号质量
            parameter_sensitivity: 参数敏感性

        Returns:
            建议列表
        """
        recommendations = []

        # 基于收益表现
        if metrics.total_return < -0.05:
            recommendations.append("⚠️ 本周亏损超过5%，建议暂停交易并检查策略逻辑")
        elif metrics.total_return < 0:
            recommendations.append("📉 本周小幅亏损，建议关注市场变化")
        elif metrics.total_return > 0.05:
            recommendations.append("✅ 本周表现优异，可适当增加仓位")

        # 基于夏普比率
        if metrics.sharpe_ratio < 0.5:
            recommendations.append("⚠️ 夏普比率偏低，建议优化风险收益比")
        elif metrics.sharpe_ratio > 2:
            recommendations.append("✅ 夏普比率优秀，策略风险控制好")

        # 基于最大回撤
        if metrics.max_drawdown < -0.1:
            recommendations.append("🚨 回撤过大，建议加强止损机制")

        # 基于胜率
        if metrics.win_rate < 0.4:
            recommendations.append("⚠️ 胜率偏低，建议优化入场条件")

        # 基于信号质量
        if signal_quality.get('signal_accuracy', 0) < 0.5:
            recommendations.append("⚠️ 信号准确率不足，建议重新校准信号")

        # 基于参数敏感性
        for param, analysis in parameter_sensitivity.items():
            if analysis.get('sensitivity_score', 0) > 0.5:
                direction = analysis.get('recommended_direction', '')
                recommendations.append(
                    f"🔧 参数'{param}'敏感度高，建议{direction}调整"
                )

        # 如果一切正常
        if not recommendations:
            recommendations.append("✅ 本周表现正常，继续保持")

        return recommendations

    def generate_report(
        self,
        review: StrategyWeeklyReview,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成周度复盘报告

        Args:
            review: 复盘结果
            output_path: 输出路径

        Returns:
            报告文本
        """
        lines = []
        lines.append("=" * 70)
        lines.append(f"📊 策略周度复盘报告: {review.strategy_name}")
        lines.append("=" * 70)
        lines.append("")

        # 基本信息
        m = review.metrics
        lines.append(f"📅 复盘周期: {m.week_start.strftime('%Y-%m-%d')} 至 {m.week_end.strftime('%Y-%m-%d')}")
        lines.append("")

        # 收益指标
        lines.append("【收益表现】")
        lines.append(f"  周收益率: {m.total_return:+.2%}")
        lines.append(f"  基准收益: {m.benchmark_return:+.2%}")
        lines.append(f"  Alpha: {m.alpha:+.2%}")
        lines.append(f"  Beta: {m.beta:.2f}")
        lines.append("")

        # 风险指标
        lines.append("【风险指标】")
        lines.append(f"  夏普比率: {m.sharpe_ratio:.2f}")
        lines.append(f"  最大回撤: {m.max_drawdown:.2%}")
        lines.append(f"  波动率: {m.volatility:.2%}")
        lines.append("")

        # 交易统计
        lines.append("【交易统计】")
        lines.append(f"  交易次数: {m.trade_count}")
        lines.append(f"  胜率: {m.win_rate:.1%}")
        lines.append(f"  盈亏比: {m.profit_loss_ratio:.2f}")
        lines.append("")

        # 信号质量
        lines.append("【信号质量】")
        for key, value in review.signal_quality.items():
            lines.append(f"  {key}: {value:.2%}")
        lines.append("")

        # 参数建议
        if review.parameter_sensitivity:
            lines.append("【参数优化建议】")
            for param, analysis in review.parameter_sensitivity.items():
                lines.append(f"  {param}:")
                lines.append(f"    当前值: {analysis['current_value']}")
                lines.append(f"    敏感度: {analysis['sensitivity_score']:.2f}")
                lines.append(f"    建议: {analysis['recommended_direction']}")
            lines.append("")

        # 改进建议
        lines.append("【改进建议】")
        for rec in review.recommendations:
            lines.append(f"  {rec}")
        lines.append("")

        report = "\n".join(lines)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)

        return report

    def export_to_json(
        self,
        review: StrategyWeeklyReview,
        output_path: str
    ) -> None:
        """
        导出复盘结果为JSON

        Args:
            review: 复盘结果
            output_path: 输出路径
        """
        data = {
            'strategy_name': review.strategy_name,
            'metrics': {
                'week_start': review.metrics.week_start.isoformat(),
                'week_end': review.metrics.week_end.isoformat(),
                'total_return': review.metrics.total_return,
                'benchmark_return': review.metrics.benchmark_return,
                'alpha': review.metrics.alpha,
                'beta': review.metrics.beta,
                'sharpe_ratio': review.metrics.sharpe_ratio,
                'max_drawdown': review.metrics.max_drawdown,
                'win_rate': review.metrics.win_rate,
                'profit_loss_ratio': review.metrics.profit_loss_ratio,
                'volatility': review.metrics.volatility,
                'trade_count': review.metrics.trade_count
            },
            'signal_quality': review.signal_quality,
            'parameter_sensitivity': review.parameter_sensitivity,
            'recommendations': review.recommendations
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
