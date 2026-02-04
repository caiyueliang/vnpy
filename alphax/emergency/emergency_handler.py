"""
应急处理处理器

实现系统故障和市场极端情况的应急处理机制
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import threading
import time


class EmergencyLevel(Enum):
    """应急级别"""
    LOW = "low"           # 低 - 一般问题
    MEDIUM = "medium"     # 中 - 需要关注
    HIGH = "high"         # 高 - 需要立即处理
    CRITICAL = "critical" # 严重 - 系统级故障


class EmergencyType(Enum):
    """应急类型"""
    # 系统故障
    SYSTEM_FAILURE = "system_failure"
    NETWORK_FAILURE = "network_failure"
    DATABASE_FAILURE = "database_failure"
    
    # 交易故障
    ORDER_FAILURE = "order_failure"
    TRADE_FAILURE = "trade_failure"
    GATEWAY_FAILURE = "gateway_failure"
    
    # 市场极端情况
    MARKET_CRASH = "market_crash"
    CIRCUIT_BREAKER = "circuit_breaker"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    
    # 风控触发
    RISK_LIMIT_HIT = "risk_limit_hit"
    MARGIN_CALL = "margin_call"


@dataclass
class EmergencyPlan:
    """应急预案"""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    emergency_type: EmergencyType = EmergencyType.SYSTEM_FAILURE
    level: EmergencyLevel = EmergencyLevel.MEDIUM
    
    # 触发条件
    trigger_conditions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 处理步骤
    steps: List[Dict[str, Any]] = field(default_factory=list)
    
    # 自动执行
    auto_execute: bool = False
    
    # 通知设置
    notify_channels: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "description": self.description,
            "emergency_type": self.emergency_type.value,
            "level": self.level.value,
            "trigger_conditions": self.trigger_conditions,
            "steps": self.steps,
            "auto_execute": self.auto_execute,
            "notify_channels": self.notify_channels,
        }


@dataclass
class EmergencyEvent:
    """应急事件"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    emergency_type: EmergencyType = EmergencyType.SYSTEM_FAILURE
    level: EmergencyLevel = EmergencyLevel.MEDIUM
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    
    # 处理状态
    status: str = "pending"  # pending, processing, resolved, failed
    resolved_at: Optional[datetime] = None
    resolution: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "emergency_type": self.emergency_type.value,
            "level": self.level.value,
            "description": self.description,
            "context": self.context,
            "status": self.status,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution,
        }


