"""
综合监控面板

整合所有监控模块，提供统一的监控视图和告警管理
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import threading
import time
import json

from monitoring.alert_manager import AlertManager, AlertLevel, AlertChannel, AlertRule, AlertMessage
from monitoring.system_monitor import SystemMonitor
from monitoring.trade_monitor import TradeMonitor
from monitoring.strategy_monitor import StrategyMonitor
from monitoring.data_monitor import DataMonitor


class MonitorType(Enum):
    """监控类型"""
    SYSTEM = "system"
    TRADE = "trade"
    STRATEGY = "strategy"
    DATA = "data"
    FILL_RATE = "fill_rate"
    RISK = "risk"


@dataclass
class MonitorStatus:
    """监控状态"""
    monitor_type: MonitorType
    is_healthy: bool
    last_check: datetime
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardConfig:
    """面板配置"""
    # 检查间隔
    check_interval_seconds: int = 60
    
    # 告警阈值
    cpu_threshold: float = 80.0
    memory_threshold: float = 85.0
    disk_threshold: float = 90.0
    fill_rate_threshold: float = 0.95
    data_delay_threshold_seconds: float = 60.0
    
    # 自动告警
    auto_alert_enabled: bool = True
    alert_cooldown_minutes: int = 30


class MonitoringDashboard:
    """
    综合监控面板
    
    整合系统监控、交易监控、策略监控、数据监控，
    提供统一的监控视图和自动告警功能。
    """
    
    def __init__(self, config: Optional[DashboardConfig] = None):
        """
        Constructor
        
        Args:
            config: 面板配置
        """
        self.config = config or DashboardConfig()
        
        # 监控器
        self.system_monitor = SystemMonitor()
        self.trade_monitor = TradeMonitor()
        self.strategy_monitor = StrategyMonitor()
        self.data_monitor = DataMonitor()
        
        # 告警管理器
        self.alert_manager = AlertManager()
        
        # 状态跟踪
        self.status_history: Dict[MonitorType, List[MonitorStatus]] = defaultdict(list)
        self.current_status: Dict[MonitorType, MonitorStatus] = {}
        
        # 运行状态
        self._running: bool = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # 回调
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # 初始化告警规则
        self._init_alert_rules()
    
    def _init_alert_rules(self) -> None:
        """初始化告警规则"""
        # 系统资源告警
        self.alert_manager.add_rule(AlertRule(
            name="cpu_high",
            description=f"CPU使用率超过{self.config.cpu_threshold}%",
            level=AlertLevel.P1,
            condition=self._check_cpu_high,
            channels=[AlertChannel.EMAIL, AlertChannel.LOG],
            cooldown_minutes=self.config.alert_cooldown_minutes,
        ))
        
        self.alert_manager.add_rule(AlertRule(
            name="memory_high",
            description=f"内存使用率超过{self.config.memory_threshold}%",
            level=AlertLevel.P1,
            condition=self._check_memory_high,
            channels=[AlertChannel.EMAIL, AlertChannel.LOG],
            cooldown_minutes=self.config.alert_cooldown_minutes,
        ))
        
        self.alert_manager.add_rule(AlertRule(
            name="disk_high",
            description=f"磁盘使用率超过{self.config.disk_threshold}%",
            level=AlertLevel.P1,
            condition=self._check_disk_high,
            channels=[AlertChannel.EMAIL, AlertChannel.LOG],
            cooldown_minutes=self.config.alert_cooldown_minutes,
        ))
        
        # 交易告警
        self.alert_manager.add_rule(AlertRule(
            name="fill_rate_low",
            description=f"成交率低于{self.config.fill_rate_threshold*100:.0f}%",
            level=AlertLevel.P1,
            condition=self._check_fill_rate_low,
            channels=[AlertChannel.EMAIL, AlertChannel.LOG],
            cooldown_minutes=self.config.alert_cooldown_minutes,
        ))
        
        self.alert_manager.add_rule(AlertRule(
            name="order_rejected",
            description="订单被拒绝",
            level=AlertLevel.P2,
            condition=self._check_order_rejected,
            channels=[AlertChannel.LOG],
            cooldown_minutes=5,
        ))
        
        # 策略告警
        self.alert_manager.add_rule(AlertRule(
            name="strategy_error",
            description="策略执行异常",
            level=AlertLevel.P0,
            condition=self._check_strategy_error,
            channels=[AlertChannel.EMAIL, AlertChannel.SMS, AlertChannel.LOG],
            cooldown_minutes=10,
        ))
        
        self.alert_manager.add_rule(AlertRule(
            name="drawdown_high",
            description="策略回撤超过阈值",
            level=AlertLevel.P1,
            condition=self._check_drawdown_high,
            channels=[AlertChannel.EMAIL, AlertChannel.LOG],
            cooldown_minutes=self.config.alert_cooldown_minutes,
        ))
        
        # 数据告警
        self.alert_manager.add_rule(AlertRule(
            name="data_delay",
            description=f"数据延迟超过{self.config.data_delay_threshold_seconds}秒",
            level=AlertLevel.P1,
            condition=self._check_data_delay,
            channels=[AlertChannel.EMAIL, AlertChannel.LOG],
            cooldown_minutes=self.config.alert_cooldown_minutes,
        ))
        
        self.alert_manager.add_rule(AlertRule(
            name="data_error",
            description="数据异常",
            level=AlertLevel.P2,
            condition=self._check_data_error,
            channels=[AlertChannel.LOG],
            cooldown_minutes=5,
        ))
    
    def _check_cpu_high(self) -> bool:
        """检查CPU使用率是否过高"""
        try:
            metrics = self.system_monitor.get_metrics()
            return metrics.cpu_percent > self.config.cpu_threshold
        except:
            return False
    
    def _check_memory_high(self) -> bool:
        """检查内存使用率是否过高"""
        try:
            metrics = self.system_monitor.get_metrics()
            return metrics.memory_percent > self.config.memory_threshold
        except:
            return False
    
    def _check_disk_high(self) -> bool:
        """检查磁盘使用率是否过高"""
        try:
            metrics = self.system_monitor.get_metrics()
            return metrics.disk_percent > self.config.disk_threshold
        except:
            return False
    
    def _check_fill_rate_low(self) -> bool:
        """检查成交率是否过低"""
        try:
            summary = self.trade_monitor.get_summary()
            return summary["orders"]["fill_rate"] < self.config.fill_rate_threshold * 100
        except:
            return False
    
    def _check_order_rejected(self) -> bool:
        """检查是否有订单被拒绝"""
        try:
            summary = self.trade_monitor.get_summary()
            return summary["orders"]["rejected"] > 0
        except:
            return False
    
    def _check_strategy_error(self) -> bool:
        """检查策略是否异常"""
        try:
            summary = self.strategy_monitor.get_summary()
            return summary.get("errors", 0) > 0
        except:
            return False
    
    def _check_drawdown_high(self) -> bool:
        """检查回撤是否过高"""
        try:
            summary = self.strategy_monitor.get_summary()
            return summary.get("max_drawdown", 0) > 10.0
        except:
            return False
    
    def _check_data_delay(self) -> bool:
        """检查数据是否延迟"""
        try:
            summary = self.data_monitor.get_summary()
            return summary.get("max_delay_seconds", 0) > self.config.data_delay_threshold_seconds
        except:
            return False
    
    def _check_data_error(self) -> bool:
        """检查数据是否异常"""
        try:
            summary = self.data_monitor.get_summary()
            return summary.get("errors", 0) > 0
        except:
            return False
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)
    
    def start(self) -> None:
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
        
        # 启动告警管理器
        if self.config.auto_alert_enabled:
            self.alert_manager.start_monitoring()
        
        self._emit("monitoring_started")
    
    def stop(self) -> None:
        """停止监控"""
        self._running = False
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        self.alert_manager.stop_monitoring()
        self._emit("monitoring_stopped")
    
    def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                self._check_all_monitors()
            except Exception as e:
                print(f"监控循环出错: {e}")
            
            time.sleep(self.config.check_interval_seconds)
    
    def _check_all_monitors(self) -> None:
        """检查所有监控器"""
        now = datetime.now()
        
        # 系统监控
        try:
            sys_metrics = self.system_monitor.get_metrics()
            sys_healthy = (
                sys_metrics.cpu_percent < self.config.cpu_threshold and
                sys_metrics.memory_percent < self.config.memory_threshold and
                sys_metrics.disk_percent < self.config.disk_threshold
            )
            sys_status = MonitorStatus(
                monitor_type=MonitorType.SYSTEM,
                is_healthy=sys_healthy,
                last_check=now,
                message="系统运行正常" if sys_healthy else "系统资源使用率过高",
                metrics={
                    "cpu_percent": sys_metrics.cpu_percent,
                    "memory_percent": sys_metrics.memory_percent,
                    "disk_percent": sys_metrics.disk_percent,
                }
            )
            self._update_status(MonitorType.SYSTEM, sys_status)
        except Exception as e:
            self._update_status(MonitorType.SYSTEM, MonitorStatus(
                monitor_type=MonitorType.SYSTEM,
                is_healthy=False,
                last_check=now,
                message=f"系统监控异常: {e}",
            ))
        
        # 交易监控
        try:
            trade_summary = self.trade_monitor.get_summary()
            fill_rate = trade_summary["orders"]["fill_rate"]
            trade_healthy = fill_rate >= self.config.fill_rate_threshold * 100
            trade_status = MonitorStatus(
                monitor_type=MonitorType.TRADE,
                is_healthy=trade_healthy,
                last_check=now,
                message=f"成交率{fill_rate:.1f}%" if trade_healthy else f"成交率过低: {fill_rate:.1f}%",
                metrics=trade_summary,
            )
            self._update_status(MonitorType.TRADE, trade_status)
        except Exception as e:
            self._update_status(MonitorType.TRADE, MonitorStatus(
                monitor_type=MonitorType.TRADE,
                is_healthy=False,
                last_check=now,
                message=f"交易监控异常: {e}",
            ))
        
        # 策略监控
        try:
            strategy_summary = self.strategy_monitor.get_summary()
            strategy_healthy = strategy_summary.get("errors", 0) == 0
            strategy_status = MonitorStatus(
                monitor_type=MonitorType.STRATEGY,
                is_healthy=strategy_healthy,
                last_check=now,
                message="策略运行正常" if strategy_healthy else f"策略异常: {strategy_summary.get('errors', 0)}个错误",
                metrics=strategy_summary,
            )
            self._update_status(MonitorType.STRATEGY, strategy_status)
        except Exception as e:
            self._update_status(MonitorType.STRATEGY, MonitorStatus(
                monitor_type=MonitorType.STRATEGY,
                is_healthy=False,
                last_check=now,
                message=f"策略监控异常: {e}",
            ))
        
        # 数据监控
        try:
            data_summary = self.data_monitor.get_summary()
            data_healthy = data_summary.get("max_delay_seconds", 0) < self.config.data_delay_threshold_seconds
            data_status = MonitorStatus(
                monitor_type=MonitorType.DATA,
                is_healthy=data_healthy,
                last_check=now,
                message="数据正常" if data_healthy else f"数据延迟: {data_summary.get('max_delay_seconds', 0)}秒",
                metrics=data_summary,
            )
            self._update_status(MonitorType.DATA, data_status)
        except Exception as e:
            self._update_status(MonitorType.DATA, MonitorStatus(
                monitor_type=MonitorType.DATA,
                is_healthy=False,
                last_check=now,
                message=f"数据监控异常: {e}",
            ))
    
    def _update_status(self, monitor_type: MonitorType, status: MonitorStatus) -> None:
        """更新状态"""
        self.current_status[monitor_type] = status
        self.status_history[monitor_type].append(status)
        
        # 限制历史记录数量
        if len(self.status_history[monitor_type]) > 1000:
            self.status_history[monitor_type] = self.status_history[monitor_type][-1000:]
        
        # 触发状态变化事件
        if not status.is_healthy:
            self._emit("status_alert", status)
    
    def get_overall_status(self) -> Dict[str, Any]:
        """获取整体状态"""
        all_healthy = all(
            status.is_healthy
            for status in self.current_status.values()
        )
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_healthy": all_healthy,
            "monitors": {
                monitor_type.value: {
                    "healthy": status.is_healthy,
                    "message": status.message,
                    "last_check": status.last_check.isoformat(),
                    "metrics": status.metrics,
                }
                for monitor_type, status in self.current_status.items()
            },
        }
    
    def get_health_report(self) -> str:
        """获取健康报告"""
        status = self.get_overall_status()
        
        lines = [
            "=" * 50,
            "系统健康报告",
            "=" * 50,
            f"时间: {status['timestamp']}",
            f"整体状态: {'✓ 正常' if status['overall_healthy'] else '✗ 异常'}",
            "-" * 50,
        ]
        
        for monitor_name, monitor_data in status["monitors"].items():
            healthy = "✓" if monitor_data["healthy"] else "✗"
            lines.append(f"{healthy} {monitor_name.upper()}: {monitor_data['message']}")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标汇总"""
        return {
            "system": self.system_monitor.get_metrics() if hasattr(self.system_monitor, 'get_metrics') else {},
            "trade": self.trade_monitor.get_summary(),
            "strategy": self.strategy_monitor.get_summary(),
            "data": self.data_monitor.get_summary(),
        }
    
    def add_custom_alert_rule(
        self,
        name: str,
        description: str,
        level: AlertLevel,
        condition: Callable[[], bool],
        channels: List[AlertChannel],
        cooldown_minutes: int = 30,
    ) -> None:
        """
        添加自定义告警规则
        
        Args:
            name: 规则名称
            description: 规则描述
            level: 告警级别
            condition: 触发条件函数
            channels: 告警渠道
            cooldown_minutes: 冷却时间
        """
        rule = AlertRule(
            name=name,
            description=description,
            level=level,
            condition=condition,
            channels=channels,
            cooldown_minutes=cooldown_minutes,
        )
        self.alert_manager.add_rule(rule)
    
    def get_alert_history(
        self,
        level: Optional[AlertLevel] = None,
        limit: int = 100
    ) -> List[AlertMessage]:
        """获取告警历史"""
        return self.alert_manager.get_alert_history(level=level, limit=limit)
    
    def export_report(self, filepath: str) -> None:
        """
        导出监控报告
        
        Args:
            filepath: 文件路径
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": self.get_overall_status(),
            "metrics_summary": self.get_metrics_summary(),
            "alert_stats": self.alert_manager.get_stats(),
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)


class RealtimeMonitor:
    """
    实时监控器
    
    提供实时监控数据流
    """
    
    def __init__(self, dashboard: MonitoringDashboard):
        """
        Constructor
        
        Args:
            dashboard: 监控面板
        """
        self.dashboard = dashboard
        self._subscribers: List[Callable[[Dict], None]] = []
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
    
    def subscribe(self, callback: Callable[[Dict], None]) -> None:
        """订阅实时数据"""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[Dict], None]) -> None:
        """取消订阅"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def start(self, interval_seconds: float = 1.0) -> None:
        """启动实时推送"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._push_loop,
            args=(interval_seconds,)
        )
        self._thread.daemon = True
        self._thread.start()
    
    def stop(self) -> None:
        """停止实时推送"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _push_loop(self, interval_seconds: float) -> None:
        """推送循环"""
        while self._running:
            try:
                data = self.dashboard.get_overall_status()
                for subscriber in self._subscribers:
                    try:
                        subscriber(data)
                    except Exception as e:
                        print(f"推送数据失败: {e}")
            except Exception as e:
                print(f"获取监控数据失败: {e}")
            
            time.sleep(interval_seconds)
