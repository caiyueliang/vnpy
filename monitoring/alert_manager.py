"""
告警管理器

管理告警规则和告警发送
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time


class AlertLevel(Enum):
    """告警级别"""
    P0 = "P0"  # 紧急：电话+短信+邮件
    P1 = "P1"  # 重要：短信+邮件
    P2 = "P2"  # 一般：邮件
    P3 = "P3"  # 提示：日志记录


class AlertChannel(Enum):
    """告警渠道"""
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    WEBHOOK = "webhook"
    LOG = "log"


@dataclass
class AlertRule:
    """告警规则"""
    name: str                           # 规则名称
    description: str                    # 规则描述
    level: AlertLevel                   # 告警级别
    condition: Callable[[], bool]       # 触发条件函数
    channels: List[AlertChannel]        # 告警渠道
    cooldown_minutes: int = 30          # 冷却时间（分钟）
    enabled: bool = True                # 是否启用
    last_triggered: Optional[datetime] = None  # 上次触发时间
    trigger_count: int = 0              # 触发次数


@dataclass
class AlertMessage:
    """告警消息"""
    rule_name: str
    level: AlertLevel
    title: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AlertManager:
    """
    告警管理器

    管理告警规则、触发条件和告警发送
    """

    def __init__(self) -> None:
        """Constructor"""
        self.rules: Dict[str, AlertRule] = {}
        self.alert_history: List[AlertMessage] = []
        self.max_history: int = 1000

        # 渠道配置
        self.channel_configs: Dict[AlertChannel, Dict] = {
            AlertChannel.EMAIL: {
                "smtp_server": "",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_addr": "",
                "to_addrs": [],
            },
            AlertChannel.SMS: {
                "api_key": "",
                "api_secret": "",
                "phone_numbers": [],
            },
            AlertChannel.PHONE: {
                "api_key": "",
                "phone_numbers": [],
            },
            AlertChannel.WEBHOOK: {
                "url": "",
                "headers": {},
            },
        }

        # 运行状态
        self._running: bool = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._check_interval: int = 60  # 检查间隔（秒）

    def add_rule(self, rule: AlertRule) -> None:
        """
        添加告警规则

        Args:
            rule: 告警规则
        """
        self.rules[rule.name] = rule

    def remove_rule(self, rule_name: str) -> bool:
        """
        移除告警规则

        Args:
            rule_name: 规则名称

        Returns:
            是否成功移除
        """
        if rule_name in self.rules:
            del self.rules[rule_name]
            return True
        return False

    def enable_rule(self, rule_name: str) -> bool:
        """启用规则"""
        if rule_name in self.rules:
            self.rules[rule_name].enabled = True
            return True
        return False

    def disable_rule(self, rule_name: str) -> bool:
        """禁用规则"""
        if rule_name in self.rules:
            self.rules[rule_name].enabled = False
            return True
        return False

    def configure_channel(self, channel: AlertChannel, config: Dict) -> None:
        """
        配置告警渠道

        Args:
            channel: 告警渠道
            config: 配置字典
        """
        self.channel_configs[channel].update(config)

    def check_rules(self) -> List[AlertMessage]:
        """
        检查所有规则

        Returns:
            触发的告警消息列表
        """
        triggered_alerts = []

        for rule in self.rules.values():
            if not rule.enabled:
                continue

            # 检查冷却时间
            if rule.last_triggered:
                cooldown = timedelta(minutes=rule.cooldown_minutes)
                if datetime.now() - rule.last_triggered < cooldown:
                    continue

            # 检查触发条件
            try:
                if rule.condition():
                    alert = self._create_alert(rule)
                    triggered_alerts.append(alert)

                    # 发送告警
                    self._send_alert(alert, rule.channels)

                    # 更新规则状态
                    rule.last_triggered = datetime.now()
                    rule.trigger_count += 1

            except Exception as e:
                print(f"检查规则 {rule.name} 时出错: {e}")

        # 添加到历史
        self.alert_history.extend(triggered_alerts)
        self._trim_history()

        return triggered_alerts

    def _create_alert(self, rule: AlertRule) -> AlertMessage:
        """创建告警消息"""
        return AlertMessage(
            rule_name=rule.name,
            level=rule.level,
            title=f"[{rule.level.value}] {rule.name}",
            content=rule.description,
            metadata={
                "trigger_count": rule.trigger_count + 1,
                "cooldown_minutes": rule.cooldown_minutes,
            }
        )

    def _send_alert(
        self,
        alert: AlertMessage,
        channels: List[AlertChannel]
    ) -> None:
        """
        发送告警

        Args:
            alert: 告警消息
            channels: 告警渠道列表
        """
        for channel in channels:
            try:
                if channel == AlertChannel.EMAIL:
                    self._send_email(alert)
                elif channel == AlertChannel.SMS:
                    self._send_sms(alert)
                elif channel == AlertChannel.PHONE:
                    self._send_phone_call(alert)
                elif channel == AlertChannel.WEBHOOK:
                    self._send_webhook(alert)
                elif channel == AlertChannel.LOG:
                    self._send_log(alert)
            except Exception as e:
                print(f"发送告警到 {channel.value} 失败: {e}")

    def _send_email(self, alert: AlertMessage) -> None:
        """发送邮件告警"""
        config = self.channel_configs[AlertChannel.EMAIL]

        if not config["smtp_server"] or not config["to_addrs"]:
            return

        msg = MIMEMultipart()
        msg['From'] = config["from_addr"]
        msg['To'] = ", ".join(config["to_addrs"])
        msg['Subject'] = alert.title

        body = f"""
        告警级别: {alert.level.value}
        规则名称: {alert.rule_name}
        触发时间: {alert.timestamp.strftime("%Y-%m-%d %H:%M:%S")}

        告警内容:
        {alert.content}

        元数据:
        {json.dumps(alert.metadata, indent=2, ensure_ascii=False)}
        """

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["username"], config["password"])
            server.send_message(msg)

    def _send_sms(self, alert: AlertMessage) -> None:
        """发送短信告警"""
        # 这里集成具体的短信服务商API
        # 例如：阿里云短信、腾讯云短信等
        config = self.channel_configs[AlertChannel.SMS]

        if not config["api_key"]:
            return

        # 示例：调用短信API
        print(f"[SMS] {alert.title}: {alert.content[:50]}...")

    def _send_phone_call(self, alert: AlertMessage) -> None:
        """发送电话告警"""
        # 这里集成具体的语音电话服务商API
        # 例如：阿里云语音、腾讯云语音等
        config = self.channel_configs[AlertChannel.PHONE]

        if not config["api_key"]:
            return

        # 示例：调用语音API
        print(f"[PHONE CALL] {alert.title}: {alert.content[:50]}...")

    def _send_webhook(self, alert: AlertMessage) -> None:
        """发送Webhook告警"""
        import requests

        config = self.channel_configs[AlertChannel.WEBHOOK]

        if not config["url"]:
            return

        payload = {
            "title": alert.title,
            "level": alert.level.value,
            "content": alert.content,
            "timestamp": alert.timestamp.isoformat(),
            "metadata": alert.metadata,
        }

        try:
            response = requests.post(
                config["url"],
                json=payload,
                headers=config.get("headers", {}),
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Webhook发送失败: {e}")

    def _send_log(self, alert: AlertMessage) -> None:
        """记录日志告警"""
        log_message = f"[{alert.level.value}] {alert.rule_name}: {alert.content}"
        print(log_message)

    def _trim_history(self) -> None:
        """修剪历史记录"""
        if len(self.alert_history) > self.max_history:
            self.alert_history = self.alert_history[-self.max_history:]

    def start_monitoring(self) -> None:
        """启动监控线程"""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """停止监控线程"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                self.check_rules()
            except Exception as e:
                print(f"监控循环出错: {e}")

            time.sleep(self._check_interval)

    def get_alert_history(
        self,
        level: Optional[AlertLevel] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AlertMessage]:
        """
        获取告警历史

        Args:
            level: 告警级别过滤
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            告警消息列表
        """
        filtered = self.alert_history

        if level:
            filtered = [a for a in filtered if a.level == level]

        if start_time:
            filtered = [a for a in filtered if a.timestamp >= start_time]

        if end_time:
            filtered = [a for a in filtered if a.timestamp <= end_time]

        return filtered[-limit:]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_rules": len(self.rules),
            "enabled_rules": sum(1 for r in self.rules.values() if r.enabled),
            "total_alerts": len(self.alert_history),
            "rules_triggered": {
                name: rule.trigger_count
                for name, rule in self.rules.items()
            }
        }
