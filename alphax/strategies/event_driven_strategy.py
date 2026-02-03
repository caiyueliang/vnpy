"""
事件驱动策略

基于特定事件进行交易决策的策略：
1. 财报事件策略 - 基于业绩预告、业绩快报等事件
2. 资金流向事件策略 - 基于主力资金流向变化
3. 龙虎榜事件策略 - 基于龙虎榜数据
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate, StrategyConfig


@dataclass
class EventDrivenConfig(StrategyConfig):
    """事件驱动策略配置"""
    # 事件窗口
    event_lookback_days: int = 30        # 事件回看天数
    holding_period: int = 5              # 持仓周期（交易日）

    # 财报事件参数
    earnings_threshold: float = 0.20     # 业绩预告变动阈值（20%）
    surprise_threshold: float = 0.10     # 业绩超预期阈值

    # 资金流向参数
    flow_threshold: float = 1e8          # 资金流向阈值（1亿）
    flow_consecutive_days: int = 3       # 连续流入天数

    # 龙虎榜参数
    dragon_tiger_amount: float = 5e7     # 龙虎榜金额阈值（5000万）
    institution_buy_ratio: float = 0.6   # 机构买入比例阈值

    # 仓位管理
    event_position_scale: float = 1.0    # 事件仓位缩放


class EarningsEventStrategy(StrategyTemplate):
    """
    财报事件策略

    基于业绩预告、业绩快报等财报事件进行交易。
    当公司业绩大幅超出预期时，预期股价会上涨；
    当公司业绩大幅低于预期时，预期股价会下跌。

    策略逻辑：
    1. 监控业绩预告数据
    2. 筛选净利润变动幅度超过阈值的股票
    3. 预增股票做多，预减股票做空
    4. 持有固定周期后平仓
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = EventDrivenConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in EventDrivenConfig.__dataclass_fields__}
        )

        # 事件状态
        self.earnings_events: dict[str, dict] = {}  # 股票代码 -> 事件信息
        self.position_entry_dates: dict[str, datetime] = {}

        # 数据收集器
        self.fundamental_collector: Any = None

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("财报事件策略初始化完成")

        # 初始化基本面数据收集器
        try:
            from data.collectors import FundamentalCollector
            self.fundamental_collector = FundamentalCollector()
            self.fundamental_collector.connect()
        except Exception as e:
            self.write_log(f"基本面数据收集器初始化失败: {e}")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("财报事件策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("财报事件策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 更新历史数据
        for vt_symbol, bar in bars.items():
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > 60:
                self.history_bars[vt_symbol].pop(0)

        # 检查财报事件
        self._check_earnings_events()

        # 生成交易信号
        for vt_symbol, bar in bars.items():
            self._generate_signals(vt_symbol, bar)

    def _check_earnings_events(self) -> None:
        """检查财报事件"""
        if not self.fundamental_collector:
            return

        try:
            # 获取业绩预告
            forecasts = self.fundamental_collector.get_performance_forecast()

            for forecast in forecasts:
                symbol = forecast.get("symbol", "")
                if symbol not in [s.split(".")[0] for s in self.vt_symbols]:
                    continue

                # 检查净利润变动幅度
                profit_change_min = forecast.get("profit_change_min", 0)
                profit_change_max = forecast.get("profit_change_max", 0)
                avg_change = (profit_change_min + profit_change_max) / 2

                # 预增且超过阈值
                if forecast.get("forecast_type") == "预增" and avg_change > self.config.earnings_threshold * 100:
                    self.earnings_events[symbol] = {
                        "type": "positive",
                        "change": avg_change,
                        "date": forecast.get("forecast_date"),
                        "reason": forecast.get("reason", ""),
                    }
                    self.write_log(f"发现预增事件: {symbol}, 变动: {avg_change:.1f}%")

                # 预减且超过阈值
                elif forecast.get("forecast_type") == "预减" and avg_change < -self.config.earnings_threshold * 100:
                    self.earnings_events[symbol] = {
                        "type": "negative",
                        "change": avg_change,
                        "date": forecast.get("forecast_date"),
                        "reason": forecast.get("reason", ""),
                    }
                    self.write_log(f"发现预减事件: {symbol}, 变动: {avg_change:.1f}%")

        except Exception as e:
            self.write_log(f"检查财报事件失败: {e}")

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        symbol = vt_symbol.split(".")[0]
        position = self.get_position(vt_symbol)

        # 检查是否有事件
        if symbol in self.earnings_events:
            event = self.earnings_events[symbol]

            # 入场信号
            if position == 0:
                volume = self._calculate_position_size(vt_symbol)

                if event["type"] == "positive":
                    self.buy(vt_symbol, bar.close_price, volume)
                    self.position_entry_dates[vt_symbol] = bar.datetime
                    self.write_log(f"财报事件做多: {vt_symbol}, 预增{event['change']:.1f}%")

                elif event["type"] == "negative":
                    self.short(vt_symbol, bar.close_price, volume)
                    self.position_entry_dates[vt_symbol] = bar.datetime
                    self.write_log(f"财报事件做空: {vt_symbol}, 预减{event['change']:.1f}%")

            # 移除已处理的事件
            del self.earnings_events[symbol]

        # 出场信号（持仓时间到期）
        if position != 0 and vt_symbol in self.position_entry_dates:
            hold_days = (bar.datetime - self.position_entry_dates[vt_symbol]).days

            if hold_days >= self.config.holding_period:
                if position > 0:
                    self.sell(vt_symbol, bar.close_price, position)
                else:
                    self.cover(vt_symbol, bar.close_price, abs(position))
                self.write_log(f"持仓到期平仓: {vt_symbol}, 持有{hold_days}天")
                del self.position_entry_dates[vt_symbol]

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """计算仓位大小"""
        return 100 * self.config.event_position_scale


class CapitalFlowEventStrategy(StrategyTemplate):
    """
    资金流向事件策略

    基于主力资金流向变化进行交易。
    当主力资金连续多日大幅流入时，预期股价会上涨；
    当主力资金连续多日大幅流出时，预期股价会下跌。

    策略逻辑：
    1. 监控个股资金流向数据
    2. 识别主力资金连续流入/流出事件
    3. 连续流入做多，连续流出做空
    4. 资金流向反转时平仓
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = EventDrivenConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in EventDrivenConfig.__dataclass_fields__}
        )

        # 资金流向历史
        self.capital_flow_history: dict[str, list[dict]] = {s: [] for s in vt_symbols}
        self.flow_events: dict[str, str] = {}  # 股票代码 -> 事件类型 (inflow/outflow)

        # 数据收集器
        self.flow_collector: Any = None

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("资金流向事件策略初始化完成")

        try:
            from data.collectors import CapitalFlowCollector
            self.flow_collector = CapitalFlowCollector()
            self.flow_collector.connect()
        except Exception as e:
            self.write_log(f"资金流向收集器初始化失败: {e}")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("资金流向事件策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("资金流向事件策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 更新历史数据
        for vt_symbol, bar in bars.items():
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > 60:
                self.history_bars[vt_symbol].pop(0)

        # 更新资金流向数据
        self._update_capital_flow()

        # 生成交易信号
        for vt_symbol, bar in bars.items():
            self._generate_signals(vt_symbol, bar)

    def _update_capital_flow(self) -> None:
        """更新资金流向数据"""
        if not self.flow_collector:
            return

        try:
            for vt_symbol in self.vt_symbols:
                symbol = vt_symbol.split(".")[0]

                # 获取资金流向
                flow_data = self.flow_collector.get_stock_capital_flow(symbol)

                if flow_data:
                    self.capital_flow_history[vt_symbol].append({
                        "date": datetime.now(),
                        "main_inflow": flow_data.main_inflow,
                        "main_outflow": flow_data.main_outflow,
                        "net_main": flow_data.net_main,
                    })

                    if len(self.capital_flow_history[vt_symbol]) > 10:
                        self.capital_flow_history[vt_symbol].pop(0)

                    # 检查资金流向事件
                    self._detect_flow_events(vt_symbol)

        except Exception as e:
            self.write_log(f"更新资金流向失败: {e}")

    def _detect_flow_events(self, vt_symbol: str) -> None:
        """
        检测资金流向事件

        Args:
            vt_symbol: 合约代码
        """
        history = self.capital_flow_history.get(vt_symbol, [])

        if len(history) < self.config.flow_consecutive_days:
            return

        # 检查最近N天的资金流向
        recent_flows = history[-self.config.flow_consecutive_days:]

        # 计算净流入天数
        positive_days = sum(1 for f in recent_flows if f["net_main"] > 0)
        negative_days = sum(1 for f in recent_flows if f["net_main"] < 0)

        # 计算总净流入
        total_net_flow = sum(f["net_main"] for f in recent_flows)

        # 连续流入事件
        if positive_days >= self.config.flow_consecutive_days and total_net_flow > self.config.flow_threshold:
            self.flow_events[vt_symbol] = "inflow"
            self.write_log(f"资金流向事件: {vt_symbol} 连续{positive_days}日流入, 净流入{total_net_flow/1e8:.2f}亿")

        # 连续流出事件
        elif negative_days >= self.config.flow_consecutive_days and total_net_flow < -self.config.flow_threshold:
            self.flow_events[vt_symbol] = "outflow"
            self.write_log(f"资金流向事件: {vt_symbol} 连续{negative_days}日流出, 净流出{abs(total_net_flow)/1e8:.2f}亿")

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        position = self.get_position(vt_symbol)

        # 检查资金流向事件
        if vt_symbol in self.flow_events:
            event_type = self.flow_events[vt_symbol]

            # 入场信号
            if position == 0:
                volume = self._calculate_position_size(vt_symbol)

                if event_type == "inflow":
                    self.buy(vt_symbol, bar.close_price, volume)
                    self.write_log(f"资金流向做多: {vt_symbol}")

                elif event_type == "outflow":
                    self.short(vt_symbol, bar.close_price, volume)
                    self.write_log(f"资金流向做空: {vt_symbol}")

            # 移除已处理的事件
            del self.flow_events[vt_symbol]

        # 出场信号（资金流向反转）
        if position != 0:
            history = self.capital_flow_history.get(vt_symbol, [])
            if len(history) >= 2:
                latest_flow = history[-1]["net_main"]
                prev_flow = history[-2]["net_main"]

                # 多头持仓，资金流向转负
                if position > 0 and latest_flow < 0 and prev_flow > 0:
                    self.sell(vt_symbol, bar.close_price, position)
                    self.write_log(f"资金流向反转平仓(多): {vt_symbol}")

                # 空头持仓，资金流向转正
                elif position < 0 and latest_flow > 0 and prev_flow < 0:
                    self.cover(vt_symbol, bar.close_price, abs(position))
                    self.write_log(f"资金流向反转平仓(空): {vt_symbol}")

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """计算仓位大小"""
        return 100 * self.config.event_position_scale


class DragonTigerEventStrategy(StrategyTemplate):
    """
    龙虎榜事件策略

    基于龙虎榜数据进行交易。
    当股票登上龙虎榜且机构大幅买入时，预期股价会上涨；
    当机构大幅卖出时，预期股价会下跌。

    策略逻辑：
    1. 监控每日龙虎榜数据
    2. 筛选机构买入比例高的股票
    3. 机构大幅买入做多，机构大幅卖出做空
    4. 次日开盘即平仓（T+1制度）
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = EventDrivenConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in EventDrivenConfig.__dataclass_fields__}
        )

        # 龙虎榜事件
        self.dragon_tiger_events: dict[str, dict] = {}
        self.position_entry_dates: dict[str, datetime] = {}

        # 数据收集器
        self.fundamental_collector: Any = None

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("龙虎榜事件策略初始化完成")

        try:
            from data.collectors import FundamentalCollector
            self.fundamental_collector = FundamentalCollector()
            self.fundamental_collector.connect()
        except Exception as e:
            self.write_log(f"龙虎榜收集器初始化失败: {e}")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("龙虎榜事件策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("龙虎榜事件策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        # 更新历史数据
        for vt_symbol, bar in bars.items():
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > 20:
                self.history_bars[vt_symbol].pop(0)

        # 检查龙虎榜事件
        self._check_dragon_tiger_events()

        # 生成交易信号
        for vt_symbol, bar in bars.items():
            self._generate_signals(vt_symbol, bar)

    def _check_dragon_tiger_events(self) -> None:
        """检查龙虎榜事件"""
        if not self.fundamental_collector:
            return

        try:
            # 获取昨日龙虎榜
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            dragons = self.fundamental_collector.get_dragon_tiger_list(yesterday)

            for dragon in dragons:
                symbol = dragon.get("symbol", "")
                if symbol not in [s.split(".")[0] for s in self.vt_symbols]:
                    continue

                # 检查成交金额
                amount = dragon.get("amount", 0)
                if amount < self.config.dragon_tiger_amount:
                    continue

                # 获取龙虎榜详情
                detail = self.fundamental_collector.get_dragon_tiger_detail(symbol, yesterday)

                if not detail:
                    continue

                # 计算机构买卖情况
                buy_depts = detail.get("buy_departments", [])
                sell_depts = detail.get("sell_departments", [])

                total_buy = sum(d.get("amount", 0) for d in buy_depts)
                total_sell = sum(d.get("amount", 0) for d in sell_depts)

                # 识别机构席位（简化：包含"机构专用"的营业部）
                institution_buy = sum(
                    d.get("amount", 0) for d in buy_depts
                    if "机构" in d.get("dept_name", "")
                )
                institution_sell = sum(
                    d.get("amount", 0) for d in sell_depts
                    if "机构" in d.get("dept_name", "")
                )

                # 机构大幅买入事件
                if total_buy > 0 and institution_buy / total_buy > self.config.institution_buy_ratio:
                    self.dragon_tiger_events[symbol] = {
                        "type": "institution_buy",
                        "amount": amount,
                        "institution_buy": institution_buy,
                        "date": yesterday,
                    }
                    self.write_log(f"龙虎榜事件: {symbol} 机构买入{institution_buy/1e8:.2f}亿")

                # 机构大幅卖出事件
                elif total_sell > 0 and institution_sell / total_sell > self.config.institution_buy_ratio:
                    self.dragon_tiger_events[symbol] = {
                        "type": "institution_sell",
                        "amount": amount,
                        "institution_sell": institution_sell,
                        "date": yesterday,
                    }
                    self.write_log(f"龙虎榜事件: {symbol} 机构卖出{institution_sell/1e8:.2f}亿")

        except Exception as e:
            self.write_log(f"检查龙虎榜事件失败: {e}")

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        symbol = vt_symbol.split(".")[0]
        position = self.get_position(vt_symbol)

        # 检查龙虎榜事件
        if symbol in self.dragon_tiger_events:
            event = self.dragon_tiger_events[symbol]

            # 入场信号（次日开盘买入）
            if position == 0:
                volume = self._calculate_position_size(vt_symbol)

                if event["type"] == "institution_buy":
                    self.buy(vt_symbol, bar.close_price, volume)
                    self.position_entry_dates[vt_symbol] = bar.datetime
                    self.write_log(f"龙虎榜做多: {vt_symbol}, 机构买入{event['institution_buy']/1e8:.2f}亿")

                elif event["type"] == "institution_sell":
                    self.short(vt_symbol, bar.close_price, volume)
                    self.position_entry_dates[vt_symbol] = bar.datetime
                    self.write_log(f"龙虎榜做空: {vt_symbol}, 机构卖出{event['institution_sell']/1e8:.2f}亿")

            # 移除已处理的事件
            del self.dragon_tiger_events[symbol]

        # 出场信号（T+1，次日收盘前平仓）
        if position != 0 and vt_symbol in self.position_entry_dates:
            hold_days = (bar.datetime - self.position_entry_dates[vt_symbol]).days

            # 次日即平仓（A股T+1制度）
            if hold_days >= 1:
                if position > 0:
                    self.sell(vt_symbol, bar.close_price, position)
                else:
                    self.cover(vt_symbol, bar.close_price, abs(position))
                self.write_log(f"T+1平仓: {vt_symbol}, 持有{hold_days}天")
                del self.position_entry_dates[vt_symbol]

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """计算仓位大小"""
        return 100 * self.config.event_position_scale
