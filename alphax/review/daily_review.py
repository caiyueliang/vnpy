"""
日度复盘工具

实现交易执行质量分析和盈亏分析
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import json

import numpy as np
import pandas as pd


@dataclass
class TradeExecution:
    """交易执行记录"""
    trade_id: str
    vt_symbol: str
    direction: str
    offset: str
    
    # 价格信息
    signal_price: float = 0.0           # 信号价格
    expected_price: float = 0.0         # 预期成交价格
    actual_price: float = 0.0           # 实际成交价格
    market_price: float = 0.0           # 市场价格（VWAP/收盘价）
    
    # 数量信息
    planned_volume: float = 0.0         # 计划数量
    actual_volume: float = 0.0          # 实际成交数量
    
    # 时间信息
    signal_time: Optional[datetime] = None
    order_time: Optional[datetime] = None
    trade_time: Optional[datetime] = None
    
    # 执行质量
    slippage: float = 0.0               # 滑点
    slippage_pct: float = 0.0           # 滑点百分比
    fill_rate: float = 0.0              # 成交率
    execution_time_ms: float = 0.0      # 执行时间（毫秒）


@dataclass
class ExecutionQualityMetrics:
    """执行质量指标"""
    # 滑点统计
    avg_slippage: float = 0.0
    max_slippage: float = 0.0
    slippage_std: float = 0.0
    
    # 成交率统计
    avg_fill_rate: float = 0.0
    total_planned_volume: float = 0.0
    total_actual_volume: float = 0.0
    
    # 时间统计
    avg_execution_time_ms: float = 0.0
    
    # 质量评分 (0-100)
    quality_score: float = 0.0


@dataclass
class PnLBreakdown:
    """盈亏分解"""
    # 总盈亏
    total_pnl: float = 0.0
    
    # 分解
    alpha_pnl: float = 0.0              # Alpha收益（策略选择）
    execution_pnl: float = 0.0          # 执行收益（执行质量）
    timing_pnl: float = 0.0             # 择时收益
    cost_pnl: float = 0.0               # 成本（手续费+滑点）
    
    # 按品种
    symbol_pnl: Dict[str, float] = field(default_factory=dict)
    
    # 按方向
    long_pnl: float = 0.0
    short_pnl: float = 0.0
    
    # 按开平
    open_pnl: float = 0.0
    close_pnl: float = 0.0


@dataclass
class DailyReviewReport:
    """日度复盘报告"""
    review_date: date
    
    # 交易概况
    total_trades: int = 0
    total_orders: int = 0
    filled_orders: int = 0
    cancelled_orders: int = 0
    
    # 执行质量
    execution_quality: ExecutionQualityMetrics = field(default_factory=ExecutionQualityMetrics)
    
    # 盈亏分析
    pnl_breakdown: PnLBreakdown = field(default_factory=PnLBreakdown)
    
    # 详细记录
    trade_executions: List[TradeExecution] = field(default_factory=list)
    
    # 问题与改进
    issues: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    
    # 生成时间
    generated_at: datetime = field(default_factory=datetime.now)


class DailyReviewAnalyzer:
    """
    日度复盘分析器
    
    分析每日交易执行情况，生成复盘报告
    """
    
    def __init__(self) -> None:
        """Constructor"""
        self.trade_history: List[Dict] = []
        self.order_history: List[Dict] = []
        self.price_history: Dict[str, List[Dict]] = defaultdict(list)
    
    def add_trade(self, trade: Dict) -> None:
        """
        添加交易记录
        
        Args:
            trade: 交易记录字典
        """
        self.trade_history.append(trade)
    
    def add_order(self, order: Dict) -> None:
        """
        添加订单记录
        
        Args:
            order: 订单记录字典
        """
        self.order_history.append(order)
    
    def add_price(self, vt_symbol: str, timestamp: datetime, price: float, vwap: Optional[float] = None) -> None:
        """
        添加价格数据
        
        Args:
            vt_symbol: 合约代码
            timestamp: 时间戳
            price: 价格
            vwap: VWAP价格
        """
        self.price_history[vt_symbol].append({
            "timestamp": timestamp,
            "price": price,
            "vwap": vwap or price
        })
    
    def analyze_day(self, review_date: date) -> DailyReviewReport:
        """
        分析指定日期的交易
        
        Args:
            review_date: 复盘日期
            
        Returns:
            复盘报告
        """
        report = DailyReviewReport(review_date=review_date)
        
        # 筛选当日数据
        day_trades = [
            t for t in self.trade_history
            if self._get_date(t.get("time")) == review_date
        ]
        day_orders = [
            o for o in self.order_history
            if self._get_date(o.get("create_time")) == review_date
        ]
        
        report.total_trades = len(day_trades)
        report.total_orders = len(day_orders)
        report.filled_orders = sum(1 for o in day_orders if o.get("status") == "filled")
        report.cancelled_orders = sum(1 for o in day_orders if o.get("status") == "cancelled")
        
        # 分析执行质量
        report.execution_quality = self._analyze_execution_quality(day_trades, day_orders)
        
        # 分析盈亏
        report.pnl_breakdown = self._analyze_pnl(day_trades)
        
        # 生成详细执行记录
        report.trade_executions = self._generate_trade_executions(day_trades)
        
        # 识别问题和改进点
        report.issues = self._identify_issues(report)
        report.improvements = self._suggest_improvements(report)
        
        return report
    
    def _get_date(self, timestamp: Any) -> Optional[date]:
        """从时间戳获取日期"""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, datetime):
            return timestamp.date()
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.date()
            except:
                return None
        elif isinstance(timestamp, date):
            return timestamp
        
        return None
    
    def _analyze_execution_quality(
        self,
        trades: List[Dict],
        orders: List[Dict]
    ) -> ExecutionQualityMetrics:
        """分析执行质量"""
        metrics = ExecutionQualityMetrics()
        
        if not trades:
            return metrics
        
        # 收集滑点数据
        slippages = []
        fill_rates = []
        execution_times = []
        
        total_planned = 0.0
        total_actual = 0.0
        
        for trade in trades:
            # 滑点分析
            expected = trade.get("expected_price", 0)
            actual = trade.get("price", 0)
            
            if expected > 0 and actual > 0:
                slippage = abs(actual - expected)
                slippage_pct = slippage / expected
                slippages.append(slippage_pct)
            
            # 成交率分析
            planned = trade.get("planned_volume", trade.get("volume", 0))
            actual_vol = trade.get("volume", 0)
            
            if planned > 0:
                fill_rate = actual_vol / planned
                fill_rates.append(fill_rate)
                total_planned += planned
                total_actual += actual_vol
            
            # 执行时间分析
            signal_time = trade.get("signal_time")
            trade_time = trade.get("time")
            
            if signal_time and trade_time:
                exec_time = self._calculate_time_diff_ms(signal_time, trade_time)
                if exec_time is not None:
                    execution_times.append(exec_time)
        
        # 计算统计指标
        if slippages:
            metrics.avg_slippage = np.mean(slippages)
            metrics.max_slippage = max(slippages)
            metrics.slippage_std = np.std(slippages)
        
        if fill_rates:
            metrics.avg_fill_rate = np.mean(fill_rates)
        
        metrics.total_planned_volume = total_planned
        metrics.total_actual_volume = total_actual
        
        if execution_times:
            metrics.avg_execution_time_ms = np.mean(execution_times)
        
        # 计算质量评分
        metrics.quality_score = self._calculate_quality_score(metrics)
        
        return metrics
    
    def _calculate_time_diff_ms(self, start: Any, end: Any) -> Optional[float]:
        """计算时间差（毫秒）"""
        try:
            if isinstance(start, str):
                start = datetime.fromisoformat(start.replace('Z', '+00:00'))
            if isinstance(end, str):
                end = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            diff = (end - start).total_seconds() * 1000
            return diff
        except:
            return None
    
    def _calculate_quality_score(self, metrics: ExecutionQualityMetrics) -> float:
        """计算执行质量评分"""
        score = 100.0
        
        # 滑点扣分
        if metrics.avg_slippage > 0.001:  # 0.1%
            score -= min(30, metrics.avg_slippage * 10000)
        
        # 成交率扣分
        if metrics.avg_fill_rate < 0.95:
            score -= (0.95 - metrics.avg_fill_rate) * 100
        
        # 执行时间扣分
        if metrics.avg_execution_time_ms > 1000:  # 1秒
            score -= min(20, (metrics.avg_execution_time_ms - 1000) / 100)
        
        return max(0, min(100, score))
    
    def _analyze_pnl(self, trades: List[Dict]) -> PnLBreakdown:
        """分析盈亏"""
        breakdown = PnLBreakdown()
        
        if not trades:
            return breakdown
        
        for trade in trades:
            pnl = trade.get("pnl", 0)
            breakdown.total_pnl += pnl
            
            # 按品种统计
            symbol = trade.get("vt_symbol", "unknown")
            breakdown.symbol_pnl[symbol] = breakdown.symbol_pnl.get(symbol, 0) + pnl
            
            # 按方向统计
            direction = trade.get("direction", "")
            if direction == "LONG":
                breakdown.long_pnl += pnl
            elif direction == "SHORT":
                breakdown.short_pnl += pnl
            
            # 按开平统计
            offset = trade.get("offset", "")
            if offset == "OPEN":
                breakdown.open_pnl += pnl
            elif offset == "CLOSE":
                breakdown.close_pnl += pnl
            
            # 成本分解
            commission = trade.get("commission", 0)
            slippage = trade.get("slippage", 0)
            breakdown.cost_pnl -= (commission + slippage)
        
        # Alpha收益 = 总盈亏 - 成本
        breakdown.alpha_pnl = breakdown.total_pnl - breakdown.cost_pnl
        
        return breakdown
    
    def _generate_trade_executions(self, trades: List[Dict]) -> List[TradeExecution]:
        """生成交易执行记录"""
        executions = []
        
        for trade in trades:
            execution = TradeExecution(
                trade_id=trade.get("trade_id", ""),
                vt_symbol=trade.get("vt_symbol", ""),
                direction=trade.get("direction", ""),
                offset=trade.get("offset", ""),
                signal_price=trade.get("signal_price", 0),
                expected_price=trade.get("expected_price", 0),
                actual_price=trade.get("price", 0),
                market_price=trade.get("market_price", 0),
                planned_volume=trade.get("planned_volume", trade.get("volume", 0)),
                actual_volume=trade.get("volume", 0),
                signal_time=trade.get("signal_time"),
                order_time=trade.get("order_time"),
                trade_time=trade.get("time"),
                slippage=trade.get("slippage", 0),
                slippage_pct=trade.get("slippage_pct", 0),
                fill_rate=trade.get("fill_rate", 1.0),
                execution_time_ms=trade.get("execution_time_ms", 0)
            )
            executions.append(execution)
        
        return executions
    
    def _identify_issues(self, report: DailyReviewReport) -> List[str]:
        """识别问题"""
        issues = []
        
        eq = report.execution_quality
        
        # 滑点问题
        if eq.avg_slippage > 0.002:  # 0.2%
            issues.append(f"平均滑点过高: {eq.avg_slippage:.4%}")
        
        if eq.max_slippage > 0.005:  # 0.5%
            issues.append(f"最大滑点过高: {eq.max_slippage:.4%}")
        
        # 成交率问题
        if eq.avg_fill_rate < 0.9:
            issues.append(f"成交率偏低: {eq.avg_fill_rate:.2%}")
        
        # 执行时间问题
        if eq.avg_execution_time_ms > 2000:  # 2秒
            issues.append(f"执行时间过长: {eq.avg_execution_time_ms:.0f}ms")
        
        # 盈亏问题
        pnl = report.pnl_breakdown
        if pnl.total_pnl < 0:
            issues.append(f"当日亏损: {pnl.total_pnl:,.2f}")
        
        if pnl.cost_pnl < -abs(pnl.total_pnl) * 0.2:  # 成本占比超过20%
            issues.append(f"交易成本过高: {abs(pnl.cost_pnl):,.2f}")
        
        # 订单问题
        if report.total_orders > 0:
            cancel_rate = report.cancelled_orders / report.total_orders
            if cancel_rate > 0.3:  # 撤单率超过30%
                issues.append(f"撤单率过高: {cancel_rate:.2%}")
        
        return issues
    
    def _suggest_improvements(self, report: DailyReviewReport) -> List[str]:
        """建议改进点"""
        improvements = []
        
        eq = report.execution_quality
        
        # 滑点改进建议
        if eq.avg_slippage > 0.001:
            improvements.append("考虑使用限价单替代市价单，减少滑点")
            improvements.append("优化下单时机，避开波动剧烈时段")
        
        # 成交率改进建议
        if eq.avg_fill_rate < 0.95:
            improvements.append("适当放宽价格限制，提高成交率")
            improvements.append("检查市场流动性，避免大单冲击")
        
        # 执行时间改进建议
        if eq.avg_execution_time_ms > 1000:
            improvements.append("优化系统延迟，缩短信号到下单的时间")
        
        # 成本改进建议
        pnl = report.pnl_breakdown
        if abs(pnl.cost_pnl) > abs(pnl.total_pnl) * 0.1:
            improvements.append("降低交易频率，减少手续费支出")
            improvements.append("优化订单拆分策略，降低市场冲击")
        
        # 通用建议
        if not improvements:
            improvements.append("整体执行质量良好，继续保持")
            improvements.append("关注市场微观结构变化，及时调整策略")
        
        return improvements
    
    def generate_report_text(self, report: DailyReviewReport) -> str:
        """
        生成报告文本
        
        Args:
            report: 复盘报告
            
        Returns:
            报告文本
        """
        lines = []
        
        lines.append("=" * 70)
        lines.append(f"AlphaX 日度复盘报告 - {report.review_date}")
        lines.append("=" * 70)
        lines.append("")
        
        # 交易概况
        lines.append("【交易概况】")
        lines.append(f"  总订单数: {report.total_orders}")
        lines.append(f"  成交订单: {report.filled_orders}")
        lines.append(f"  撤销订单: {report.cancelled_orders}")
        lines.append(f"  总成交笔数: {report.total_trades}")
        lines.append("")
        
        # 执行质量
        eq = report.execution_quality
        lines.append("【执行质量】")
        lines.append(f"  质量评分: {eq.quality_score:.1f}/100")
        lines.append(f"  平均滑点: {eq.avg_slippage:.4%}")
        lines.append(f"  最大滑点: {eq.max_slippage:.4%}")
        lines.append(f"  滑点标准差: {eq.slippage_std:.4%}")
        lines.append(f"  平均成交率: {eq.avg_fill_rate:.2%}")
        lines.append(f"  计划成交量: {eq.total_planned_volume:,.0f}")
        lines.append(f"  实际成交量: {eq.total_actual_volume:,.0f}")
        lines.append(f"  平均执行时间: {eq.avg_execution_time_ms:.0f}ms")
        lines.append("")
        
        # 盈亏分析
        pnl = report.pnl_breakdown
        lines.append("【盈亏分析】")
        lines.append(f"  总盈亏: {pnl.total_pnl:,.2f}")
        lines.append(f"  Alpha收益: {pnl.alpha_pnl:,.2f}")
        lines.append(f"  成本支出: {pnl.cost_pnl:,.2f}")
        lines.append(f"  多头盈亏: {pnl.long_pnl:,.2f}")
        lines.append(f"  空头盈亏: {pnl.short_pnl:,.2f}")
        
        if pnl.symbol_pnl:
            lines.append("  品种盈亏:")
            for symbol, pnl_val in sorted(pnl.symbol_pnl.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
                lines.append(f"    {symbol}: {pnl_val:,.2f}")
        lines.append("")
        
        # 问题识别
        if report.issues:
            lines.append("【问题识别】")
            for issue in report.issues:
                lines.append(f"  ⚠ {issue}")
            lines.append("")
        
        # 改进建议
        if report.improvements:
            lines.append("【改进建议】")
            for suggestion in report.improvements:
                lines.append(f"  💡 {suggestion}")
            lines.append("")
        
        # 交易明细
        if report.trade_executions:
            lines.append("【交易明细】")
            lines.append(f"{'时间':<20} {'品种':<12} {'方向':<6} {'价格':<10} {'数量':<8} {'滑点':<10}")
            lines.append("-" * 70)
            
            for te in report.trade_executions[:10]:  # 显示前10笔
                time_str = te.trade_time.strftime("%H:%M:%S") if te.trade_time else "N/A"
                lines.append(
                    f"{time_str:<20} {te.vt_symbol:<12} {te.direction:<6} "
                    f"{te.actual_price:<10.2f} {te.actual_volume:<8.0f} {te.slippage_pct:<10.4%}"
                )
            
            if len(report.trade_executions) > 10:
                lines.append(f"  ... 还有 {len(report.trade_executions) - 10} 笔交易")
            lines.append("")
        
        lines.append("=" * 70)
        lines.append(f"报告生成时间: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def export_report(self, report: DailyReviewReport, filepath: str) -> None:
        """
        导出报告到文件
        
        Args:
            report: 复盘报告
            filepath: 文件路径
        """
        # 生成文本报告
        text_report = self.generate_report_text(report)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        # 同时导出JSON格式
        json_filepath = filepath.replace('.txt', '.json')
        
        report_dict = {
            "review_date": report.review_date.isoformat(),
            "total_trades": report.total_trades,
            "total_orders": report.total_orders,
            "execution_quality": {
                "quality_score": report.execution_quality.quality_score,
                "avg_slippage": report.execution_quality.avg_slippage,
                "avg_fill_rate": report.execution_quality.avg_fill_rate,
            },
            "pnl_breakdown": {
                "total_pnl": report.pnl_breakdown.total_pnl,
                "alpha_pnl": report.pnl_breakdown.alpha_pnl,
                "cost_pnl": report.pnl_breakdown.cost_pnl,
            },
            "issues": report.issues,
            "improvements": report.improvements,
            "generated_at": report.generated_at.isoformat()
        }
        
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)


class WeeklyReviewAnalyzer:
    """
    周度复盘分析器
    
    整合多日复盘报告，进行周度分析
    """
    
    def __init__(self) -> None:
        """Constructor"""
        self.daily_reports: List[DailyReviewReport] = []
    
    def add_daily_report(self, report: DailyReviewReport) -> None:
        """添加日度报告"""
        self.daily_reports.append(report)
    
    def analyze_week(self, week_start: date) -> Dict:
        """
        分析指定周
        
        Args:
            week_start: 周开始日期
            
        Returns:
            周度分析结果
        """
        week_end = week_start + timedelta(days=6)
        
        # 筛选本周报告
        week_reports = [
            r for r in self.daily_reports
            if week_start <= r.review_date <= week_end
        ]
        
        if not week_reports:
            return {}
        
        # 汇总统计
        total_pnl = sum(r.pnl_breakdown.total_pnl for r in week_reports)
        total_trades = sum(r.total_trades for r in week_reports)
        total_orders = sum(r.total_orders for r in week_reports)
        
        # 平均执行质量
        avg_quality_score = np.mean([r.execution_quality.quality_score for r in week_reports])
        avg_slippage = np.mean([r.execution_quality.avg_slippage for r in week_reports])
        
        # 盈亏分布
        profit_days = sum(1 for r in week_reports if r.pnl_breakdown.total_pnl > 0)
        loss_days = sum(1 for r in week_reports if r.pnl_breakdown.total_pnl < 0)
        
        return {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "total_orders": total_orders,
            "avg_quality_score": avg_quality_score,
            "avg_slippage": avg_slippage,
            "profit_days": profit_days,
            "loss_days": loss_days,
            "win_rate": profit_days / len(week_reports) if week_reports else 0,
        }
