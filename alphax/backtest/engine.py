"""
回测引擎

实现历史数据回测功能
"""

from datetime import datetime, date
from typing import Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import numpy as np

from vnpy.trader.object import BarData, TickData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset, Status, Interval
from vnpy.trader.utility import extract_vt_symbol

from alphax.risk import RiskManager, RiskLimits
from alphax.position import PositionManager, PositionConfig
from alphax.evaluation import PerformanceEvaluator


@dataclass
class BacktestConfig:
    """回测配置"""
    # 基础配置
    start_date: datetime
    end_date: datetime
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003       # 手续费率 0.03%
    slippage: float = 0.0001              # 滑点 0.01%
    size: int = 1                         # 合约乘数
    pricetick: float = 0.01               # 最小价格变动

    # 风控配置
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    position_config: PositionConfig = field(default_factory=PositionConfig)

    # 回测模式
    mode: str = "bar"                     # "bar" 或 "tick"


@dataclass
class DailyResult:
    """每日回测结果"""
    date: date
    close_price: float = 0.0
    pre_close: float = 0.0

    trade_count: int = 0
    turnover: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0

    trading_pnl: float = 0.0
    holding_pnl: float = 0.0
    total_pnl: float = 0.0

    net_pnl: float = 0.0
    balance: float = 0.0


