"""
系统监控模块

监控系统资源使用情况
"""

import psutil
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque


@dataclass
class SystemMetrics:
    """系统指标数据"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    network_sent_mb: float
    network_recv_mb: float
    process_cpu_percent: float
    process_memory_mb: float


class SystemMonitor:
    """
    系统监控器

    监控系统资源使用情况，包括：
    - CPU使用率
    - 内存使用率
    - 磁盘使用率
    - 网络流量
    - 进程资源使用
    """

    def __init__(self, history_size: int = 1440) -> None:
        """
        Constructor

        Args:
            history_size: 历史数据保留数量（默认1440，约1天的分钟数据）
        """
        self.history_size = history_size
        self.metrics_history: deque = deque(maxlen=history_size)

        # 进程监控
        self.process = psutil.Process()
        self.process.cpu_percent(interval=None)  # 初始化CPU监控

        # 网络基准值
        self._last_net_io = psutil.net_io_counters()
        self._last_net_time = time.time()

        # 告警阈值
        self.thresholds = {
            "cpu_percent": 80.0,
            "memory_percent": 85.0,
            "disk_percent": 90.0,
        }

    def collect_metrics(self) -> SystemMetrics:
        """
        收集系统指标

        Returns:
            系统指标数据
        """
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)

        # 内存
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = memory.used / (1024 ** 3)
        memory_total_gb = memory.total / (1024 ** 3)

        # 磁盘
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)

        # 网络
        current_time = time.time()
        current_net_io = psutil.net_io_counters()
        time_delta = current_time - self._last_net_time

        if time_delta > 0:
            network_sent_mb = (current_net_io.bytes_sent - self._last_net_io.bytes_sent) / (1024 ** 2) / time_delta * 60
            network_recv_mb = (current_net_io.bytes_recv - self._last_net_io.bytes_recv) / (1024 ** 2) / time_delta * 60
        else:
            network_sent_mb = 0.0
            network_recv_mb = 0.0

        self._last_net_io = current_net_io
        self._last_net_time = current_time

        # 进程资源
        try:
            process_cpu = self.process.cpu_percent(interval=None)
            process_memory = self.process.memory_info().rss / (1024 ** 2)
        except psutil.NoSuchProcess:
            process_cpu = 0.0
            process_memory = 0.0

        metrics = SystemMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            disk_percent=disk_percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            network_sent_mb=network_sent_mb,
            network_recv_mb=network_recv_mb,
            process_cpu_percent=process_cpu,
            process_memory_mb=process_memory
        )

        # 添加到历史
        self.metrics_history.append(metrics)

        return metrics

    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """
        获取当前指标

        Returns:
            最新的系统指标，如果没有则返回None
        """
        if self.metrics_history:
            return self.metrics_history[-1]
        return None

    def get_metrics_history(
        self,
        minutes: int = 60
    ) -> List[SystemMetrics]:
        """
        获取历史指标

        Args:
            minutes: 返回最近多少分钟的数据

        Returns:
            系统指标列表
        """
        # 假设每分钟一个数据点
        return list(self.metrics_history)[-minutes:]

    def check_thresholds(self) -> Dict[str, bool]:
        """
        检查是否超过阈值

        Returns:
            各指标是否超过阈值的字典
        """
        metrics = self.get_current_metrics()
        if not metrics:
            return {}

        return {
            "cpu_percent": metrics.cpu_percent > self.thresholds["cpu_percent"],
            "memory_percent": metrics.memory_percent > self.thresholds["memory_percent"],
            "disk_percent": metrics.disk_percent > self.thresholds["disk_percent"],
        }

    def get_summary(self) -> Dict:
        """
        获取系统摘要

        Returns:
            系统资源使用摘要
        """
        metrics = self.get_current_metrics()
        if not metrics:
            return {}

        # 计算平均值
        if len(self.metrics_history) > 0:
            avg_cpu = sum(m.cpu_percent for m in self.metrics_history) / len(self.metrics_history)
            avg_memory = sum(m.memory_percent for m in self.metrics_history) / len(self.metrics_history)
        else:
            avg_cpu = metrics.cpu_percent
            avg_memory = metrics.memory_percent

        return {
            "current": {
                "cpu_percent": round(metrics.cpu_percent, 2),
                "memory_percent": round(metrics.memory_percent, 2),
                "memory_used_gb": round(metrics.memory_used_gb, 2),
                "disk_percent": round(metrics.disk_percent, 2),
                "disk_used_gb": round(metrics.disk_used_gb, 2),
                "network_sent_mbps": round(metrics.network_sent_mb, 2),
                "network_recv_mbps": round(metrics.network_recv_mb, 2),
            },
            "average": {
                "cpu_percent": round(avg_cpu, 2),
                "memory_percent": round(avg_memory, 2),
            },
            "process": {
                "cpu_percent": round(metrics.process_cpu_percent, 2),
                "memory_mb": round(metrics.process_memory_mb, 2),
            },
            "thresholds": self.thresholds,
            "alerts": self.check_thresholds(),
        }

    def set_threshold(self, metric: str, value: float) -> None:
        """
        设置告警阈值

        Args:
            metric: 指标名称
            value: 阈值
        """
        if metric in self.thresholds:
            self.thresholds[metric] = value

    def get_top_processes(self, n: int = 10) -> List[Dict]:
        """
        获取资源使用最高的进程

        Args:
            n: 返回进程数量

        Returns:
            进程列表
        """
        processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "cpu_percent": proc.info['cpu_percent'],
                    "memory_percent": proc.info['memory_percent'],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # 按CPU使用率排序
        processes.sort(key=lambda x: x['cpu_percent'], reverse=True)

        return processes[:n]
