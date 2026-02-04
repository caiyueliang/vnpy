"""
实盘交易模块

提供与券商交易系统的对接能力，包括：
- 网关适配器：统一接口对接不同券商
- 订单管理：订单生命周期管理
- 持仓管理：实时持仓跟踪
- 资金管理：账户资金和可用资金监控
"""

from .gateway_adapter import GatewayAdapter, GatewayConfig
from .order_manager import OrderManager, OrderStatusTracker
from .position_manager import PositionManager, PositionTracker
from .account_manager import AccountManager, AccountTracker
from .live_engine import LiveTradingEngine

__all__ = [
    "GatewayAdapter",
    "GatewayConfig",
    "OrderManager",
    "OrderStatusTracker",
    "PositionManager",
    "PositionTracker",
    "AccountManager",
    "AccountTracker",
    "LiveTradingEngine",
]
