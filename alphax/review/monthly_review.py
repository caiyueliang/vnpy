"""
月度检验工具

提供策略的月度有效性检验和因子IC分析功能。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from scipy import stats


@dataclass
class MonthlyMetrics:
    """月度指标"""
    month_start: datetime
    month_end: datetime
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    trade_count: int


@dataclass
class FactorICAnalysis:
    """因子IC分析结果"""
    factor_name: str
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float
    rank_ic_mean: float
    rank_ic_ir: float
    t_statistic: float
    p_value: float
    is_significant: bool


@dataclass
class StrategyMonthlyReview:
    """策略月度复盘结果"""
    strategy_name: str
    metrics: MonthlyMetrics
    factor_ic_analysis: List[FactorICAnalysis]
    strategy_effectiveness: Dict[str, Any]
    recommendations: List[str]


class MonthlyReview:
    """
    月度检验工具

    对策略进行月度有效性检验，包括因子IC分析和策略表现评估。
    """

    def __init__(
        self,
        benchmark_return: float = 0.0,
        risk_free_rate: float = 0.03,
        significance_level: float = 0.05
    ):
        """
        初始化月度检验

        Args:
            benchmark_return: 基准月收益率
            risk_free_rate: 无风险利率（年化）
            significance_level: 显著性水平
        """
        self.benchmark_return = benchmark_return
        self.risk_free_rate = risk_free_rate
        self.significance_level = significance_level

    def review(
        self,
        strategy_name: str,
        trades: pd.DataFrame,
        daily_returns: pd.Series,
        factor_data: Optional[Dict[str, pd.Series]] = None,
        forward_returns: Optional[pd.Series] = None
    ) -> StrategyMonthlyReview:
        """
        执行月度检验

        Args:
            strategy_name: 策略名称
            trades: 交易记录
            daily_returns: 日收益率
            factor_data: 因子数据字典（可选）
            forward_returns: 前瞻收益（可选）

        Returns:
            月度检验结果
        """
        # 计算月度指标
        metrics = self._calculate_monthly_metrics(daily_returns, trades)

        # 因子IC分析
        factor_ic_analysis = []
        if factor_data is not None and forward_returns is not None:
            for factor_name, factor_values in factor_data.items():
                ic_result = self._calculate_factor_ic(
                    factor_name, factor_values, forward_returns
                )
                factor_ic_analysis.append(ic_result)

        # 策略有效性评估
        strategy_effectiveness = self._evaluate_strategy_effectiveness(
            metrics, factor_ic_analysis
        )

        # 生成建议
        recommendations = self._generate_recommendations(
            metrics, factor_ic_analysis, strategy_effectiveness
        )

        return StrategyMonthlyReview(
            strategy_name=strategy_name,
            metrics=metrics,
            factor_ic_analysis=factor_ic_analysis,
            strategy_effectiveness=strategy_effectiveness,
            recommendations=recommendations
        )

    def _calculate_monthly_metrics(
        self,
        daily_returns: pd.Series,
        trades: pd.DataFrame
    ) -> MonthlyMetrics:
        """
        计算月度指标

        Args:
            daily_returns: 日收益率
            trades: 交易记录

        Returns:
            月度指标
        """
        # 时间范围
        if isinstance(daily_returns.index, pd.DatetimeIndex):
            month_start = daily_returns.index[0]
            month_end = daily_returns.index[-1]
        else:
            month_start = datetime.now() - timedelta(days=30)
            month_end = datetime.now()

        # 总收益
        total_return = (1 + daily_returns).prod() - 1

        # 年化收益
        days = len(daily_returns)
        annualized_return = (1 + total_return) ** (252 / days) - 1

        # 年化波动率
        annualized_volatility = daily_returns.std() * np.sqrt(252)

        # 夏普比率
        excess_return = annualized_return - self.risk_free_rate
        sharpe_ratio = excess_return / (annualized_volatility + 1e-6)

        # Sortino比率
        downside_returns = daily_returns[daily_returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252)
        sortino_ratio = excess_return / (downside_std + 1e-6)

        # 最大回撤
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Calmar比率
        calmar_ratio = annualized_return / (abs(max_drawdown) + 1e-6)

        # 胜率
        win_rate = (daily_returns > 0).mean()

        # 盈亏因子
        gross_profit = daily_returns[daily_returns > 0].sum()
        gross_loss = abs(daily_returns[daily_returns < 0].sum())
        profit_factor = gross_profit / (gross_loss + 1e-6)

        # 交易次数
        trade_count = len(trades)

        return MonthlyMetrics(
            month_start=month_start,
            month_end=month_end,
            total_return=total_return,
            annualized_return=annualized_return,
            annualized_volatility=annualized_volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            trade_count=trade_count
        )

    def _calculate_factor_ic(
        self,
        factor_name: str,
        factor_values: pd.Series,
        forward_returns: pd.Series
    ) -> FactorICAnalysis:
        """
        计算因子IC

        Args:
            factor_name: 因子名称
            factor_values: 因子值
            forward_returns: 前瞻收益

        Returns:
            因子IC分析结果
        """
        # 对齐数据
        aligned_data = pd.DataFrame({
            'factor': factor_values,
            'returns': forward_returns
        }).dropna()

        if len(aligned_data) < 10:
            return FactorICAnalysis(
                factor_name=factor_name,
                ic_mean=0,
                ic_std=0,
                ic_ir=0,
                ic_positive_ratio=0,
                rank_ic_mean=0,
                rank_ic_ir=0,
                t_statistic=0,
                p_value=1,
                is_significant=False
            )

        # 计算IC序列
        window = min(5, len(aligned_data) // 4)
        if window >= 3:
            ic_series = aligned_data['factor'].rolling(window).corr(
                aligned_data['returns']
            ).dropna()
            rank_ic_series = aligned_data['factor'].rolling(window).corr(
                aligned_data['returns'], method='spearman'
            ).dropna()
        else:
            ic_series = pd.Series([aligned_data['factor'].corr(aligned_data['returns'])])
            rank_ic_series = pd.Series([aligned_data['factor'].corr(
                aligned_data['returns'], method='spearman'
            )])

        # 计算统计量
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ic_ir = ic_mean / (ic_std + 1e-6)
        ic_positive_ratio = (ic_series > 0).mean()

        rank_ic_mean = rank_ic_series.mean()
        rank_ic_ir = rank_ic_mean / (rank_ic_series.std() + 1e-6)

        # T检验
        t_stat, p_value = stats.ttest_1samp(ic_series.dropna(), 0)

        # 判断是否显著
        is_significant = p_value < self.significance_level and abs(ic_mean) > 0.02

        return FactorICAnalysis(
            factor_name=factor_name,
            ic_mean=ic_mean,
            ic_std=ic_std,
            ic_ir=ic_ir,
            ic_positive_ratio=ic_positive_ratio,
            rank_ic_mean=rank_ic_mean,
            rank_ic_ir=rank_ic_ir,
            t_statistic=t_stat,
            p_value=p_value,
            is_significant=is_significant
        )

    def _evaluate_strategy_effectiveness(
        self,
        metrics: MonthlyMetrics,
        factor_ic_analysis: List[FactorICAnalysis]
    ) -> Dict[str, Any]:
        """
        评估策略有效性

        Args:
            metrics: 月度指标
            factor_ic_analysis: 因子IC分析列表

        Returns:
            有效性评估结果
        """
        effectiveness = {
            'is_profitable': metrics.total_return > 0,
            'is_risk_adjusted_profitable': metrics.sharpe_ratio > 1,
            'is_drawdown_acceptable': metrics.max_drawdown > -0.2,
            'is_stable': metrics.win_rate > 0.45,
            'significant_factors': [],
            'effectiveness_score': 0.0
        }

        # 统计显著因子
        for ic_result in factor_ic_analysis:
            if ic_result.is_significant:
                effectiveness['significant_factors'].append(ic_result.factor_name)

        # 计算综合有效性得分
        score = 0
        if effectiveness['is_profitable']:
            score += 20
        if effectiveness['is_risk_adjusted_profitable']:
            score += 25
        if effectiveness['is_drawdown_acceptable']:
            score += 20
        if effectiveness['is_stable']:
            score += 15
        score += len(effectiveness['significant_factors']) * 5

        effectiveness['effectiveness_score'] = min(score, 100)

        # 有效性等级
        if score >= 80:
            effectiveness['grade'] = 'A'
        elif score >= 60:
            effectiveness['grade'] = 'B'
        elif score >= 40:
            effectiveness['grade'] = 'C'
        else:
            effectiveness['grade'] = 'D'

        return effectiveness

    def _generate_recommendations(
        self,
        metrics: MonthlyMetrics,
        factor_ic_analysis: List[FactorICAnalysis],
        strategy_effectiveness: Dict[str, Any]
    ) -> List[str]:
        """
        生成改进建议

        Args:
            metrics: 月度指标
            factor_ic_analysis: 因子IC分析
            strategy_effectiveness: 有效性评估

        Returns:
            建议列表
        """
        recommendations = []

        # 基于收益表现
        if metrics.total_return < -0.1:
            recommendations.append("🚨 本月亏损超过10%，策略可能失效，建议暂停并重新评估")
        elif metrics.total_return < 0:
            recommendations.append("⚠️ 本月亏损，建议检查市场环境是否适合当前策略")
        elif metrics.total_return > 0.1:
            recommendations.append("✅ 本月表现优异，策略运行良好")

        # 基于夏普比率
        if metrics.sharpe_ratio < 0.5:
            recommendations.append("🚨 夏普比率过低，风险收益比不合理，需要优化")
        elif metrics.sharpe_ratio < 1:
            recommendations.append("⚠️ 夏普比率偏低，建议优化风险控制")

        # 基于最大回撤
        if metrics.max_drawdown < -0.15:
            recommendations.append("🚨 回撤过大，建议收紧止损条件")
        elif metrics.max_drawdown < -0.1:
            recommendations.append("⚠️ 回撤较大，关注风险控制")

        # 基于因子IC
        significant_factors = strategy_effectiveness.get('significant_factors', [])
        if len(significant_factors) == 0 and len(factor_ic_analysis) > 0:
            recommendations.append("⚠️ 本月无显著有效因子，建议重新筛选因子")
        elif len(significant_factors) >= 3:
            recommendations.append(f"✅ 本月有{len(significant_factors)}个显著因子，因子模型有效")

        # 基于有效性得分
        score = strategy_effectiveness.get('effectiveness_score', 0)
        if score < 40:
            recommendations.append("🚨 策略有效性评分过低，建议全面审查策略逻辑")
        elif score < 60:
            recommendations.append("⚠️ 策略有效性一般，建议针对性优化")

        # 基于Calmar比率
        if metrics.calmar_ratio < 1:
            recommendations.append("⚠️ Calmar比率偏低，收益与回撤不匹配")

        # 如果一切正常
        if not recommendations:
            recommendations.append("✅ 本月策略表现正常，各项指标良好")

        return recommendations

    def generate_report(
        self,
        review: StrategyMonthlyReview,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成月度检验报告

        Args:
            review: 检验结果
            output_path: 输出路径

        Returns:
            报告文本
        """
        lines = []
        lines.append("=" * 70)
        lines.append(f"📊 策略月度检验报告: {review.strategy_name}")
        lines.append("=" * 70)
        lines.append("")

        # 基本信息
        m = review.metrics
        lines.append(f"📅 检验周期: {m.month_start.strftime('%Y-%m-%d')} 至 {m.month_end.strftime('%Y-%m-%d')}")
        lines.append("")

        # 收益指标
        lines.append("【收益表现】")
        lines.append(f"  月收益率: {m.total_return:+.2%}")
        lines.append(f"  年化收益: {m.annualized_return:+.2%}")
        lines.append("")

        # 风险指标
        lines.append("【风险指标】")
        lines.append(f"  年化波动率: {m.annualized_volatility:.2%}")
        lines.append(f"  夏普比率: {m.sharpe_ratio:.2f}")
        lines.append(f"  Sortino比率: {m.sortino_ratio:.2f}")
        lines.append(f"  最大回撤: {m.max_drawdown:.2%}")
        lines.append(f"  Calmar比率: {m.calmar_ratio:.2f}")
        lines.append("")

        # 交易统计
        lines.append("【交易统计】")
        lines.append(f"  交易次数: {m.trade_count}")
        lines.append(f"  胜率: {m.win_rate:.1%}")
        lines.append(f"  盈亏因子: {m.profit_factor:.2f}")
        lines.append("")

        # 因子IC分析
        if review.factor_ic_analysis:
            lines.append("【因子IC分析】")
            for ic in review.factor_ic_analysis:
                sig_marker = "✅" if ic.is_significant else "❌"
                lines.append(f"  {sig_marker} {ic.factor_name}:")
                lines.append(f"    IC均值: {ic.ic_mean:.4f}, IC_IR: {ic.ic_ir:.2f}")
                lines.append(f"    Rank IC: {ic.rank_ic_mean:.4f}, P值: {ic.p_value:.4f}")
            lines.append("")

        # 有效性评估
        se = review.strategy_effectiveness
        lines.append("【策略有效性评估】")
        lines.append(f"  有效性评分: {se['effectiveness_score']}/100 (等级: {se['grade']})")
        lines.append(f"  盈利性: {'✅' if se['is_profitable'] else '❌'}")
        lines.append(f"  风险调整收益: {'✅' if se['is_risk_adjusted_profitable'] else '❌'}")
        lines.append(f"  回撤可控: {'✅' if se['is_drawdown_acceptable'] else '❌'}")
        lines.append(f"  稳定性: {'✅' if se['is_stable'] else '❌'}")
        if se['significant_factors']:
            lines.append(f"  显著因子: {', '.join(se['significant_factors'])}")
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
        review: StrategyMonthlyReview,
        output_path: str
    ) -> None:
        """
        导出检验结果为JSON

        Args:
            review: 检验结果
            output_path: 输出路径
        """
        data = {
            'strategy_name': review.strategy_name,
            'metrics': {
                'month_start': review.metrics.month_start.isoformat(),
                'month_end': review.metrics.month_end.isoformat(),
                'total_return': review.metrics.total_return,
                'annualized_return': review.metrics.annualized_return,
                'annualized_volatility': review.metrics.annualized_volatility,
                'sharpe_ratio': review.metrics.sharpe_ratio,
                'sortino_ratio': review.metrics.sortino_ratio,
                'max_drawdown': review.metrics.max_drawdown,
                'calmar_ratio': review.metrics.calmar_ratio,
                'win_rate': review.metrics.win_rate,
                'profit_factor': review.metrics.profit_factor,
                'trade_count': review.metrics.trade_count
            },
            'factor_ic_analysis': [
                {
                    'factor_name': ic.factor_name,
                    'ic_mean': ic.ic_mean,
                    'ic_std': ic.ic_std,
                    'ic_ir': ic.ic_ir,
                    'ic_positive_ratio': ic.ic_positive_ratio,
                    'rank_ic_mean': ic.rank_ic_mean,
                    'rank_ic_ir': ic.rank_ic_ir,
                    't_statistic': ic.t_statistic,
                    'p_value': ic.p_value,
                    'is_significant': ic.is_significant
                }
                for ic in review.factor_ic_analysis
            ],
            'strategy_effectiveness': review.strategy_effectiveness,
            'recommendations': review.recommendations
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
