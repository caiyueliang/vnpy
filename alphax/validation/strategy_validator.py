"""
策略验证器

实现系统性的策略回测验证，包括：
1. 历史回测验证
2. 样本外测试
3. 多标的验证
4. 不同市场环境验证
"""

from datetime import datetime, timedelta
from typing import Dict, List, Type, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json

import pandas as pd
import numpy as np

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange

from alphax.backtest.engine import BacktestEngine, BacktestConfig
from alphax.risk import RiskLimits
from alphax.position import PositionConfig


@dataclass
class ValidationConfig:
    """验证配置"""
    # 回测参数
    start_date: datetime
    end_date: datetime
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage: float = 0.0001

    # 验证参数
    train_period: int = 252  # 训练期（交易日）
    test_period: int = 63    # 测试期（交易日）
    n_splits: int = 5        # 交叉验证折数

    # 目标指标 (调整为年化100%，即一年一倍)
    target_annual_return: float = 1.0  # 目标年化收益率 100%
    target_sharpe: float = 2.0         # 夏普比率目标调整为2.0
    target_max_drawdown: float = 0.20  # 最大回撤20%
    target_win_rate: float = 0.55      # 胜率55%

    # 风险约束
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    position_config: PositionConfig = field(default_factory=PositionConfig)


@dataclass
class ValidationResult:
    """验证结果"""
    strategy_name: str
    symbol: str

    # 回测结果
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float

    # 统计指标
    total_trades: int
    profit_days: int
    loss_days: int
    avg_daily_return: float
    volatility: float

    # 风险评估
    var_95: float
    var_99: float
    calmar_ratio: float
    sortino_ratio: float

    # 是否通过验证
    passed: bool
    failure_reasons: List[str]

    # 详细数据
    daily_returns: List[float] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


