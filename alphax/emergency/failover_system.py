"""
故障转移系统

实现备用系统自动切换和状态同步
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import threading


class SystemStatus(Enum):
    """系统状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    FAILOVER = "failover"


class FailoverMode(Enum):
    """故障转移模式"""
    ACTIVE_PASSIVE = "active_passive"  # 主备模式
    ACTIVE_ACTIVE = "active_active"    # 双活模式


@dataclass
class SystemNode:
    """系统节点"""
    node_id: str
    name: str
    host: str
    port: int
    is_primary: bool = False
    status: SystemStatus = SystemStatus.HEALTHY
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FailoverConfig:
    """故障转移配置"""
    # 健康检查
    heartbeat_interval: int = 10          # 心跳间隔（秒）
    heartbeat_timeout: int = 30           # 心跳超时（秒）
    
    # 故障转移
    failover_delay: int = 5               # 故障转移延迟（秒）
    auto_failover: bool = True            # 自动故障转移
    
    # 恢复
    auto_recover: bool = False            # 自动恢复
    recover_delay: int = 300              # 恢复延迟（秒）


class FailoverSystem:
    """
    故障转移系统
    
    功能：
    1. 多节点管理
    2. 健康检查
    3. 自动故障转移
    4. 状态同步
    """
    
    def __init__(
        self,
        node_id: str,
        config: Optional[FailoverConfig] = None,
        storage_path: str = "./failover",
    ) -> None:
        """
        Constructor
        
        Args:
            node_id: 当前节点ID
            config: 故障转移配置
            storage_path: 存储路径
        """
        self.node_id = node_id
        self.config = config or FailoverConfig()
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 节点管理
        self.nodes: Dict[str, SystemNode] = {}
        self.primary_node: Optional[str] = None
        
        # 状态
        self.current_status = SystemStatus.HEALTHY
        self.failover_count = 0
        self.last_failover_time: Optional[datetime] = None
        
        # 回调
        self._on_failover_callbacks: List[Callable[[str, str], None]] = []
        self._on_status_change_callbacks: List[Callable[[SystemStatus], None]] = []
        
        # 运行状态
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def register_node(self, node: SystemNode) -> None:
        """
        注册节点
        
        Args:
            node: 系统节点
        """
        self.nodes[node.node_id] = node
        
        if node.is_primary:
            self.primary_node = node.node_id
    
    def unregister_node(self, node_id: str) -> bool:
        """
        注销节点
        
        Args:
            node_id: 节点ID
            
        Returns:
            是否成功
        """
        if node_id in self.nodes:
            del self.nodes[node_id]
            if self.primary_node == node_id:
                self.primary_node = None
            return True
        return False
    
    def update_heartbeat(self, node_id: str) -> None:
        """
        更新心跳
        
        Args:
            node_id: 节点ID
        """
        if node_id in self.nodes:
            self.nodes[node_id].last_heartbeat = datetime.now()
            self.nodes[node_id].status = SystemStatus.HEALTHY
    
    def start(self) -> None:
        """启动故障转移系统"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
    
    def stop(self) -> None:
        """停止故障转移系统"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                self._check_nodes_health()
                self._check_failover()
            except Exception as e:
                print(f"故障转移监控异常: {e}")
            
            time.sleep(self.config.heartbeat_interval)
    
    def _check_nodes_health(self) -> None:
        """检查节点健康状态"""
        now = datetime.now()
        timeout = self.config.heartbeat_timeout
        
        for node in self.nodes.values():
            if node.node_id == self.node_id:
                continue  # 跳过自己
            
            elapsed = (now - node.last_heartbeat).total_seconds()
            
            if elapsed > timeout:
                # 节点超时
                if node.status != SystemStatus.FAILED:
                    node.status = SystemStatus.FAILED
                    print(f"节点 {node.name} 已失效")
            elif elapsed > timeout / 2:
                # 节点降级
                if node.status == SystemStatus.HEALTHY:
                    node.status = SystemStatus.DEGRADED
                    print(f"节点 {node.name} 状态降级")
    
    def _check_failover(self) -> None:
        """检查是否需要故障转移"""
        if not self.config.auto_failover:
            return
        
        # 检查主节点状态
        if self.primary_node:
            primary = self.nodes.get(self.primary_node)
            
            if primary and primary.status == SystemStatus.FAILED:
                # 主节点失效，需要故障转移
                self._perform_failover()
    
    def _perform_failover(self) -> None:
        """执行故障转移"""
        # 选择新的主节点
        healthy_nodes = [
            n for n in self.nodes.values()
            if n.status == SystemStatus.HEALTHY and n.node_id != self.primary_node
        ]
        
        if not healthy_nodes:
            print("没有可用的备用节点")
            return
        
        # 选择第一个健康的节点作为新主节点
        new_primary = healthy_nodes[0]
        old_primary = self.primary_node
        
        # 更新状态
        if old_primary and old_primary in self.nodes:
            self.nodes[old_primary].is_primary = False
        
        new_primary.is_primary = True
        self.primary_node = new_primary.node_id
        
        # 更新统计
        self.failover_count += 1
        self.last_failover_time = datetime.now()
        
        # 触发回调
        for callback in self._on_failover_callbacks:
            try:
                callback(old_primary or "", new_primary.node_id)
            except Exception as e:
                print(f"故障转移回调失败: {e}")
        
        print(f"故障转移完成: {old_primary} -> {new_primary.node_id}")
    
    def on_failover(self, callback: Callable[[str, str], None]) -> None:
        """
        注册故障转移回调
        
        Args:
            callback: 回调函数(old_node_id, new_node_id)
        """
        self._on_failover_callbacks.append(callback)
    
    def on_status_change(self, callback: Callable[[SystemStatus], None]) -> None:
        """
        注册状态变更回调
        
        Args:
            callback: 回调函数(status)
        """
        self._on_status_change_callbacks.append(callback)
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "current_node": self.node_id,
            "primary_node": self.primary_node,
            "current_status": self.current_status.value,
            "failover_count": self.failover_count,
            "last_failover_time": self.last_failover_time.isoformat() if self.last_failover_time else None,
            "nodes": {
                node_id: {
                    "name": node.name,
                    "status": node.status.value,
                    "is_primary": node.is_primary,
                    "last_heartbeat": node.last_heartbeat.isoformat(),
                }
                for node_id, node in self.nodes.items()
            },
        }
    
    def manual_failover(self, target_node_id: str) -> bool:
        """
        手动故障转移
        
        Args:
            target_node_id: 目标节点ID
            
        Returns:
            是否成功
        """
        if target_node_id not in self.nodes:
            return False
        
        target = self.nodes[target_node_id]
        if target.status != SystemStatus.HEALTHY:
            return False
        
        old_primary = self.primary_node
        
        # 更新状态
        if old_primary and old_primary in self.nodes:
            self.nodes[old_primary].is_primary = False
        
        target.is_primary = True
        self.primary_node = target_node_id
        
        self.failover_count += 1
        self.last_failover_time = datetime.now()
        
        return True
