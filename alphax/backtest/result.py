"""
回测结果模块

处理回测结果分析和可视化
"""

from datetime import datetime
from typing import Any
from dataclasses import dataclass

import pandas as pd
import numpy as np


@dataclass
class BacktestResult:
    """回测结果数据类"""

    # 基础配置
    start_date: datetime
    end_date: datetime
    initial_capital: float

    # 收益指标
    total_return: float = 0.0
    annual_return: float = 0.0
    daily_return_mean: float = 0.0
    daily_return_std: float = 0.0

    # 风险指标
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    volatility: float = 0.0
    var_95: float = 0.0

    # 风险调整收益
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # 交易指标
    total_trades: int = 0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 原始数据
    daily_returns: pd.Series | None = None
    equity_curve: pd.Series | None = None
    drawdown_curve: pd.Series | None = None
    trades: list[dict] | None = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "config": {
                "start_date": self.start_date.strftime("%Y-%m-%d"),
                "end_date": self.end_date.strftime("%Y-%m-%d"),
                "initial_capital": self.initial_capital,
            },
            "returns": {
                "total_return": f"{self.total_return:.2%}",
                "annual_return": f"{self.annual_return:.2%}",
                "daily_return_mean": f"{self.daily_return_mean:.4%}",
                "daily_return_std": f"{self.daily_return_std:.4%}",
            },
            "risks": {
                "max_drawdown": f"{self.max_drawdown:.2%}",
                "max_drawdown_duration": f"{self.max_drawdown_duration}天",
                "volatility": f"{self.volatility:.2%}",
                "var_95": f"{self.var_95:.2%}",
            },
            "risk_adjusted": {
                "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
                "sortino_ratio": f"{self.sortino_ratio:.2f}",
                "calmar_ratio": f"{self.calmar_ratio:.2f}",
            },
            "trading": {
                "total_trades": self.total_trades,
                "win_rate": f"{self.win_rate:.2%}",
                "profit_loss_ratio": f"{self.profit_loss_ratio:.2f}",
                "avg_win": f"{self.avg_win:.2f}",
                "avg_loss": f"{self.avg_loss:.2f}",
                "max_consecutive_wins": self.max_consecutive_wins,
                "max_consecutive_losses": self.max_consecutive_losses,
            },
        }

    def to_dataframe(self) -> pd.DataFrame:
        """转换为DataFrame"""
        data = []
        for category, metrics in self.to_dict().items():
            if category == "config":
                continue
            for name, value in metrics.items():
                data.append({
                    "category": category,
                    "metric": name,
                    "value": value
                })
        return pd.DataFrame(data)

    def plot_equity_curve(self, save_path: str | None = None) -> Any:
        """
        绘制权益曲线

        Args:
            save_path: 保存路径

        Returns:
            plotly图表对象
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            if self.equity_curve is None or self.drawdown_curve is None:
                return None

            # 创建子图
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                subplot_titles=('权益曲线', '回撤曲线'),
                row_heights=[0.7, 0.3]
            )

            # 权益曲线
            fig.add_trace(
                go.Scatter(
                    x=self.equity_curve.index,
                    y=self.equity_curve.values,
                    mode='lines',
                    name='权益',
                    line=dict(color='blue')
                ),
                row=1, col=1
            )

            # 回撤曲线
            fig.add_trace(
                go.Scatter(
                    x=self.drawdown_curve.index,
                    y=self.drawdown_curve.values * 100,
                    mode='lines',
                    name='回撤',
                    fill='tozeroy',
                    line=dict(color='red')
                ),
                row=2, col=1
            )

            # 更新布局
            fig.update_layout(
                title='回测结果 - 权益与回撤',
                height=600,
                showlegend=True
            )

            fig.update_yaxes(title_text="权益", row=1, col=1)
            fig.update_yaxes(title_text="回撤 (%)", row=2, col=1)
            fig.update_xaxes(title_text="日期", row=2, col=1)

            if save_path:
                fig.write_html(save_path)

            return fig

        except ImportError:
            print("Plotly未安装，无法绘制图表")
            return None

    def plot_monthly_returns(self, save_path: str | None = None) -> Any:
        """
        绘制月度收益热力图

        Args:
            save_path: 保存路径

        Returns:
            plotly图表对象
        """
        try:
            import plotly.express as px

            if self.daily_returns is None:
                return None

            # 计算月度收益
            monthly_returns = self.daily_returns.resample('M').apply(
                lambda x: (1 + x).prod() - 1
            ) * 100

            # 创建透视表
            monthly_df = pd.DataFrame({
                'year': monthly_returns.index.year,
                'month': monthly_returns.index.month,
                'return': monthly_returns.values
            })
            pivot = monthly_df.pivot(index='year', columns='month', values='return')

            # 绘制热力图
            fig = px.imshow(
                pivot,
                labels=dict(x="月份", y="年份", color="收益率(%)"),
                x=[f"{i}月" for i in range(1, 13)],
                title="月度收益热力图",
                color_continuous_scale="RdYlGn",
                aspect="auto"
            )

            if save_path:
                fig.write_html(save_path)

            return fig

        except ImportError:
            print("Plotly未安装，无法绘制图表")
            return None

    def generate_report(self) -> str:
        """
        生成详细报告

        Returns:
            报告文本
        """
        d = self.to_dict()

        report = []
        report.append("=" * 60)
        report.append("AlphaX 回测详细报告")
        report.append("=" * 60)
        report.append("")

        report.append("【回测配置】")
        for key, value in d["config"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        report.append("【收益指标】")
        for key, value in d["returns"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        report.append("【风险指标】")
        for key, value in d["risks"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        report.append("【风险调整收益】")
        for key, value in d["risk_adjusted"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        report.append("【交易统计】")
        for key, value in d["trading"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        # 评估结论
        report.append("【评估结论】")
        passed_criteria = []
        failed_criteria = []

        if self.annual_return >= 0.50:
            passed_criteria.append("年化收益率 >= 50%")
        else:
            failed_criteria.append(f"年化收益率 ({self.annual_return:.2%}) < 50%")

        if self.sharpe_ratio >= 2.0:
            passed_criteria.append("夏普比率 >= 2.0")
        else:
            failed_criteria.append(f"夏普比率 ({self.sharpe_ratio:.2f}) < 2.0")

        if self.max_drawdown >= -0.15:
            passed_criteria.append("最大回撤 <= 15%")
        else:
            failed_criteria.append(f"最大回撤 ({self.max_drawdown:.2%}) > 15%")

        if self.win_rate >= 0.55:
            passed_criteria.append("胜率 >= 55%")
        else:
            failed_criteria.append(f"胜率 ({self.win_rate:.2%}) < 55%")

        if self.profit_loss_ratio >= 1.5:
            passed_criteria.append("盈亏比 >= 1.5")
        else:
            failed_criteria.append(f"盈亏比 ({self.profit_loss_ratio:.2f}) < 1.5")

        report.append(f"  通过指标 ({len(passed_criteria)}/5):")
        for c in passed_criteria:
            report.append(f"    ✓ {c}")

        if failed_criteria:
            report.append(f"  未通过指标 ({len(failed_criteria)}/5):")
            for c in failed_criteria:
                report.append(f"    ✗ {c}")

        overall_score = len(passed_criteria) / 5
        report.append("")
        report.append(f"  综合得分: {overall_score:.1%}")
        report.append(f"  评估结果: {'合格' if overall_score >= 0.8 else '不合格'}")
        report.append("")

        report.append("=" * 60)

        return "\n".join(report)

    def save_to_excel(self, filepath: str) -> bool:
        """
        保存结果到Excel

        Args:
            filepath: 文件路径

        Returns:
            是否保存成功
        """
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # 指标汇总
                self.to_dataframe().to_excel(writer, sheet_name='指标汇总', index=False)

                # 日度收益
                if self.daily_returns is not None:
                    self.daily_returns.to_frame('return').to_excel(writer, sheet_name='日度收益')

                # 权益曲线
                if self.equity_curve is not None:
                    self.equity_curve.to_frame('equity').to_excel(writer, sheet_name='权益曲线')

                # 回撤曲线
                if self.drawdown_curve is not None:
                    self.drawdown_curve.to_frame('drawdown').to_excel(writer, sheet_name='回撤曲线')

                # 交易记录
                if self.trades:
                    pd.DataFrame(self.trades).to_excel(writer, sheet_name='交易记录', index=False)

            return True

        except Exception as e:
            print(f"保存Excel失败: {e}")
            return False


def result_from_engine(engine_result: dict) -> BacktestResult:
    """
    从回测引擎结果创建BacktestResult

    Args:
        engine_result: 回测引擎返回的结果字典

    Returns:
        BacktestResult对象
    """
    perf = engine_result.get("performance", {})
    metrics = perf.get("metrics", {})
    stats = engine_result.get("statistics", {})

    # 解析百分比字符串
    def parse_pct(value):
        if isinstance(value, str) and '%' in value:
            return float(value.replace('%', '')) / 100
        return float(value) if value else 0.0

    return BacktestResult(
        start_date=datetime.strptime(engine_result["config"]["start_date"], "%Y-%m-%d"),
        end_date=datetime.strptime(engine_result["config"]["end_date"], "%Y-%m-%d"),
        initial_capital=engine_result["config"]["initial_capital"],
        total_return=parse_pct(metrics.get("total_return", "0%")),
        annual_return=parse_pct(metrics.get("annual_return", "0%")),
        max_drawdown=parse_pct(metrics.get("max_drawdown", "0%")),
        volatility=parse_pct(metrics.get("volatility", "0%")),
        sharpe_ratio=float(metrics.get("sharpe_ratio", "0")),
        win_rate=parse_pct(metrics.get("win_rate", "0%")),
        profit_loss_ratio=float(metrics.get("profit_loss_ratio", "0")),
        total_trades=stats.get("total_trades", 0),
    )
