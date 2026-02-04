"""
交易合规检查器

实现交易前合规检查，防范违规交易行为
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

from vnpy.trader.object import OrderData, TradeData
from vnpy.trader.constant import Direction, Exchange, Offset


class ComplianceLevel(Enum):
    """合规级别"""
    INFO = "info"         # 提示
    WARNING = "warning"   # 警告
    ERROR = "error"       # 错误（禁止）


class ComplianceType(Enum):
    """合规检查类型"""
    # 交易规则
    PRICE_LIMIT = "price_limit"           # 涨跌停检查
    TRADING_TIME = "trading_time"         # 交易时间检查
    POSITION_LIMIT = "position_limit"     # 持仓限制
    
    # 合规要求
    INSIDER_TRADING = "insider_trading"   # 内幕交易防范
    MARKET_MANIPULATION = "market_manipulation"  # 操纵市场防范
    WASH_TRADING = "wash_trading"         # 对敲交易检查
    
    # 异常交易
    ABNORMAL_ORDER = "abnormal_order"     # 异常订单
    FREQUENT_ORDER = "frequent_order"     # 频繁申报
    LARGE_ORDER = "large_order"           # 大额申报


@dataclass
class ComplianceRule:
    """合规规则"""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    compliance_type: ComplianceType = ComplianceType.PRICE_LIMIT
    level: ComplianceLevel = ComplianceLevel.ERROR
    enabled: bool = True
    
    # 检查函数
    check_fn: Optional[Callable[[Any], bool]] = None
    
    # 参数
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceResult:
    """合规检查结果"""
    passed: bool = True
    rule_id: Optional[str] = None
    rule_name: str = ""
    level: ComplianceLevel = ComplianceLevel.INFO
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "passed": self.passed,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "level": self.level.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class ComplianceChecker:
    """
    交易合规检查器
    
    功能：
    1. A股市场交易规则检查
    2. 内幕交易防范
    3. 操纵市场防范
    4. 交易所异常交易监控规则遵守
    """
    
    def __init__(self) -> None:
        """Constructor"""
        # 规则集合
        self.rules: Dict[str, ComplianceRule] = {}
        
        # 检查历史
        self.check_history: List[ComplianceResult] = []
        
        # 订单统计（用于异常交易检测）
        self.order_stats: Dict[str, Dict[str, Any]] = {}
        
        # 初始化默认规则
        self._init_default_rules()
    
    def _init_default_rules(self) -> None:
        """初始化默认规则"""
        # 1. 涨跌停检查
        self.add_rule(ComplianceRule(
            name="涨跌停保护",
            description="禁止在涨停价买入、跌停价卖出",
            compliance_type=ComplianceType.PRICE_LIMIT,
            level=ComplianceLevel.ERROR,
            check_fn=self._check_price_limit,
        ))
        
        # 2. 交易时间检查
        self.add_rule(ComplianceRule(
            name="交易时间检查",
            description="检查是否在允许的交易时间内",
            compliance_type=ComplianceType.TRADING_TIME,
            level=ComplianceLevel.ERROR,
            check_fn=self._check_trading_time,
        ))
        
        # 3. 持仓限制检查
        self.add_rule(ComplianceRule(
            name="持仓集中度检查",
            description="检查单品种持仓是否超过限制",
            compliance_type=ComplianceType.POSITION_LIMIT,
            level=ComplianceLevel.WARNING,
            check_fn=self._check_position_limit,
            params={"max_position_pct": 0.20},  # 20%
        ))
        
        # 4. 频繁申报检查
        self.add_rule(ComplianceRule(
            name="频繁申报检查",
            description="检查是否频繁申报和撤销",
            compliance_type=ComplianceType.FREQUENT_ORDER,
            level=ComplianceLevel.WARNING,
            check_fn=self._check_frequent_order,
            params={"max_orders_per_minute": 30},
        ))
        
        # 5. 大额申报检查
        self.add_rule(ComplianceRule(
            name="大额申报检查",
            description="检查大额申报是否合规",
            compliance_type=ComplianceType.LARGE_ORDER,
            level=ComplianceLevel.INFO,
            check_fn=self._check_large_order,
            params={"large_order_threshold": 1000000},  # 100万
        ))
        
        # 6. 对敲交易检查
        self.add_rule(ComplianceRule(
            name="对敲交易检查",
            description="检查是否存在对敲交易行为",
            compliance_type=ComplianceType.WASH_TRADING,
            level=ComplianceLevel.ERROR,
            check_fn=self._check_wash_trading,
        ))
    
    def add_rule(self, rule: ComplianceRule) -> None:
        """
        添加规则
        
        Args:
            rule: 合规规则
        """
        self.rules[rule.rule_id] = rule
    
    def remove_rule(self, rule_id: str) -> bool:
        """
        移除规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            是否成功
        """
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        """启用规则"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True
            return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """禁用规则"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
            return True
        return False
    
    def check_order(
        self,
        vt_symbol: str,
        direction: Direction,
        price: float,
        volume: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ComplianceResult]:
        """
        检查订单合规性
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            price: 价格
            volume: 数量
            context: 上下文信息
            
        Returns:
            检查结果列表
        """
        results = []
        context = context or {}
        
        # 构建检查数据
        check_data = {
            "vt_symbol": vt_symbol,
            "direction": direction,
            "price": price,
            "volume": volume,
            "context": context,
        }
        
        # 执行所有启用的规则
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            if rule.check_fn:
                try:
                    passed = rule.check_fn(check_data)
                    result = ComplianceResult(
                        passed=passed,
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        level=rule.level if not passed else ComplianceLevel.INFO,
                        message=f"{'通过' if passed else '未通过'}: {rule.description}",
                    )
                    results.append(result)
                    
                    if not passed and rule.level == ComplianceLevel.ERROR:
                        # 错误级别直接返回
                        break
                        
                except Exception as e:
                    results.append(ComplianceResult(
                        passed=False,
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        level=ComplianceLevel.ERROR,
                        message=f"检查异常: {e}",
                    ))
        
        # 记录历史
        self.check_history.extend(results)
        
        # 更新订单统计
        self._update_order_stats(vt_symbol, direction, volume)
        
        return results
    
    def _check_price_limit(self, data: Dict[str, Any]) -> bool:
        """检查涨跌停"""
        context = data.get("context", {})
        up_limit = context.get("up_limit", 0)
        down_limit = context.get("down_limit", 0)
        price = data["price"]
        direction = data["direction"]
        
        if direction == Direction.LONG:
            # 买入时检查是否涨停
            if up_limit > 0 and price >= up_limit:
                return False
        else:
            # 卖出时检查是否跌停
            if down_limit > 0 and price <= down_limit:
                return False
        
        return True
    
    def _check_trading_time(self, data: Dict[str, Any]) -> bool:
        """检查交易时间"""
        now = datetime.now().time()
        
        # A股交易时间
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        
        # 集合竞价时间（允许下单）
        auction_morning = time(9, 15) <= now < time(9, 25)
        auction_afternoon = time(14, 57) <= now <= time(15, 0)
        
        # 正常交易时间
        morning_session = morning_start <= now <= morning_end
        afternoon_session = afternoon_start <= now <= afternoon_end
        
        return auction_morning or auction_afternoon or morning_session or afternoon_session
    
    def _check_position_limit(self, data: Dict[str, Any]) -> bool:
        """检查持仓限制"""
        context = data.get("context", {})
        current_position = context.get("current_position", 0)
        max_position_pct = context.get("max_position_pct", 0.20)
        total_capital = context.get("total_capital", 0)
        
        if total_capital <= 0:
            return True
        
        # 计算持仓比例
        position_value = current_position * data["price"]
        position_pct = position_value / total_capital
        
        return position_pct <= max_position_pct
    
    def _check_frequent_order(self, data: Dict[str, Any]) -> bool:
        """检查频繁申报"""
        vt_symbol = data["vt_symbol"]
        max_orders = data.get("context", {}).get("max_orders_per_minute", 30)
        
        # 获取该品种的订单统计
        stats = self.order_stats.get(vt_symbol, {})
        orders_last_minute = stats.get("orders_last_minute", 0)
        
        return orders_last_minute < max_orders
    
    def _check_large_order(self, data: Dict[str, Any]) -> bool:
        """检查大额申报"""
        threshold = data.get("context", {}).get("large_order_threshold", 1000000)
        order_value = data["price"] * data["volume"]
        
        # 大额订单需要记录但不阻止
        if order_value >= threshold:
            data["context"]["is_large_order"] = True
        
        return True
    
    def _check_wash_trading(self, data: Dict[str, Any]) -> bool:
        """检查对敲交易"""
        # 简化的对敲检查：检查是否存在自买自卖
        context = data.get("context", {})
        recent_trades = context.get("recent_trades", [])
        
        vt_symbol = data["vt_symbol"]
        direction = data["direction"]
        
        # 检查最近是否有相反方向的交易
        for trade in recent_trades:
            if (trade.get("vt_symbol") == vt_symbol and
                trade.get("direction") != direction):
                # 可能存在对敲
                time_diff = (datetime.now() - trade.get("timestamp", datetime.now())).total_seconds()
                if time_diff < 60:  # 1分钟内
                    return False
        
        return True
    
    def _update_order_stats(self, vt_symbol: str, direction: Direction, volume: float) -> None:
        """更新订单统计"""
        now = datetime.now()
        
        if vt_symbol not in self.order_stats:
            self.order_stats[vt_symbol] = {
                "total_orders": 0,
                "total_volume": 0,
                "orders_last_minute": 0,
                "last_order_time": now,
            }
        
        stats = self.order_stats[vt_symbol]
        stats["total_orders"] += 1
        stats["total_volume"] += volume
        
        # 检查是否需要重置分钟计数
        if (now - stats["last_order_time"]).total_seconds() > 60:
            stats["orders_last_minute"] = 1
        else:
            stats["orders_last_minute"] += 1
        
        stats["last_order_time"] = now
    
    def is_compliant(self, results: List[ComplianceResult]) -> bool:
        """
        检查是否完全合规
        
        Args:
            results: 检查结果列表
            
        Returns:
            是否合规
        """
        return all(
            r.passed or r.level != ComplianceLevel.ERROR
            for r in results
        )
    
    def get_violations(self, results: List[ComplianceResult]) -> List[ComplianceResult]:
        """
        获取违规项
        
        Args:
            results: 检查结果列表
            
        Returns:
            违规结果列表
        """
        return [r for r in results if not r.passed]
    
    def get_check_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取检查摘要
        
        Args:
            hours: 最近小时数
            
        Returns:
            摘要信息
        """
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_checks = [c for c in self.check_history if c.timestamp >= cutoff]
        
        total = len(recent_checks)
        passed = sum(1 for c in recent_checks if c.passed)
        violations = total - passed
        
        # 按级别统计
        level_counts = {"info": 0, "warning": 0, "error": 0}
        for check in recent_checks:
            if not check.passed:
                level_counts[check.level.value] += 1
        
        return {
            "total_checks": total,
            "passed": passed,
            "violations": violations,
            "pass_rate": passed / total if total > 0 else 1.0,
            "by_level": level_counts,
        }
    
    def generate_report(self) -> str:
        """生成合规报告"""
        summary = self.get_check_summary()
        
        lines = [
            "=" * 60,
            "交易合规检查报告",
            "=" * 60,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "【检查摘要】",
            f"  总检查次数: {summary['total_checks']}",
            f"  通过次数: {summary['passed']}",
            f"  违规次数: {summary['violations']}",
            f"  通过率: {summary['pass_rate']:.1%}",
            "",
            "【违规分布】",
            f"  错误: {summary['by_level']['error']}",
            f"  警告: {summary['by_level']['warning']}",
            f"  提示: {summary['by_level']['info']}",
            "",
            "【启用规则】",
        ]
        
        for rule in self.rules.values():
            status = "启用" if rule.enabled else "禁用"
            lines.append(f"  [{status}] {rule.name}: {rule.description}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
