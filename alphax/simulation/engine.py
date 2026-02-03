"""
模拟交易引擎

整合虚拟账户和撮合引擎，提供完整的模拟交易功能
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Callable, Any, Type
from collections import defaultdict

import pandas as pd

from vnpy.trader.object import BarData, TickData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset

from alphax.simulation.paper_account import PaperAccount, PaperAccountConfig
from alphax.simulation.matching_engine import MatchingEngine, MatchConfig, MatchMode
from alphax.risk import RiskManager, RiskLimits
from alphax.strategies.template import StrategyTemplate


@dataclass
class SimulationConfig:
    """模拟交易配置"""
    # 账户配置
    account_config: PaperAccountConfig = field(default_factory=PaperAccountConfig)
    
    # 撮合配置
    match_config: MatchConfig = field(default_factory=MatchConfig)
    
    # 风控配置
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    
    # 数据模式
    data_mode: str = "bar"  # "bar" 或 "tick"
    
    # 交易时间控制
    skip_first_minutes: int = 15    # 跳过开盘前15分钟
    skip_last_minutes: int = 15     # 跳过收盘前15分钟


@dataclass
class DailyTradeSummary:
    """每日交易汇总"""
    date: date
    
    # 交易统计
    total_orders: int = 0
    filled_orders: int = 0
    cancelled_orders: int = 0
    total_trades: int = 0
    
    # 盈亏
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0
    
    # 资金
    start_balance: float = 0.0
    end_balance: float = 0.0
    
    # 持仓
    positions: Dict[str, Dict] = field(default_factory=dict)


class SimulationEngine:
    """
    模拟交易引擎
    
    提供完整的模拟交易环境，包括：
    - 虚拟账户管理
    - 订单撮合
    - 风险控制
    - 绩效统计
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        """Constructor"""
        self.config = config or SimulationConfig()
        
        # 创建组件
        self.account = PaperAccount(self.config.account_config)
        self.matching_engine = MatchingEngine(self.account, self.config.match_config)
        self.risk_manager = RiskManager(self.config.risk_limits)
        
        # 策略
        self.strategy: Optional[StrategyTemplate] = None
        self.strategy_class: Optional[Type[StrategyTemplate]] = None
        self.strategy_setting: Dict = {}
        
        # 数据
        self.bars: Dict[str, List[BarData]] = {}
        self.ticks: Dict[str, List[TickData]] = {}
        self.dates: set = set()
        
        # 当前状态
        self.current_datetime: Optional[datetime] = None
        self.current_bars: Dict[str, BarData] = {}
        self.current_ticks: Dict[str, TickData] = {}
        
        # 历史记录
        self.daily_summaries: Dict[date, DailyTradeSummary] = {}
        self.trade_history: List[Dict] = []
        
        # 回调
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # 初始化
        self._setup_callbacks()
    
    def _setup_callbacks(self) -> None:
        """设置回调"""
        # 账户事件
        self.account.register_callback("trade", self._on_trade)
        self.account.register_callback("order_update", self._on_order_update)
        
        # 撮合事件
        self.matching_engine.register_callback("trade", self._on_match_trade)
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)
    
    def set_strategy(
        self,
        strategy_class: Type[StrategyTemplate],
        setting: Optional[Dict] = None
    ) -> None:
        """
        设置策略
        
        Args:
            strategy_class: 策略类
            setting: 策略参数
        """
        self.strategy_class = strategy_class
        self.strategy_setting = setting or {}
    
    def add_data(self, vt_symbol: str, bars: List[BarData]) -> None:
        """
        添加K线数据
        
        Args:
            vt_symbol: 合约代码
            bars: K线数据列表
        """
        self.bars[vt_symbol] = bars
        
        for bar in bars:
            self.dates.add(bar.datetime.date())
    
    def add_tick_data(self, vt_symbol: str, ticks: List[TickData]) -> None:
        """
        添加Tick数据
        
        Args:
            vt_symbol: 合约代码
            ticks: Tick数据列表
        """
        self.ticks[vt_symbol] = ticks
        
        for tick in ticks:
            self.dates.add(tick.datetime.date())
    
    def initialize(self) -> None:
        """初始化引擎"""
        if not self.strategy_class:
            raise ValueError("策略未设置")
        
        # 初始化风控
        self.risk_manager.set_capital(
            self.config.account_config.initial_capital,
            self.config.account_config.initial_capital
        )
        
        # 初始化策略
        vt_symbols = list(self.bars.keys()) if self.bars else list(self.ticks.keys())
        
        self.strategy = self.strategy_class(
            backtest_engine=self,
            strategy_name="simulation",
            vt_symbols=vt_symbols,
            setting=self.strategy_setting
        )
        
        # 调用策略初始化
        if hasattr(self.strategy, 'on_init'):
            self.strategy.on_init()
    
    def run_simulation(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> None:
        """
        运行模拟交易
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        """
        self.initialize()
        
        # 启动策略
        if hasattr(self.strategy, 'on_start'):
            self.strategy.on_start()
        
        # 按日期运行
        sorted_dates = sorted(self.dates)
        
        for current_date in sorted_dates:
            if start_date and current_date < start_date:
                continue
            if end_date and current_date > end_date:
                continue
            
            self._run_day(current_date)
        
        # 停止策略
        if hasattr(self.strategy, 'on_stop'):
            self.strategy.on_stop()
    
    def _run_day(self, current_date: date) -> None:
        """运行单日交易"""
        # 记录开始资金
        start_balance = self.account.balance
        
        if self.config.data_mode == "bar":
            self._run_day_bar(current_date)
        else:
            self._run_day_tick(current_date)
        
        # 创建日汇总
        summary = DailyTradeSummary(
            date=current_date,
            start_balance=start_balance,
            end_balance=self.account.balance
        )
        
        # 统计当日订单
        day_orders = [
            order for order in self.account.orders.values()
            if order.create_time.date() == current_date
        ]
        summary.total_orders = len(day_orders)
        summary.filled_orders = sum(1 for o in day_orders if o.status.value == "filled")
        summary.cancelled_orders = sum(1 for o in day_orders if o.status.value == "cancelled")
        
        # 统计当日成交
        day_trades = [
            trade for trade in self.account.trades
            if trade.trade_time.date() == current_date
        ]
        summary.total_trades = len(day_trades)
        
        # 计算盈亏
        summary.commission = self.account.total_commission
        summary.slippage = self.account.total_slippage
        summary.net_pnl = self.account.balance - start_balance
        
        # 记录持仓
        for vt_symbol, position in self.account.get_all_positions().items():
            summary.positions[vt_symbol] = {
                "volume": position.volume,
                "price": position.price,
                "pnl": position.pnl
            }
        
        self.daily_summaries[current_date] = summary
    
    def _run_day_bar(self, current_date: date) -> None:
        """使用K线数据运行单日"""
        for vt_symbol, bars in self.bars.items():
            day_bars = [b for b in bars if b.datetime.date() == current_date]
            
            for bar in day_bars:
                self.current_datetime = bar.datetime
                self.current_bars[vt_symbol] = bar
                
                # 更新撮合引擎
                self.matching_engine.on_bar(vt_symbol, bar)
                
                # 更新持仓盈亏
                if vt_symbol in self.account.positions:
                    self.account.update_position_pnl(vt_symbol, bar.close_price)
        
        # 调用策略
        if self.strategy and hasattr(self.strategy, 'on_bars'):
            self.strategy.on_bars(self.current_bars)
    
    def _run_day_tick(self, current_date: date) -> None:
        """使用Tick数据运行单日"""
        # 合并所有品种的tick
        all_ticks = []
        for vt_symbol, ticks in self.ticks.items():
            day_ticks = [t for t in ticks if t.datetime.date() == current_date]
            for tick in day_ticks:
                all_ticks.append((tick.datetime, vt_symbol, tick))
        
        # 按时间排序
        all_ticks.sort(key=lambda x: x[0])
        
        for timestamp, vt_symbol, tick in all_ticks:
            self.current_datetime = timestamp
            self.current_ticks[vt_symbol] = tick
            
            # 更新撮合引擎
            self.matching_engine.on_tick(vt_symbol, tick)
            
            # 更新持仓盈亏
            if vt_symbol in self.account.positions:
                self.account.update_position_pnl(vt_symbol, tick.last_price)
            
            # 调用策略
            if self.strategy and hasattr(self.strategy, 'on_ticks'):
                self.strategy.on_ticks(self.current_ticks)
    
    def _on_trade(self, trade) -> None:
        """成交回调"""
        self.risk_manager.update_trade(trade.to_vnpy_trade())
        
        # 记录交易历史
        self.trade_history.append({
            "time": trade.trade_time,
            "vt_symbol": trade.vt_symbol,
            "direction": trade.direction.value,
            "offset": trade.offset.value,
            "price": trade.price,
            "volume": trade.volume
        })
    
    def _on_order_update(self, order) -> None:
        """订单更新回调"""
        pass
    
    def _on_match_trade(self, trade) -> None:
        """撮合成交回调"""
        pass
    
    # ========== 交易接口 ==========
    
    def buy(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        买入开仓
        
        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        return self._send_order(vt_symbol, Direction.LONG, Offset.OPEN, price, volume)
    
    def sell(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        卖出平仓
        
        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        return self._send_order(vt_symbol, Direction.SHORT, Offset.CLOSE, price, volume)
    
    def short(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        卖出开仓
        
        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        return self._send_order(vt_symbol, Direction.SHORT, Offset.OPEN, price, volume)
    
    def cover(self, vt_symbol: str, price: float, volume: float) -> str:
        """
        买入平仓
        
        Args:
            vt_symbol: 合约代码
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        return self._send_order(vt_symbol, Direction.LONG, Offset.CLOSE, price, volume)
    
    def _send_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> str:
        """
        发送订单
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            offset: 开平
            price: 价格
            volume: 数量
            
        Returns:
            订单ID
        """
        # 风控检查
        risk_status = self.risk_manager.check_order(vt_symbol, direction, volume, price)
        if risk_status.blocked:
            print(f"订单被风控拦截: {risk_status.messages}")
            return ""
        
        # 发送订单到虚拟账户
        vt_orderid = self.account.send_order(vt_symbol, direction, offset, price, volume)
        
        if vt_orderid:
            # 获取订单并添加到撮合引擎
            order = self.account.get_order(vt_orderid)
            if order:
                self.matching_engine.add_order(order)
        
        return vt_orderid
    
    def cancel_order(self, vt_orderid: str) -> bool:
        """
        撤销订单
        
        Args:
            vt_orderid: 订单ID
            
        Returns:
            是否成功
        """
        self.matching_engine.cancel_order(vt_orderid)
        return self.account.cancel_order(vt_orderid)
    
    def cancel_all(self) -> int:
        """
        撤销所有订单
        
        Returns:
            撤销的订单数量
        """
        return self.account.cancel_all()
    
    # ========== 查询接口 ==========
    
    def get_account(self) -> Dict:
        """获取账户信息"""
        return self.account.get_statistics()
    
    def get_positions(self) -> Dict[str, Dict]:
        """获取持仓信息"""
        return {
            vt_symbol: {
                "volume": pos.volume,
                "price": pos.price,
                "pnl": pos.pnl
            }
            for vt_symbol, pos in self.account.get_all_positions().items()
        }
    
    def get_orders(self) -> List[Dict]:
        """获取订单列表"""
        return [
            {
                "vt_orderid": order.vt_orderid,
                "vt_symbol": order.vt_symbol,
                "direction": order.direction.value,
                "offset": order.offset.value,
                "price": order.price,
                "volume": order.volume,
                "traded": order.traded,
                "status": order.status.value
            }
            for order in self.account.orders.values()
        ]
    
    def get_active_orders(self) -> List[Dict]:
        """获取活跃订单"""
        return [
            {
                "vt_orderid": order.vt_orderid,
                "vt_symbol": order.vt_symbol,
                "direction": order.direction.value,
                "offset": order.offset.value,
                "price": order.price,
                "volume": order.volume,
                "traded": order.traded
            }
            for order in self.account.get_active_orders().values()
        ]
    
    def get_trades(self) -> List[Dict]:
        """获取成交列表"""
        return self.trade_history
    
    def get_daily_summary(self, date: Optional[date] = None) -> Optional[DailyTradeSummary]:
        """
        获取日汇总
        
        Args:
            date: 日期，None表示最新
            
        Returns:
            日汇总
        """
        if date:
            return self.daily_summaries.get(date)
        
        if self.daily_summaries:
            latest_date = max(self.daily_summaries.keys())
            return self.daily_summaries.get(latest_date)
        
        return None
    
    def get_all_daily_summaries(self) -> Dict[date, DailyTradeSummary]:
        """获取所有日汇总"""
        return self.daily_summaries.copy()
    
    def get_risk_report(self) -> Dict:
        """获取风险报告"""
        return self.risk_manager.get_risk_report()
    
    def generate_report(self) -> str:
        """
        生成模拟交易报告
        
        Returns:
            报告文本
        """
        stats = self.account.get_statistics()
        
        report = []
        report.append("=" * 60)
        report.append("AlphaX 模拟交易报告")
        report.append("=" * 60)
        report.append("")
        
        report.append("【账户概况】")
        report.append(f"  初始资金: {self.config.account_config.initial_capital:,.2f}")
        report.append(f"  当前资金: {stats['balance']:,.2f}")
        report.append(f"  可用资金: {stats['available']:,.2f}")
        report.append(f"  冻结资金: {stats['frozen']:,.2f}")
        report.append("")
        
        report.append("【交易统计】")
        report.append(f"  总订单数: {stats['total_orders']}")
        report.append(f"  总成交数: {stats['total_trades']}")
        report.append(f"  活跃订单: {stats['active_orders']}")
        report.append(f"  持仓数量: {stats['position_count']}")
        report.append("")
        
        report.append("【盈亏统计】")
        report.append(f"  实现盈亏: {stats['realized_pnl']:,.2f}")
        report.append(f"  浮动盈亏: {stats['unrealized_pnl']:,.2f}")
        report.append(f"  手续费: {stats['total_commission']:,.2f}")
        report.append(f"  滑点: {stats['total_slippage']:,.2f}")
        report.append(f"  净盈亏: {stats['total_pnl']:,.2f}")
        report.append(f"  收益率: {stats['total_pnl'] / self.config.account_config.initial_capital:.2%}")
        report.append("")
        
        if self.daily_summaries:
            report.append("【日度汇总】")
            for d, summary in sorted(self.daily_summaries.items())[-10:]:  # 最近10天
                report.append(f"  {d}: 订单{summary.total_orders}笔, 成交{summary.total_trades}笔, 盈亏{summary.net_pnl:,.2f}")
            report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)
