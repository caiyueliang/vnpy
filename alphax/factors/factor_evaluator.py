"""
因子评估模块

提供因子的IC分析、分层回测等评估功能。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import warnings

from .base import Factor, FactorResult


@dataclass
class ICReturn:
    """IC分析结果"""
    ic_series: pd.Series
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_positive_ratio: float
    rank_ic_mean: float
    rank_ic_std: float
    rank_ic_ir: float


@dataclass
class QuantileReturn:
    """分层回测结果"""
    quantile_returns: pd.DataFrame
    long_short_return: pd.Series
    long_short_sharpe: float
    top_quantile_return: pd.Series
    bottom_quantile_return: pd.Series
    monotonicity: float


@dataclass
class FactorEvaluation:
    """因子综合评估结果"""
    factor_name: str
    ic_analysis: ICReturn
    quantile_analysis: QuantileReturn
    turnover_analysis: Dict[str, float]
    summary: Dict[str, Any]


class FactorEvaluator:
    """
    因子评估器

    提供因子的IC分析、分层回测、换手率分析等功能。
    """

    def __init__(self, forward_period: int = 5, quantiles: int = 5):
        """
        初始化评估器

        Args:
            forward_period: 前瞻收益周期（日）
            quantiles: 分层数量
        """
        self.forward_period = forward_period
        self.quantiles = quantiles

    def evaluate(
        self,
        factor: Factor,
        data: pd.DataFrame,
        price_col: str = 'close',
        date_col: str = 'date',
        **kwargs
    ) -> FactorEvaluation:
        """
        综合评估因子

        Args:
            factor: 因子实例
            data: 包含价格和因子所需数据的DataFrame
            price_col: 价格列名
            date_col: 日期列名

        Returns:
            因子评估结果
        """
        # 计算因子值
        factor_result = factor(data, **kwargs)
        factor_values = factor_result.values

        # 计算前瞻收益
        forward_returns = self._calculate_forward_returns(
            data[price_col], self.forward_period
        )

        # IC分析
        ic_analysis = self._calculate_ic(factor_values, forward_returns)

        # 分层回测
        quantile_analysis = self._quantile_backtest(
            factor_values, forward_returns
        )

        # 换手率分析
        turnover_analysis = self._calculate_turnover(factor_values)

        # 综合摘要
        summary = self._generate_summary(
            factor, ic_analysis, quantile_analysis, turnover_analysis
        )

        return FactorEvaluation(
            factor_name=factor.name,
            ic_analysis=ic_analysis,
            quantile_analysis=quantile_analysis,
            turnover_analysis=turnover_analysis,
            summary=summary
        )

    def _calculate_forward_returns(
        self,
        prices: pd.Series,
        period: int
    ) -> pd.Series:
        """
        计算前瞻收益

        Args:
            prices: 价格序列
            period: 前瞻周期

        Returns:
            前瞻收益序列
        """
        # 计算未来收益
        forward_returns = prices.pct_change(period).shift(-period)
        return forward_returns

    def _calculate_ic(
        self,
        factor_values: pd.Series,
        forward_returns: pd.Series
    ) -> ICReturn:
        """
        计算IC指标

        Args:
            factor_values: 因子值
            forward_returns: 前瞻收益

        Returns:
            IC分析结果
        """
        # 对齐数据
        aligned_data = pd.DataFrame({
            'factor': factor_values,
            'returns': forward_returns
        }).dropna()

        if len(aligned_data) < 10:
            warnings.warn("数据量不足，无法计算IC")
            return ICReturn(
                ic_series=pd.Series(),
                ic_mean=0,
                ic_std=0,
                ic_ir=0,
                ic_positive_ratio=0,
                rank_ic_mean=0,
                rank_ic_std=0,
                rank_ic_ir=0
            )

        # 计算IC（Pearson相关系数）
        ic = aligned_data['factor'].corr(aligned_data['returns'])

        # 计算Rank IC（Spearman相关系数）
        rank_ic = aligned_data['factor'].corr(
            aligned_data['returns'], method='spearman'
        )

        # 计算滚动IC（假设数据是时间序列）
        window = min(20, len(aligned_data) // 4)
        if window >= 5:
            ic_series = aligned_data['factor'].rolling(window).corr(
                aligned_data['returns']
            ).dropna()
        else:
            ic_series = pd.Series([ic])

        # 计算统计指标
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ic_ir = ic_mean / (ic_std + 1e-6)
        ic_positive_ratio = (ic_series > 0).mean()

        # Rank IC统计
        if window >= 5:
            rank_ic_series = aligned_data['factor'].rolling(window).corr(
                aligned_data['returns'], method='spearman'
            ).dropna()
        else:
            rank_ic_series = pd.Series([rank_ic])

        rank_ic_mean = rank_ic_series.mean()
        rank_ic_std = rank_ic_series.std()
        rank_ic_ir = rank_ic_mean / (rank_ic_std + 1e-6)

        return ICReturn(
            ic_series=ic_series,
            ic_mean=ic_mean,
            ic_std=ic_std,
            ic_ir=ic_ir,
            ic_positive_ratio=ic_positive_ratio,
            rank_ic_mean=rank_ic_mean,
            rank_ic_std=rank_ic_std,
            rank_ic_ir=rank_ic_ir
        )

    def _quantile_backtest(
        self,
        factor_values: pd.Series,
        forward_returns: pd.Series
    ) -> QuantileReturn:
        """
        分层回测

        Args:
            factor_values: 因子值
            forward_returns: 前瞻收益

        Returns:
            分层回测结果
        """
        # 对齐数据
        aligned_data = pd.DataFrame({
            'factor': factor_values,
            'returns': forward_returns
        }).dropna()

        if len(aligned_data) < self.quantiles * 2:
            warnings.warn("数据量不足，无法进行分层回测")
            empty_series = pd.Series(0, index=range(self.quantiles))
            return QuantileReturn(
                quantile_returns=pd.DataFrame(),
                long_short_return=empty_series,
                long_short_sharpe=0,
                top_quantile_return=empty_series,
                bottom_quantile_return=empty_series,
                monotonicity=0
            )

        # 按因子值分层
        aligned_data['quantile'] = pd.qcut(
            aligned_data['factor'],
            q=self.quantiles,
            labels=range(1, self.quantiles + 1),
            duplicates='drop'
        )

        # 计算每层收益
        quantile_returns = aligned_data.groupby('quantile')['returns'].mean()

        # 多空收益（最高层 - 最低层）
        long_short = (
            aligned_data[aligned_data['quantile'] == self.quantiles]['returns'].values -
            aligned_data[aligned_data['quantile'] == 1]['returns'].values
        )

        # 如果长度不一致，取交集
        top_returns = aligned_data[aligned_data['quantile'] == self.quantiles]['returns']
        bottom_returns = aligned_data[aligned_data['quantile'] == 1]['returns']

        # 多空夏普
        long_short_sharpe = (
            long_short.mean() / (long_short.std() + 1e-6) * np.sqrt(252)
        )

        # 单调性检验
        monotonicity = self._test_monotonicity(quantile_returns)

        return QuantileReturn(
            quantile_returns=quantile_returns.to_frame().T,
            long_short_return=pd.Series(long_short),
            long_short_sharpe=long_short_sharpe,
            top_quantile_return=top_returns,
            bottom_quantile_return=bottom_returns,
            monotonicity=monotonicity
        )

    def _test_monotonicity(self, quantile_returns: pd.Series) -> float:
        """
        检验分层收益的单调性

        Args:
            quantile_returns: 各层收益

        Returns:
            单调性得分（1表示完全单调递增，-1表示完全单调递减）
        """
        if len(quantile_returns) < 2:
            return 0

        # 计算相邻层收益的差值
        diffs = quantile_returns.diff().dropna()

        # 正差值的比例
        positive_ratio = (diffs > 0).mean()

        # 负差值的比例
        negative_ratio = (diffs < 0).mean()

        # 单调性得分
        if positive_ratio > negative_ratio:
            return positive_ratio
        else:
            return -negative_ratio

    def _calculate_turnover(
        self,
        factor_values: pd.Series
    ) -> Dict[str, float]:
        """
        计算换手率

        Args:
            factor_values: 因子值时间序列

        Returns:
            换手率统计
        """
        if len(factor_values) < 2:
            return {
                'mean_turnover': 0,
                'max_turnover': 0,
                'min_turnover': 0
            }

        # 计算因子值的变化率
        turnover = factor_values.pct_change().abs().dropna()

        return {
            'mean_turnover': turnover.mean(),
            'max_turnover': turnover.max(),
            'min_turnover': turnover.min()
        }

    def _generate_summary(
        self,
        factor: Factor,
        ic_analysis: ICReturn,
        quantile_analysis: QuantileReturn,
        turnover_analysis: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        生成评估摘要

        Args:
            factor: 因子
            ic_analysis: IC分析结果
            quantile_analysis: 分层分析结果
            turnover_analysis: 换手率分析

        Returns:
            摘要字典
        """
        # 因子有效性判断
        is_effective = (
            abs(ic_analysis.ic_mean) > 0.02 and
            ic_analysis.ic_ir > 0.3 and
            abs(quantile_analysis.monotonicity) > 0.5
        )

        # 因子方向
        direction = "正向" if ic_analysis.ic_mean > 0 else "反向"

        # 稳定性
        is_stable = ic_analysis.ic_positive_ratio > 0.55

        return {
            'factor_name': factor.name,
            'is_effective': is_effective,
            'direction': direction,
            'is_stable': is_stable,
            'ic_mean': round(ic_analysis.ic_mean, 4),
            'ic_ir': round(ic_analysis.ic_ir, 4),
            'rank_ic_mean': round(ic_analysis.rank_ic_mean, 4),
            'rank_ic_ir': round(ic_analysis.rank_ic_ir, 4),
            'long_short_sharpe': round(quantile_analysis.long_short_sharpe, 4),
            'monotonicity': round(quantile_analysis.monotonicity, 4),
            'mean_turnover': round(turnover_analysis['mean_turnover'], 4),
            'evaluation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def generate_report(
        self,
        evaluation: FactorEvaluation,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成评估报告

        Args:
            evaluation: 评估结果
            output_path: 输出文件路径

        Returns:
            报告文本
        """
        report = []
        report.append("=" * 60)
        report.append(f"因子评估报告: {evaluation.factor_name}")
        report.append("=" * 60)
        report.append("")

        # 摘要
        report.append("【评估摘要】")
        for key, value in evaluation.summary.items():
            report.append(f"  {key}: {value}")
        report.append("")

        # IC分析
        report.append("【IC分析】")
        report.append(f"  IC均值: {evaluation.ic_analysis.ic_mean:.4f}")
        report.append(f"  IC标准差: {evaluation.ic_analysis.ic_std:.4f}")
        report.append(f"  IC_IR: {evaluation.ic_analysis.ic_ir:.4f}")
        report.append(f"  IC正占比: {evaluation.ic_analysis.ic_positive_ratio:.2%}")
        report.append(f"  Rank IC均值: {evaluation.ic_analysis.rank_ic_mean:.4f}")
        report.append(f"  Rank IC_IR: {evaluation.ic_analysis.rank_ic_ir:.4f}")
        report.append("")

        # 分层分析
        report.append("【分层回测】")
        report.append(f"  多空夏普: {evaluation.quantile_analysis.long_short_sharpe:.4f}")
        report.append(f"  单调性: {evaluation.quantile_analysis.monotonicity:.4f}")
        report.append("")

        # 换手率
        report.append("【换手率分析】")
        for key, value in evaluation.turnover_analysis.items():
            report.append(f"  {key}: {value:.4f}")
        report.append("")

        report_text = "\n".join(report)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)

        return report_text
