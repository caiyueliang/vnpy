"""
移动平均线策略

基于双均线交叉产生交易信号
"""

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate


class MovingAverageStrategy(StrategyTemplate):
    """
    双均线交叉策略

    当短期均线上穿长期均线时买入
    当短期均线下穿长期均线时卖出
    """

    # 策略参数
    fast_window: int = 10       # 短期均线周期
    slow_window: int = 20       # 长期均线周期

    def __init__(self, backtest_engine, strategy_name, vt_symbols, setting):
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 指标值
        self.fast_ma: dict[str, float] = {}
        self.slow_ma: dict[str, float] = {}

        # 信号状态
        self.signal: dict[str, int] = {s: 0 for s in vt_symbols}  # 0=无, 1=多头, -1=空头

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log(f"策略初始化 - 快周期:{self.fast_window}, 慢周期:{self.slow_window}")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)

            # 检查数据是否足够
            if len(self.history_bars[vt_symbol]) < self.slow_window:
                continue

            # 计算均线
            fast_ma = self.calculate_ma(vt_symbol, self.fast_window)
            slow_ma = self.calculate_ma(vt_symbol, self.slow_window)

            self.fast_ma[vt_symbol] = fast_ma
            self.slow_ma[vt_symbol] = slow_ma

            # 获取当前持仓
            pos = self.get_position(vt_symbol)

            # 生成交易信号
            if fast_ma > slow_ma:
                # 多头信号
                if pos <= 0:
                    # 平空仓，开多仓
                    if pos < 0:
                        self.cover(vt_symbol, bar.close_price, abs(pos))
                        self.write_log(f"{vt_symbol} 平空仓 @ {bar.close_price}")

                    # 计算目标仓位
                    target_volume = self.calculate_target_volume(vt_symbol, bar.close_price)
                    self.buy(vt_symbol, bar.close_price, target_volume)
                    self.write_log(f"{vt_symbol} 买入开仓 @ {bar.close_price}, 数量:{target_volume}")

                    self.signal[vt_symbol] = 1

            elif fast_ma < slow_ma:
                # 空头信号
                if pos >= 0:
                    # 平多仓，开空仓
                    if pos > 0:
                        self.sell(vt_symbol, bar.close_price, pos)
                        self.write_log(f"{vt_symbol} 卖出平仓 @ {bar.close_price}")

                    # 计算目标仓位
                    target_volume = self.calculate_target_volume(vt_symbol, bar.close_price)
                    self.short(vt_symbol, bar.close_price, target_volume)
                    self.write_log(f"{vt_symbol} 卖出开仓 @ {bar.close_price}, 数量:{target_volume}")

                    self.signal[vt_symbol] = -1

    def calculate_target_volume(self, vt_symbol: str, price: float) -> float:
        """
        计算目标仓位数量

        Args:
            vt_symbol: 合约代码
            price: 当前价格

        Returns:
            目标数量
        """
        # 简化的仓位计算：使用固定金额
        capital_per_trade = self.backtest_engine.config.initial_capital * 0.1  # 10%资金
        volume = capital_per_trade / price if price > 0 else 0

        # 取整（假设股票为100股一手）
        volume = int(volume / 100) * 100

        return max(volume, 100)  # 至少100股
