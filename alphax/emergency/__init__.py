"""
应急处理预案系统

提供系统故障和市场极端情况的应急处理机制
"""

from .emergency_handler import EmergencyHandler, EmergencyLevel, EmergencyPlan
from .failover_system import FailoverSystem

__all__ = [
    "EmergencyHandler",
    "EmergencyLevel",
    "EmergencyPlan",
    "FailoverSystem",
]