class StrategyValidator:
    """
    策略验证器

    提供系统性的策略验证功能，确保策略在不同市场条件下的稳健性
    """

    def __init__(self, config: ValidationConfig):
        """
        构造函数

        Args:
            config: 验证配置
        """
        self.config = config
        self.results: List[ValidationResult] = []

    def validate_strategy(
        self,
        strategy_class: Type,
        strategy_params: Dict[str, Any],
        symbol: str,
        bars: List[BarData]
    ) -> ValidationResult:
        """
        验证单个策略

        Args:
            strategy_class: 策略类
            strategy_params: 策略参数
            symbol: 标的代码
            bars: 历史数据

        Returns:
            验证结果
        """
        # 创建回测配置
        backtest_config = BacktestConfig(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            commission_rate=self.config.commission_rate,
            slippage=self.config.slippage,
            risk_limits=self.config.risk_limits,
            position_config=self.config.position_config
        )

        # 创建回测引擎
        engine = BacktestEngine(backtest_config)
        engine.add_data(symbol, bars)
        engine.set_strategy(strategy_class, strategy_params)

        # 运行回测
        engine.run_backtesting()

        # 获取结果
        result_dict = engine.get_result()

        # 转换为验证结果
        return self._create_validation_result(
            strategy_class.__name__,
            symbol,
            result_dict,
            engine.evaluator.daily_returns
        )

    def walk_forward_validation(
        self,
        strategy_class: Type,
        param_grid: Dict[str, List[Any]],
        symbol: str,
        bars: List[BarData]
    ) -> Dict[str, Any]:
        """
        滚动前向验证

        将数据分为多个训练/测试周期，验证策略稳健性

        Args:
            strategy_class: 策略类
            param_grid: 参数搜索空间
            symbol: 标的代码
            bars: 历史数据

        Returns:
            验证结果字典
        """
        results = []

        # 按日期排序
        bars_sorted = sorted(bars, key=lambda x: x.datetime)

        # 计算滚动窗口
        total_days = len(bars_sorted)
        window_size = self.config.train_period + self.config.test_period

        for i in range(self.config.n_splits):
            # 计算窗口范围
            end_idx = total_days - (self.config.n_splits - i - 1) * self.config.test_period
            start_idx = max(0, end_idx - window_size)

            if end_idx - start_idx < window_size:
                continue

            train_end = start_idx + self.config.train_period

            train_bars = bars_sorted[start_idx:train_end]
            test_bars = bars_sorted[train_end:end_idx]

            # 在训练集上优化参数
            best_params = self._optimize_params(
                strategy_class, param_grid, symbol, train_bars
            )

            # 在测试集上验证
            test_result = self.validate_strategy(
                strategy_class, best_params, symbol, test_bars
            )

            results.append({
                "fold": i + 1,
                "train_start": train_bars[0].datetime,
                "train_end": train_bars[-1].datetime,
                "test_start": test_bars[0].datetime,
                "test_end": test_bars[-1].datetime,
                "params": best_params,
                "result": test_result
            })

        # 汇总结果
        return self._summarize_walk_forward_results(results)

    def multi_symbol_validation(
        self,
        strategy_class: Type,
        strategy_params: Dict[str, Any],
        symbol_data: Dict[str, List[BarData]]
    ) -> Dict[str, Any]:
        """
        多标的验证

        验证策略在不同标的上的表现一致性

        Args:
            strategy_class: 策略类
            strategy_params: 策略参数
            symbol_data: 标的代码到数据的映射

        Returns:
            验证结果字典
        """
        results = {}

        for symbol, bars in symbol_data.items():
            result = self.validate_strategy(
                strategy_class, strategy_params, symbol, bars
            )
            results[symbol] = result

        # 计算一致性指标
        returns = [r.annual_return for r in results.values()]
        sharpes = [r.sharpe_ratio for r in results.values()]
        drawdowns = [r.max_drawdown for r in results.values()]

        consistency_score = self._calculate_consistency(returns)

        return {
            "individual_results": results,
            "summary": {
                "avg_annual_return": np.mean(returns),
                "std_annual_return": np.std(returns),
                "avg_sharpe": np.mean(sharpes),
                "std_sharpe": np.std(sharpes),
                "avg_max_drawdown": np.mean(drawdowns),
                "consistency_score": consistency_score,
                "pass_rate": sum(1 for r in results.values() if r.passed) / len(results)
            }
        }

    def _optimize_params(
        self,
        strategy_class: Type,
        param_grid: Dict[str, List[Any]],
        symbol: str,
        bars: List[BarData]
    ) -> Dict[str, Any]:
        """
        参数优化（网格搜索）

        Args:
            strategy_class: 策略类
            param_grid: 参数搜索空间
            symbol: 标的代码
            bars: 训练数据

        Returns:
            最优参数
        """
        best_sharpe = -np.inf
        best_params = {}

        # 生成参数组合
        param_combinations = self._generate_param_combinations(param_grid)

        for params in param_combinations:
            try:
                result = self.validate_strategy(
                    strategy_class, params, symbol, bars
                )

                if result.sharpe_ratio > best_sharpe:
                    best_sharpe = result.sharpe_ratio
                    best_params = params
            except Exception as e:
                continue

        return best_params

    def _generate_param_combinations(
        self,
        param_grid: Dict[str, List[Any]]
    ) -> List[Dict[str, Any]]:
        """生成参数组合"""
        import itertools

        keys = list(param_grid.keys())
        values = [param_grid[k] for k in keys]

        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def _create_validation_result(
        self,
        strategy_name: str,
        symbol: str,
        result_dict: Dict,
        daily_returns: pd.Series
    ) -> ValidationResult:
        """创建验证结果"""
        perf = result_dict.get("performance", {})
        metrics = perf.get("metrics", {})
        stats = result_dict.get("statistics", {})

        # 计算额外指标
        returns_array = np.array(daily_returns.dropna())

        # VaR计算
        var_95 = np.percentile(returns_array, 5) if len(returns_array) > 0 else 0
        var_99 = np.percentile(returns_array, 1) if len(returns_array) > 0 else 0

        # Calmar比率
        annual_return = metrics.get("annual_return", 0)
        max_dd = metrics.get("max_drawdown", 0)
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

        # Sortino比率
        downside_returns = returns_array[returns_array < 0]
        downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0.001
        sortino = (np.mean(returns_array) * 252) / (downside_std * np.sqrt(252)) if downside_std > 0 else 0

        # 验证是否通过
        failure_reasons = []

        if annual_return < self.config.target_annual_return:
            failure_reasons.append(
                f"年化收益率 {annual_return:.2%} 低于目标 {self.config.target_annual_return:.2%}"
            )

        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe < self.config.target_sharpe:
            failure_reasons.append(
                f"夏普比率 {sharpe:.2f} 低于目标 {self.config.target_sharpe}"
            )

        if max_dd > self.config.target_max_drawdown:
            failure_reasons.append(
                f"最大回撤 {max_dd:.2%} 超过目标 {self.config.target_max_drawdown:.2%}"
            )

        win_rate = metrics.get("win_rate", 0)
        if win_rate < self.config.target_win_rate:
            failure_reasons.append(
                f"胜率 {win_rate:.2%} 低于目标 {self.config.target_win_rate:.2%}"
            )

        # 构建权益曲线
        equity_curve = [self.config.initial_capital]
        for ret in daily_returns.dropna():
            equity_curve.append(equity_curve[-1] * (1 + ret))

        return ValidationResult(
            strategy_name=strategy_name,
            symbol=symbol,
            total_return=metrics.get("total_return", 0),
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=metrics.get("profit_factor", 0),
            total_trades=stats.get("total_trades", 0),
            profit_days=stats.get("profit_days", 0),
            loss_days=stats.get("loss_days", 0),
            avg_daily_return=np.mean(returns_array) if len(returns_array) > 0 else 0,
            volatility=np.std(returns_array) * np.sqrt(252) if len(returns_array) > 0 else 0,
            var_95=var_95,
            var_99=var_99,
            calmar_ratio=calmar,
            sortino_ratio=sortino,
            passed=len(failure_reasons) == 0,
            failure_reasons=failure_reasons,
            daily_returns=returns_array.tolist(),
            equity_curve=equity_curve
        )

    def _summarize_walk_forward_results(
        self,
        results: List[Dict]
    ) -> Dict[str, Any]:
        """汇总滚动验证结果"""
        test_returns = [r["result"].annual_return for r in results]
        test_sharpes = [r["result"].sharpe_ratio for r in results]

        return {
            "fold_results": results,
            "summary": {
                "avg_test_return": np.mean(test_returns),
                "std_test_return": np.std(test_returns),
                "avg_test_sharpe": np.mean(test_sharpes),
                "std_test_sharpe": np.std(test_sharpes),
                "min_test_return": np.min(test_returns),
                "max_test_return": np.max(test_returns),
                "consistency": 1 - np.std(test_returns) / (np.mean(test_returns) + 0.001),
                "pass_rate": sum(1 for r in results if r["result"].passed) / len(results)
            }
        }

    def _calculate_consistency(self, returns: List[float]) -> float:
        """计算一致性得分"""
        if not returns or np.mean(returns) == 0:
            return 0

        # 变异系数的倒数
        cv = np.std(returns) / abs(np.mean(returns))
        return max(0, 1 - cv)

    def generate_report(self) -> str:
        """生成验证报告"""
        if not self.results:
            return "没有验证结果"

        report = []
        report.append("=" * 80)
        report.append("AlphaX 策略验证报告")
        report.append("=" * 80)
        report.append("")

        # 目标对比
        report.append("【目标指标】")
        report.append(f"  目标年化收益率: {self.config.target_annual_return:.2%}")
        report.append(f"  目标夏普比率: {self.config.target_sharpe:.2f}")
        report.append(f"  目标最大回撤: {self.config.target_max_drawdown:.2%}")
        report.append(f"  目标胜率: {self.config.target_win_rate:.2%}")
        report.append("")

        # 验证结果汇总
        passed_count = sum(1 for r in self.results if r.passed)
        report.append("【验证结果汇总】")
        report.append(f"  验证策略数: {len(self.results)}")
        report.append(f"  通过验证: {passed_count}")
        report.append(f"  未通过验证: {len(self.results) - passed_count}")
        report.append(f"  通过率: {passed_count / len(self.results):.2%}")
        report.append("")

        # 详细结果
        for result in self.results:
            report.append(f"【{result.strategy_name} - {result.symbol}】")
            status = "✓ 通过" if result.passed else "✗ 未通过"
            report.append(f"  状态: {status}")
            report.append(f"  年化收益率: {result.annual_return:.2%}")
            report.append(f"  夏普比率: {result.sharpe_ratio:.2f}")
            report.append(f"  最大回撤: {result.max_drawdown:.2%}")
            report.append(f"  胜率: {result.win_rate:.2%}")
            report.append(f"  交易次数: {result.total_trades}")
            report.append(f"  Calmar比率: {result.calmar_ratio:.2f}")
            report.append(f"  Sortino比率: {result.sortino_ratio:.2f}")

            if result.failure_reasons:
                report.append("  未通过原因:")
                for reason in result.failure_reasons:
                    report.append(f"    - {reason}")

            report.append("")

        report.append("=" * 80)

        return "\n".join(report)

    def export_results(self, filepath: str) -> None:
        """导出结果到JSON"""
        data = []
        for result in self.results:
            data.append({
                "strategy_name": result.strategy_name,
                "symbol": result.symbol,
                "total_return": result.total_return,
                "annual_return": result.annual_return,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "passed": result.passed,
                "failure_reasons": result.failure_reasons
            })

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
