"""
复盘报告生成器

生成每日、每周、每月、每季度复盘报告
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path
import json


class ReportGenerator:
    """
    复盘报告生成器
    
    生成各类复盘报告：
    - 每日复盘报告
    - 每周复盘报告
    - 每月复盘报告
    - 每季度复盘报告
    """
    
    def __init__(self, output_path: str = "./reports") -> None:
        """
        Constructor
        
        Args:
            output_path: 报告输出路径
        """
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
    
    def generate_daily_report(
        self,
        date: Optional[datetime] = None,
        trades: Optional[List[Dict]] = None,
        pnl: float = 0.0,
        positions: Optional[Dict] = None,
    ) -> str:
        """
        生成每日复盘报告
        
        Args:
            date: 日期
            trades: 交易列表
            pnl: 当日盈亏
            positions: 持仓信息
            
        Returns:
            报告内容
        """
        date = date or datetime.now()
        trades = trades or []
        positions = positions or {}
        
        lines = [
            "=" * 60,
            f"AlphaX 每日复盘报告 - {date.strftime('%Y-%m-%d')}",
            "=" * 60,
            "",
            "【当日盈亏】",
            f"  总盈亏: {pnl:,.2f}",
            "",
            "【交易记录】",
        ]
        
        for trade in trades:
            lines.append(f"  {trade.get('time', '')} {trade.get('symbol', '')} "
                        f"{trade.get('direction', '')} {trade.get('volume', 0)}@"
                        f"{trade.get('price', 0):.2f}")
        
        lines.extend([
            "",
            "【持仓情况】",
        ])
        
        for symbol, pos in positions.items():
            lines.append(f"  {symbol}: {pos.get('volume', 0)} 市值: {pos.get('value', 0):,.2f}")
        
        lines.extend([
            "",
            "=" * 60,
        ])
        
        report = "\n".join(lines)
        
        # 保存报告
        self._save_report(f"daily_{date.strftime('%Y%m%d')}.txt", report)
        
        return report
    
    def generate_weekly_report(
        self,
        week_start: Optional[datetime] = None,
        weekly_pnl: float = 0.0,
        weekly_return: float = 0.0,
        trades_count: int = 0,
        win_rate: float = 0.0,
    ) -> str:
        """
        生成每周复盘报告
        
        Args:
            week_start: 周开始日期
            weekly_pnl: 周盈亏
            weekly_return: 周收益率
            trades_count: 交易次数
            win_rate: 胜率
            
        Returns:
            报告内容
        """
        week_start = week_start or (datetime.now() - timedelta(days=7))
        week_end = week_start + timedelta(days=6)
        
        lines = [
            "=" * 60,
            f"AlphaX 每周复盘报告 ({week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')})",
            "=" * 60,
            "",
            "【周度绩效】",
            f"  总盈亏: {weekly_pnl:,.2f}",
            f"  收益率: {weekly_return:.2%}",
            f"  交易次数: {trades_count}",
            f"  胜率: {win_rate:.1%}",
            "",
            "=" * 60,
        ]
        
        report = "\n".join(lines)
        
        # 保存报告
        self._save_report(f"weekly_{week_start.strftime('%Y%m%d')}.txt", report)
        
        return report
    
    def generate_monthly_report(
        self,
        month: Optional[datetime] = None,
        monthly_return: float = 0.0,
        max_drawdown: float = 0.0,
        sharpe_ratio: float = 0.0,
        total_trades: int = 0,
    ) -> str:
        """
        生成每月复盘报告
        
        Args:
            month: 月份
            monthly_return: 月收益率
            max_drawdown: 最大回撤
            sharpe_ratio: 夏普比率
            total_trades: 总交易次数
            
        Returns:
            报告内容
        """
        month = month or datetime.now()
        
        lines = [
            "=" * 60,
            f"AlphaX 每月复盘报告 - {month.strftime('%Y年%m月')}",
            "=" * 60,
            "",
            "【月度绩效】",
            f"  月收益率: {monthly_return:.2%}",
            f"  最大回撤: {max_drawdown:.2%}",
            f"  夏普比率: {sharpe_ratio:.2f}",
            f"  总交易次数: {total_trades}",
            "",
            "【目标达成】",
        ]
        
        # 目标检查
        if monthly_return >= 0.21:
            lines.append(f"  ✓ 月度收益率目标达成 (21%)")
        else:
            lines.append(f"  ✗ 月度收益率目标未达成 (当前: {monthly_return:.2%})")
        
        if max_drawdown <= 0.20:
            lines.append(f"  ✓ 最大回撤控制良好 (<=20%)")
        else:
            lines.append(f"  ✗ 最大回撤超出限制 (当前: {max_drawdown:.2%})")
        
        if sharpe_ratio >= 3.0:
            lines.append(f"  ✓ 夏普比率达标 (>=3.0)")
        else:
            lines.append(f"  ✗ 夏普比率未达标 (当前: {sharpe_ratio:.2f})")
        
        lines.extend([
            "",
            "=" * 60,
        ])
        
        report = "\n".join(lines)
        
        # 保存报告
        self._save_report(f"monthly_{month.strftime('%Y%m')}.txt", report)
        
        return report
    
    def generate_quarterly_report(
        self,
        quarter: Optional[datetime] = None,
        quarterly_return: float = 0.0,
        avg_monthly_return: float = 0.0,
        strategies_performance: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        生成每季度复盘报告
        
        Args:
            quarter: 季度
            quarterly_return: 季度收益率
            avg_monthly_return: 平均月收益率
            strategies_performance: 各策略表现
            
        Returns:
            报告内容
        """
        quarter = quarter or datetime.now()
        strategies_performance = strategies_performance or {}
        
        lines = [
            "=" * 60,
            f"AlphaX 每季度复盘报告 - {quarter.year}年Q{(quarter.month-1)//3 + 1}",
            "=" * 60,
            "",
            "【季度绩效】",
            f"  季度收益率: {quarterly_return:.2%}",
            f"  平均月收益率: {avg_monthly_return:.2%}",
            "",
            "【策略表现】",
        ]
        
        for strategy, perf in strategies_performance.items():
            lines.append(f"  {strategy}: {perf:.2%}")
        
        lines.extend([
            "",
            "【目标达成】",
        ])
        
        if quarterly_return >= 1.0:
            lines.append(f"  ✓ 季度收益率目标达成 (100%)")
        else:
            lines.append(f"  ✗ 季度收益率目标未达成 (当前: {quarterly_return:.2%})")
        
        lines.extend([
            "",
            "=" * 60,
        ])
        
        report = "\n".join(lines)
        
        # 保存报告
        self._save_report(f"quarterly_{quarter.year}Q{(quarter.month-1)//3 + 1}.txt", report)
        
        return report
    
    def _save_report(self, filename: str, content: str) -> None:
        """保存报告到文件"""
        filepath = self.output_path / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