class EmergencyHandler:
    """
    应急处理器
    
    功能：
    1. 应急预案管理
    2. 应急事件处理
    3. 自动故障转移
    4. 持仓状态确认
    5. 手动平仓机制
    """
    
    def __init__(self, storage_path: str = "./emergency") -> None:
        """
        Constructor
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 应急预案
        self.plans: Dict[str, EmergencyPlan] = {}
        
        # 事件历史
        self.events: List[EmergencyEvent] = []
        
        # 处理函数映射
        self._handlers: Dict[EmergencyType, Callable[[EmergencyEvent], bool]] = {}
        
        # 回调
        self._on_event_callbacks: List[Callable[[EmergencyEvent], None]] = []
        
        # 锁
        self._lock = threading.Lock()
        
        # 初始化默认预案
        self._init_default_plans()
        
        # 加载历史
        self._load_events()
    
    def _init_default_plans(self) -> None:
        """初始化默认预案"""
        # 1. 系统故障预案
        self.add_plan(EmergencyPlan(
            name="系统故障应急预案",
            description="处理系统级故障，包括内存不足、CPU过载等",
            emergency_type=EmergencyType.SYSTEM_FAILURE,
            level=EmergencyLevel.HIGH,
            steps=[
                {"action": "log_error", "params": {"message": "系统故障 detected"}},
                {"action": "notify", "params": {"level": "high"}},
                {"action": "pause_strategies", "params": {}},
                {"action": "save_state", "params": {}},
            ],
            notify_channels=["email", "sms"],
        ))
        
        # 2. 网络故障预案
        self.add_plan(EmergencyPlan(
            name="网络故障应急预案",
            description="处理网络连接中断",
            emergency_type=EmergencyType.NETWORK_FAILURE,
            level=EmergencyLevel.HIGH,
            steps=[
                {"action": "log_error", "params": {"message": "网络故障 detected"}},
                {"action": "notify", "params": {"level": "high"}},
                {"action": "wait", "params": {"seconds": 30}},
                {"action": "retry_connection", "params": {"max_retries": 3}},
            ],
            notify_channels=["email"],
        ))
        
        # 3. 市场熔断预案
        self.add_plan(EmergencyPlan(
            name="市场熔断应急预案",
            description="处理市场熔断情况",
            emergency_type=EmergencyType.CIRCUIT_BREAKER,
            level=EmergencyLevel.CRITICAL,
            auto_execute=True,
            steps=[
                {"action": "log_error", "params": {"message": "市场熔断 triggered"}},
                {"action": "notify", "params": {"level": "critical"}},
                {"action": "pause_all_trading", "params": {}},
                {"action": "confirm_positions", "params": {}},
                {"action": "wait_for_market_open", "params": {}},
            ],
            notify_channels=["email", "sms", "phone"],
        ))
        
        # 4. 风控限制预案
        self.add_plan(EmergencyPlan(
            name="风控限制应急预案",
            description="处理触发风控限制的情况",
            emergency_type=EmergencyType.RISK_LIMIT_HIT,
            level=EmergencyLevel.HIGH,
            auto_execute=True,
            steps=[
                {"action": "log_error", "params": {"message": "风控限制 triggered"}},
                {"action": "notify", "params": {"level": "high"}},
                {"action": "reduce_positions", "params": {"target_pct": 0.5}},
                {"action": "pause_strategies", "params": {"duration_hours": 1}},
            ],
            notify_channels=["email", "sms"],
        ))
    
    def add_plan(self, plan: EmergencyPlan) -> None:
        """
        添加应急预案
        
        Args:
            plan: 应急预案
        """
        self.plans[plan.plan_id] = plan
    
    def remove_plan(self, plan_id: str) -> bool:
        """
        移除应急预案
        
        Args:
            plan_id: 预案ID
            
        Returns:
            是否成功
        """
        if plan_id in self.plans:
            del self.plans[plan_id]
            return True
        return False
    
    def register_handler(
        self,
        emergency_type: EmergencyType,
        handler: Callable[[EmergencyEvent], bool]
    ) -> None:
        """
        注册处理函数
        
        Args:
            emergency_type: 应急类型
            handler: 处理函数
        """
        self._handlers[emergency_type] = handler
    
    def trigger_event(
        self,
        emergency_type: EmergencyType,
        level: EmergencyLevel,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> EmergencyEvent:
        """
        触发应急事件
        
        Args:
            emergency_type: 应急类型
            level: 级别
            description: 描述
            context: 上下文
            
        Returns:
            应急事件
        """
        event = EmergencyEvent(
            emergency_type=emergency_type,
            level=level,
            description=description,
            context=context or {},
        )
        
        with self._lock:
            self.events.append(event)
        
        # 触发回调
        for callback in self._on_event_callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"应急事件回调失败: {e}")
        
        # 查找并执行预案
        self._execute_plan(event)
        
        # 保存
        self._save_events()
        
        return event
    
    def _execute_plan(self, event: EmergencyEvent) -> bool:
        """
        执行应急预案
        
        Args:
            event: 应急事件
            
        Returns:
            是否成功
        """
        # 查找匹配的预案
        matching_plans = [
            p for p in self.plans.values()
            if p.emergency_type == event.emergency_type and p.level == event.level
        ]
        
        if not matching_plans:
            return False
        
        plan = matching_plans[0]
        
        # 更新状态
        event.status = "processing"
        
        # 执行步骤
        for step in plan.steps:
            action = step.get("action")
            params = step.get("params", {})
            
            try:
                self._execute_action(action, params, event)
            except Exception as e:
                print(f"执行应急步骤失败: {action}, 错误: {e}")
                event.status = "failed"
                return False
        
        # 标记为已解决
        event.status = "resolved"
        event.resolved_at = datetime.now()
        event.resolution = f"执行预案: {plan.name}"
        
        return True
    
    def _execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        event: EmergencyEvent
    ) -> None:
        """执行具体动作"""
        if action == "log_error":
            print(f"[ERROR] {params.get('message', '')}")
        
        elif action == "notify":
            level = params.get("level", "info")
            print(f"[NOTIFY] 级别: {level}, 事件: {event.description}")
        
        elif action == "wait":
            seconds = params.get("seconds", 10)
            time.sleep(seconds)
        
        elif action == "pause_strategies":
            print("[ACTION] 暂停所有策略")
        
        elif action == "pause_all_trading":
            print("[ACTION] 暂停所有交易")
        
        elif action == "reduce_positions":
            target_pct = params.get("target_pct", 0.5)
            print(f"[ACTION] 减仓至 {target_pct:.0%}")
        
        elif action == "confirm_positions":
            print("[ACTION] 确认持仓状态")
        
        elif action == "save_state":
            print("[ACTION] 保存系统状态")
        
        elif action == "retry_connection":
            max_retries = params.get("max_retries", 3)
            print(f"[ACTION] 重试连接，最大次数: {max_retries}")
    
    def on_event(self, callback: Callable[[EmergencyEvent], None]) -> None:
        """
        注册事件回调
        
        Args:
            callback: 回调函数
        """
        self._on_event_callbacks.append(callback)
    
    def resolve_event(
        self,
        event_id: str,
        resolution: str,
    ) -> bool:
        """
        手动解决事件
        
        Args:
            event_id: 事件ID
            resolution: 解决方案
            
        Returns:
            是否成功
        """
        for event in self.events:
            if event.event_id == event_id:
                event.status = "resolved"
                event.resolved_at = datetime.now()
                event.resolution = resolution
                self._save_events()
                return True
        return False
    
    def get_pending_events(self) -> List[EmergencyEvent]:
        """获取待处理事件"""
        return [e for e in self.events if e.status == "pending"]
    
    def get_event_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取事件统计
        
        Args:
            days: 天数
            
        Returns:
            统计信息
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent_events = [e for e in self.events if e.timestamp >= cutoff]
        
        # 按类型统计
        type_counts = {t.value: 0 for t in EmergencyType}
        for event in recent_events:
            type_counts[event.emergency_type.value] += 1
        
        # 按级别统计
        level_counts = {l.value: 0 for l in EmergencyLevel}
        for event in recent_events:
            level_counts[event.level.value] += 1
        
        # 按状态统计
        status_counts = {"pending": 0, "processing": 0, "resolved": 0, "failed": 0}
        for event in recent_events:
            status_counts[event.status] += 1
        
        return {
            "total_events": len(recent_events),
            "by_type": type_counts,
            "by_level": level_counts,
            "by_status": status_counts,
            "resolution_rate": (
                status_counts["resolved"] / len(recent_events)
                if recent_events else 1.0
            ),
        }
    
    def _save_events(self) -> None:
        """保存事件历史"""
        events_file = self.storage_path / "emergency_events.json"
        try:
            data = [e.to_dict() for e in self.events[-1000:]]
            with open(events_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"保存应急事件失败: {e}")
    
    def _load_events(self) -> None:
        """加载事件历史"""
        events_file = self.storage_path / "emergency_events.json"
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for event_data in data:
                        event = EmergencyEvent(
                            event_id=event_data["event_id"],
                            timestamp=datetime.fromisoformat(event_data["timestamp"]),
                            emergency_type=EmergencyType(event_data["emergency_type"]),
                            level=EmergencyLevel(event_data["level"]),
                            description=event_data["description"],
                            context=event_data.get("context", {}),
                            status=event_data["status"],
                            resolved_at=datetime.fromisoformat(event_data["resolved_at"]) if event_data.get("resolved_at") else None,
                            resolution=event_data.get("resolution", ""),
                        )
                        self.events.append(event)
            except Exception as e:
                print(f"加载应急事件失败: {e}")
    
    def generate_report(self) -> str:
        """生成应急处理报告"""
        stats = self.get_event_stats()
        pending = self.get_pending_events()
        
        lines = [
            "=" * 60,
            "应急处理预案报告",
            "=" * 60,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "【事件统计】",
            f"  总事件数: {stats['total_events']}",
            f"  解决率: {stats['resolution_rate']:.1%}",
            "",
            "【按级别分布】",
        ]
        
        for level, count in stats["by_level"].items():
            lines.append(f"  {level}: {count}")
        
        lines.extend([
            "",
            "【按状态分布】",
            f"  待处理: {stats['by_status']['pending']}",
            f"  处理中: {stats['by_status']['processing']}",
            f"  已解决: {stats['by_status']['resolved']}",
            f"  失败: {stats['by_status']['failed']}",
        ])
        
        if pending:
            lines.extend([
                "",
                "【待处理事件】",
            ])
            for event in pending:
                lines.append(f"  [{event.level.value}] {event.emergency_type.value}: {event.description}")
        
        lines.extend([
            "",
            "【可用预案】",
        ])
        for plan in self.plans.values():
            lines.append(f"  {plan.name} ({plan.emergency_type.value})")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