class BacktestEngine:
    """
    回测引擎

    实现基于历史数据的策略回测
    """

    def __init__(self, config: BacktestConfig) -> None:
        """Constructor"""
        self.config: BacktestConfig = config

        # 数据
        self.bars: dict[str, list[BarData]] = {}
        self.ticks: dict[str, list[TickData]] = {}
        self.dates: set[date] = set()

        # 策略
        self.strategy: Any = None
        self.strategy_class: type | None = None
        self.strategy_setting: dict = {}

        # 撮合相关
        self.datetime: datetime = config.start_date
        self.current_bars: dict[str, BarData] = {}
        self.current_ticks: dict[str, TickData] = {}

        # 账户
        self.balance: float = config.initial_capital
        self.available: float = config.initial_capital
        self.frozen: float = 0.0

        # 成交记录
        self.trades: list[TradeData] = []
        self.orders: list[OrderData] = []
        self.daily_results: dict[date, DailyResult] = {}

        # 风控和仓位管理
        self.risk_manager = RiskManager(config.risk_limits)
        self.position_manager = PositionManager(config.position_config)

        # 绩效评估
        self.evaluator = PerformanceEvaluator()

        # 回调函数
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)

        # 统计
        self._trade_count: int = 0
        self._order_count: int = 0

    def add_data(self, vt_symbol: str, bars: list[BarData]) -> None:
        """
        添加K线数据

        Args:
            vt_symbol: 合约代码
            bars: K线数据列表
        """
        self.bars[vt_symbol] = bars

        # 收集所有日期
        for bar in bars:
            self.dates.add(bar.datetime.date())

    def set_strategy(self, strategy_class: type, setting: dict = None) -> None:
        """
        设置策略

        Args:
            strategy_class: 策略类
            setting: 策略参数
        """
        self.strategy_class = strategy_class
        self.strategy_setting = setting or {}

    def register_callback(self, event: str, callback: Callable) -> None:
        """
        注册回调函数

        Args:
            event: 事件类型
            callback: 回调函数
        """
        self._callbacks[event].append(callback)

    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发事件"""
        for callback in self._callbacks.get(event, []):
            callback(*args, **kwargs)

    def run_backtesting(self) -> None:
        """运行回测"""
        if not self.strategy_class:
            raise ValueError("策略未设置")

        if not self.bars:
            raise ValueError("数据未加载")

        # 初始化风控和仓位管理
        self.risk_manager.set_capital(self.config.initial_capital, self.config.initial_capital)
        self.position_manager.set_portfolio_value(self.config.initial_capital, self.config.initial_capital)

        # 初始化策略
        self.strategy = self.strategy_class(
            backtest_engine=self,
            strategy_name="backtest",
            vt_symbols=list(self.bars.keys()),
            setting=self.strategy_setting
        )

        # 按日期排序
        sorted_dates = sorted(self.dates)

        # 回测主循环
        for current_date in sorted_dates:
            if current_date < self.config.start_date.date() or current_date > self.config.end_date.date():
                continue

            # 获取当日数据
            day_bars: dict[str, BarData] = {}
            for vt_symbol, bars in self.bars.items():
                day_bar = next((b for b in bars if b.datetime.date() == current_date), None)
                if day_bar:
                    day_bars[vt_symbol] = day_bar

            if not day_bars:
                continue

            # 更新当前时间
            self.datetime = datetime.combine(current_date, datetime.min.time())
            self.current_bars = day_bars

            # 更新持仓市值
            self._update_position_value()

            # 调用策略on_bars
            if hasattr(self.strategy, 'on_bars'):
                self.strategy.on_bars(day_bars)

            # 计算当日结果
            self._calculate_daily_result(current_date)

        # 计算最终绩效
        self._calculate_performance()

    def _update_position_value(self) -> None:
        """更新持仓市值"""
        for vt_symbol, bar in self.current_bars.items():
            position_size = self.position_manager.get_position(vt_symbol)
            if position_size != 0:
                position_value = position_size * bar.close_price * self.config.size
                self.position_manager.update_position_value(vt_symbol, position_value)
                self.risk_manager.update_position_value(vt_symbol, abs(position_value))

    def _calculate_daily_result(self, current_date: date) -> None:
        """计算每日结果"""
        result = DailyResult(date=current_date)

        # 获取当日成交
        day_trades = [t for t in self.trades if t.datetime.date() == current_date]
        result.trade_count = len(day_trades)

        # 计算当日盈亏
        for trade in day_trades:
            turnover = trade.price * trade.volume * self.config.size
            commission = turnover * self.config.commission_rate
            slippage = trade.price * trade.volume * self.config.slippage * self.config.size

            result.turnover += turnover
            result.commission += commission
            result.slippage += slippage

            # 计算交易盈亏
            trade_pnl = self._calculate_trade_pnl(trade)
            result.trading_pnl += trade_pnl

        # 计算持仓盈亏
        for vt_symbol, bar in self.current_bars.items():
            position_size = self.position_manager.get_position(vt_symbol)
            if position_size != 0:
                # 简化计算，使用收盘价
                cost = self.position_manager.position_cost.get(vt_symbol, 0)
                if cost > 0:
                    holding_pnl = (bar.close_price - cost) * position_size * self.config.size
                    result.holding_pnl += holding_pnl

        result.total_pnl = result.trading_pnl + result.holding_pnl
        result.net_pnl = result.total_pnl - result.commission - result.slippage

        # 更新余额
        self.balance += result.net_pnl
        self.available = self.balance - self.frozen

        result.balance = self.balance
        result.close_price = bar.close_price if bar else 0

        self.daily_results[current_date] = result

        # 更新绩效评估器
        if self.config.initial_capital > 0:
            daily_return = result.net_pnl / self.config.initial_capital
            self.evaluator.add_daily_return(
                date=datetime.combine(current_date, datetime.min.time()),
                ret=daily_return,
                pnl=result.net_pnl,
                portfolio_value=self.balance
            )

    def _calculate_trade_pnl(self, trade: TradeData) -> float:
        """计算单笔交易盈亏"""
        vt_symbol = trade.vt_symbol
        position_size = self.position_manager.get_position(vt_symbol)
        cost = self.position_manager.position_cost.get(vt_symbol, 0)

        if trade.offset == Offset.OPEN:
            # 开仓，更新成本
            return 0.0
        else:
            # 平仓，计算盈亏
            if position_size != 0 and cost > 0:
                if trade.direction == Direction.LONG:
                    # 空头平仓
                    pnl = (cost - trade.price) * trade.volume * self.config.size
                else:
                    # 多头平仓
                    pnl = (trade.price - cost) * trade.volume * self.config.size
                return pnl
            return 0.0

    def _calculate_performance(self) -> None:
        """计算回测绩效"""
        # 绩效评估器已经通过add_daily_return收集了数据
        pass

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

        # 生成订单ID
        self._order_count += 1
        order_id = f"{self.datetime.strftime('%Y%m%d')}_{self._order_count:04d}"

        # 创建订单
        order = OrderData(
            symbol=extract_vt_symbol(vt_symbol)[0],
            exchange=extract_vt_symbol(vt_symbol)[1],
            orderid=order_id,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            traded=0,
            status=Status.NOTTRADED,
            datetime=self.datetime,
            gateway_name="BACKTEST"
        )
        order.vt_orderid = f"BACKTEST.{order_id}"

        self.orders.append(order)
        self.risk_manager.update_order(order)

        # 立即撮合（简化处理）
        self._cross_order(order)

        return order.vt_orderid

    def _cross_order(self, order: OrderData) -> None:
        """撮合订单"""
        bar = self.current_bars.get(order.vt_symbol)
        if not bar:
            return

        # 简化撮合逻辑：使用开盘价成交
        trade_price = bar.open_price

        # 检查涨跌停（简化）
        if trade_price <= 0:
            return

        # 生成成交
        self._trade_count += 1
        trade = TradeData(
            symbol=order.symbol,
            exchange=order.exchange,
            orderid=order.orderid,
            tradeid=str(self._trade_count),
            direction=order.direction,
            offset=order.offset,
            price=trade_price,
            volume=order.volume,
            datetime=self.datetime,
            gateway_name="BACKTEST"
        )
        trade.vt_orderid = order.vt_orderid
        trade.vt_tradeid = f"BACKTEST.{self._trade_count}"

        self.trades.append(trade)

        # 更新订单状态
        order.traded = order.volume
        order.status = Status.ALLTRADED

        # 更新持仓
        self.position_manager.update_position(
            vt_symbol=order.vt_symbol,
            size=order.volume if order.direction == Direction.LONG else -order.volume,
            price=trade_price,
            is_open=(order.offset == Offset.OPEN)
        )

        # 更新风控
        self.risk_manager.update_trade(trade)

        # 计算费用
        turnover = trade_price * order.volume * self.config.size
        commission = turnover * self.config.commission_rate
        slippage = trade_price * order.volume * self.config.slippage * self.config.size

        # 更新资金
        if order.offset == Offset.OPEN:
            margin = turnover * 0.1  # 假设10%保证金
            self.frozen += margin
        else:
            self.frozen -= turnover * 0.1

        self.available = self.balance - self.frozen - commission - slippage

        # 触发回调
        self._emit("trade", trade)

    def get_result(self) -> dict:
        """
        获取回测结果

        Returns:
            回测结果字典
        """
        # 获取绩效评估结果
        evaluation = self.evaluator.evaluate_strategy()

        # 统计信息
        total_days = len(self.daily_results)
        profit_days = sum(1 for r in self.daily_results.values() if r.net_pnl > 0)
        loss_days = sum(1 for r in self.daily_results.values() if r.net_pnl < 0)

        return {
            "config": {
                "start_date": self.config.start_date.strftime("%Y-%m-%d"),
                "end_date": self.config.end_date.strftime("%Y-%m-%d"),
                "initial_capital": self.config.initial_capital,
                "commission_rate": self.config.commission_rate,
                "slippage": self.config.slippage,
            },
            "performance": evaluation,
            "statistics": {
                "total_days": total_days,
                "profit_days": profit_days,
                "loss_days": loss_days,
                "total_trades": len(self.trades),
                "total_orders": len(self.orders),
                "final_balance": self.balance,
                "total_return": (self.balance - self.config.initial_capital) / self.config.initial_capital,
            },
            "daily_results": [
                {
                    "date": str(r.date),
                    "trade_count": r.trade_count,
                    "turnover": r.turnover,
                    "commission": r.commission,
                    "slippage": r.slippage,
                    "trading_pnl": r.trading_pnl,
                    "holding_pnl": r.holding_pnl,
                    "total_pnl": r.total_pnl,
                    "net_pnl": r.net_pnl,
                    "balance": r.balance,
                }
                for r in self.daily_results.values()
            ]
        }

    def generate_report(self) -> str:
        """
        生成回测报告

        Returns:
            报告文本
        """
        result = self.get_result()
        perf = result["performance"]
        stats = result["statistics"]

        report = []
        report.append("=" * 60)
        report.append("AlphaX 回测报告")
        report.append("=" * 60)
        report.append("")

        report.append("【回测配置】")
        for key, value in result["config"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        report.append("【绩效指标】")
        for key, value in perf["metrics"].items():
            report.append(f"  {key}: {value}")
        report.append("")

        report.append("【标准评估】")
        for name, criterion in perf["criteria"].items():
            status = "✓ 通过" if criterion["passed"] else "✗ 未通过"
            report.append(f"  {criterion['description']}: {status}")
        report.append("")

        report.append("【统计信息】")
        for key, value in stats.items():
            if isinstance(value, float):
                report.append(f"  {key}: {value:.2%}" if "return" in key else f"  {key}: {value:.2f}")
            else:
                report.append(f"  {key}: {value}")
        report.append("")

        report.append("=" * 60)

        return "\n".join(report)
