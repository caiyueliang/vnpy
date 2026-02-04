"""
交易所规则检查器

实现交易所特定的异常交易监控规则
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import defaultdict
import uuid

from vnpy.trader.constant import Direction


@dataclass
class AbnormalTradePattern:
    """异常交易模式"""
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    severity: str = "warning"  # info, warning, error


class ExchangeRuleChecker:
    """
    交易所规则检查器
    
    实现交易所异常交易监控规则：
    1. 虚假申报
    2. 拉抬打压
    3. 维持涨跌幅限制价格
    4. 自买自卖和互为对手方交易
    5. 严重异常波动股票申报速率异常
    """
    
    def __init__(self) -> None:
        """Constructor"""
        # 订单历史
        self.order_history: List[Dict[str, Any]] = []
        
        # 成交历史
        self.trade_history: List[Dict[str, Any]] = []
        
        # 统计信息
        self.symbol_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "orders": [],
            "cancels": [],
            "trades": [],
            "order_count": 0,
            "cancel_count": 0,
            "trade_count": 0,
        })
        
        # 检测到的异常
        self.abnormal_events: List[Dict[str, Any]] = []
    
    def record_order(
        self,
        vt_symbol: str,
        direction: Direction,
        price: float,
        volume: float,
        order_id: str,
    ) -> None:
        """
        记录订单
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            price: 价格
            volume: 数量
            order_id: 订单ID
        """
        order = {
            "timestamp": datetime.now(),
            "vt_symbol": vt_symbol,
            "direction": direction.value,
            "price": price,
            "volume": volume,
            "order_id": order_id,
            "type": "order",
        }
        
        self.order_history.append(order)
        self.symbol_stats[vt_symbol]["orders"].append(order)
        self.symbol_stats[vt_symbol]["order_count"] += 1
        
        # 限制历史记录
        if len(self.order_history) > 10000:
            self.order_history = self.order_history[-5000:]
    
    def record_cancel(
        self,
        vt_symbol: str,
        order_id: str,
        reason: str = "",
    ) -> None:
        """
        记录撤单
        
        Args:
            vt_symbol: 合约代码
            order_id: 订单ID
            reason: 撤单原因
        """
        cancel = {
            "timestamp": datetime.now(),
            "vt_symbol": vt_symbol,
            "order_id": order_id,
            "reason": reason,
            "type": "cancel",
        }
        
        self.symbol_stats[vt_symbol]["cancels"].append(cancel)
        self.symbol_stats[vt_symbol]["cancel_count"] += 1
    
    def record_trade(
        self,
        vt_symbol: str,
        direction: Direction,
        price: float,
        volume: float,
        trade_id: str,
    ) -> None:
        """
        记录成交
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            price: 价格
            volume: 数量
            trade_id: 成交ID
        """
        trade = {
            "timestamp": datetime.now(),
            "vt_symbol": vt_symbol,
            "direction": direction.value,
            "price": price,
            "volume": volume,
            "trade_id": trade_id,
            "type": "trade",
        }
        
        self.trade_history.append(trade)
        self.symbol_stats[vt_symbol]["trades"].append(trade)
        self.symbol_stats[vt_symbol]["trade_count"] += 1
        
        # 限制历史记录
        if len(self.trade_history) > 10000:
            self.trade_history = self.trade_history[-5000:]
    
    def check_abnormal_patterns(self, vt_symbol: str) -> List[Dict[str, Any]]:
        """
        检查异常交易模式
        
        Args:
            vt_symbol: 合约代码
            
        Returns:
            检测到的异常列表
        """
        abnormalities = []
        
        # 1. 检查虚假申报
        if self._check_false_declaration(vt_symbol):
            abnormalities.append({
                "pattern": "虚假申报",
                "description": "频繁申报和撤销，可能影响其他投资者决策",
                "severity": "warning",
                "timestamp": datetime.now().isoformat(),
            })
        
        # 2. 检查拉抬打压
        if self._check_manipulation(vt_symbol):
            abnormalities.append({
                "pattern": "拉抬打压",
                "description": "大笔申报、连续申报、密集申报，影响证券交易价格",
                "severity": "error",
                "timestamp": datetime.now().isoformat(),
            })
        
        # 3. 检查维持涨跌幅限制价格
        if self._check_maintain_limit(vt_symbol):
            abnormalities.append({
                "pattern": "维持涨跌幅限制价格",
                "description": "大量申报在涨跌停价格，维持该价格",
                "severity": "error",
                "timestamp": datetime.now().isoformat(),
            })
        
        # 4. 检查自买自卖
        if self._check_wash_trading(vt_symbol):
            abnormalities.append({
                "pattern": "自买自卖",
                "description": "在自己实际控制的账户之间进行证券交易",
                "severity": "error",
                "timestamp": datetime.now().isoformat(),
            })
        
        # 5. 检查申报速率异常
        if self._check_order_rate_abnormal(vt_symbol):
            abnormalities.append({
                "pattern": "申报速率异常",
                "description": "严重异常波动股票申报速率明显异常",
                "severity": "warning",
                "timestamp": datetime.now().isoformat(),
            })
        
        # 记录异常
        self.abnormal_events.extend(abnormalities)
        
        return abnormalities
    
    def _check_false_declaration(self, vt_symbol: str) -> bool:
        """检查虚假申报"""
        stats = self.symbol_stats[vt_symbol]
        
        # 最近1分钟的订单和撤单
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        
        recent_orders = [
            o for o in stats["orders"]
            if o["timestamp"] >= one_minute_ago
        ]
        recent_cancels = [
            c for c in stats["cancels"]
            if c["timestamp"] >= one_minute_ago
        ]
        
        # 如果撤单率超过80%，可能存在虚假申报
        if len(recent_orders) >= 10:
            cancel_rate = len(recent_cancels) / len(recent_orders)
            return cancel_rate > 0.8
        
        return False
    
    def _check_manipulation(self, vt_symbol: str) -> bool:
        """检查拉抬打压"""
        stats = self.symbol_stats[vt_symbol]
        
        # 最近5分钟的订单
        now = datetime.now()
        five_minutes_ago = now - timedelta(minutes=5)
        
        recent_orders = [
            o for o in stats["orders"]
            if o["timestamp"] >= five_minutes_ago
        ]
        
        # 检查是否大量申报（超过100笔）
        if len(recent_orders) >= 100:
            # 检查是否连续申报
            timestamps = [o["timestamp"] for o in recent_orders]
            timestamps.sort()
            
            # 检查是否有连续密集申报（10秒内超过20笔）
            for i in range(len(timestamps) - 20):
                time_span = (timestamps[i + 20] - timestamps[i]).total_seconds()
                if time_span <= 10:
                    return True
        
        return False
    
    def _check_maintain_limit(self, vt_symbol: str) -> bool:
        """检查维持涨跌幅限制价格"""
        # 简化的检查：检查是否在涨跌停价格大量挂单
        # 实际实现需要结合行情数据
        return False
    
    def _check_wash_trading(self, vt_symbol: str) -> bool:
        """检查自买自卖"""
        stats = self.symbol_stats[vt_symbol]
        
        # 最近1分钟的成交
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        
        recent_trades = [
            t for t in stats["trades"]
            if t["timestamp"] >= one_minute_ago
        ]
        
        # 检查是否有大量同时买卖
        buy_volume = sum(t["volume"] for t in recent_trades if t["direction"] == Direction.LONG.value)
        sell_volume = sum(t["volume"] for t in recent_trades if t["direction"] == Direction.SHORT.value)
        
        # 如果买卖量都很大且接近，可能存在对敲
        if buy_volume > 100000 and sell_volume > 100000:
            ratio = min(buy_volume, sell_volume) / max(buy_volume, sell_volume)
            return ratio > 0.9
        
        return False
    
    def _check_order_rate_abnormal(self, vt_symbol: str) -> bool:
        """检查申报速率异常"""
        stats = self.symbol_stats[vt_symbol]
        
        # 最近1分钟的订单数
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        
        recent_orders = [
            o for o in stats["orders"]
            if o["timestamp"] >= one_minute_ago
        ]
        
        # 如果超过阈值（例如每秒10笔）
        return len(recent_orders) > 600
    
    def get_abnormal_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取异常交易摘要
        
        Args:
            hours: 最近小时数
            
        Returns:
            摘要信息
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_events = [e for e in self.abnormal_events if datetime.fromisoformat(e["timestamp"]) >= cutoff]
        
        # 按类型统计
        pattern_counts = defaultdict(int)
        for event in recent_events:
            pattern_counts[event["pattern"]] += 1
        
        # 按严重程度统计
        severity_counts = {"info": 0, "warning": 0, "error": 0}
        for event in recent_events:
            severity_counts[event["severity"]] += 1
        
        return {
            "total_events": len(recent_events),
            "by_pattern": dict(pattern_counts),
            "by_severity": severity_counts,
            "recent_events": recent_events[-10:],  # 最近10条
        }
    
    def generate_report(self) -> str:
        """生成异常交易报告"""
        summary = self.get_abnormal_summary()
        
        lines = [
            "=" * 60,
            "交易所异常交易监控报告",
            "=" * 60,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "【异常统计】",
            f"  总异常事件: {summary['total_events']}",
            "",
            "【按类型分布】",
        ]
        
        for pattern, count in summary["by_pattern"].items():
            lines.append(f"  {pattern}: {count}")
        
        lines.extend([
            "",
            "【按严重程度分布】",
            f"  错误: {summary['by_severity']['error']}",
            f"  警告: {summary['by_severity']['warning']}",
            f"  提示: {summary['by_severity']['info']}",
        ])
        
        if summary["recent_events"]:
            lines.extend([
                "",
                "【最近异常事件】",
            ])
            for event in summary["recent_events"]:
                lines.append(f"  [{event['severity']}] {event['pattern']}: {event['description']}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def clear_history(self, before: Optional[datetime] = None) -> None:
        """
        清除历史记录
        
        Args:
            before: 清除该时间之前的数据
        """
        if before:
            self.order_history = [o for o in self.order_history if o["timestamp"] >= before]
            self.trade_history = [t for t in self.trade_history if t["timestamp"] >= before]
            self.abnormal_events = [
                e for e in self.abnormal_events
                if datetime.fromisoformat(e["timestamp"]) >= before
            ]
        else:
            self.order_history.clear()
            self.trade_history.clear()
            self.abnormal_events.clear()
            self.symbol_stats.clear()
