"""
策略验证测试

运行策略回测验证，评估策略是否能达到目标收益
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List
import random

import numpy as np
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange

from alphax.validation import StrategyValidator, ValidationConfig
from alphax.strategies import MultiFactorMomentumStrategy, BreakoutStrategy


def generate_mock_data(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    trend: str = "random"
) -> List[BarData]:
    """
    生成模拟K线数据

    Args:
        symbol: 标的代码
        start_date: 开始日期
        end_date: 结束日期
        trend: 趋势类型 ("up", "down", "random", "trending")

    Returns:
        K线数据列表
    """
    bars = []
    current_date = start_date

    # 初始价格
    price = 100.0
    base_volume = 1000000

    # 根据趋势设置参数
    if trend == "up":
        drift = 0.0005  # 上涨趋势
    elif trend == "down":
        drift = -0.0005  # 下跌趋势
    elif trend == "trending":
        drift = 0.0003
    else:
        drift = 0.0  # 随机游走

    volatility = 0.02  # 波动率

    days = 0
    while current_date <= end_date:
        # 跳过周末
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        # 生成价格变动
        if trend == "trending":
            # 趋势行情：持续性更强
            if days % 20 < 10:
                daily_drift = abs(drift) * 2
            else:
                daily_drift = -abs(drift) * 2
        else:
            daily_drift = drift

        change = np.random.normal(daily_drift, volatility)

        # 计算OHLC
        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.005)))
        low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.005)))

        # 成交量
        volume = int(base_volume * (1 + np.random.normal(0, 0.2)))

        bar = BarData(
            symbol=symbol,
            exchange=Exchange.SSE,
            datetime=current_date,
            interval="d",
            volume=volume,
            open_price=round(open_price, 2),
            high_price=round(high_price, 2),
            low_price=round(low_price, 2),
            close_price=round(close_price, 2),
            gateway_name="MOCK"
        )
        bar.vt_symbol = f"{symbol}.{Exchange.SSE.value}"

        bars.append(bar)

        # 更新价格
        price = close_price
        current_date += timedelta(days=1)
        days += 1

    return bars


def test_momentum_strategy():
    """测试动量策略"""
    print("\n" + "=" * 80)
    print("测试多因子动量策略")
    print("=" * 80)

    # 生成2年模拟数据
    end_date = datetime(2024, 12, 31)
    start_date = end_date - timedelta(days=730)

    # 生成不同市场环境的数据
    symbols_data = {
        "600519": generate_mock_data("600519", start_date, end_date, "trending"),  # 茅台 - 趋势
        "000001": generate_mock_data("000001", start_date, end_date, "random"),    # 平安 - 震荡
        "000858": generate_mock_data("000858", start_date, end_date, "up"),        # 五粮液 - 上涨
    }

    # 创建验证配置
    config = ValidationConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=1_000_000.0,
        target_annual_return=10.0,  # 1000% 目标
        target_sharpe=3.0,
        target_max_drawdown=0.20,
        target_win_rate=0.55
    )

    validator = StrategyValidator(config)

    # 测试参数
    strategy_params = {
        "lookback_period": 20,
        "price_momentum_weight": 0.4,
        "volume_momentum_weight": 0.2,
        "vol_adj_momentum_weight": 0.3,
        "trend_strength_weight": 0.1,
        "long_threshold": 0.3,
        "short_threshold": -0.3,
        "exit_threshold": 0.05
    }

    # 多标的验证
    print("\n运行多标的验证...")
    results = validator.multi_symbol_validation(
        MultiFactorMomentumStrategy,
        strategy_params,
        symbols_data
    )

    # 打印结果
    print("\n【多标的验证结果】")
    summary = results["summary"]
    print(f"  平均年化收益率: {summary['avg_annual_return']:.2%}")
    print(f"  收益率标准差: {summary['std_annual_return']:.2%}")
    print(f"  平均夏普比率: {summary['avg_sharpe']:.2f}")
    print(f"  一致性得分: {summary['consistency_score']:.2f}")
    print(f"  通过率: {summary['pass_rate']:.2%}")

    # 详细结果
    print("\n【各标的详细结果】")
    for symbol, result in results["individual_results"].items():
        status = "✓ 通过" if result.passed else "✗ 未通过"
        print(f"\n  {symbol}:")
        print(f"    状态: {status}")
        print(f"    年化收益率: {result.annual_return:.2%}")
        print(f"    夏普比率: {result.sharpe_ratio:.2f}")
        print(f"    最大回撤: {result.max_drawdown:.2%}")
        print(f"    胜率: {result.win_rate:.2%}")

        if result.failure_reasons:
            print("    未通过原因:")
            for reason in result.failure_reasons:
                print(f"      - {reason}")

    return results


def test_breakout_strategy():
    """测试突破策略"""
    print("\n" + "=" * 80)
    print("测试突破策略")
    print("=" * 80)

    # 生成2年模拟数据
    end_date = datetime(2024, 12, 31)
    start_date = end_date - timedelta(days=730)

    bars = generate_mock_data("600519", start_date, end_date, "trending")

    # 创建验证配置
    config = ValidationConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=1_000_000.0,
        target_annual_return=10.0,
        target_sharpe=3.0,
        target_max_drawdown=0.20,
        target_win_rate=0.55
    )

    validator = StrategyValidator(config)

    # 测试参数
    strategy_params = {
        "channel_period": 20,
        "breakout_threshold": 0.02,
        "volume_confirm": True,
        "volume_threshold": 1.5,
        "atr_period": 14,
        "atr_multiplier": 2.0
    }

    print("\n运行单标的验证...")
    result = validator.validate_strategy(
        BreakoutStrategy,
        strategy_params,
        "600519",
        bars
    )

    # 保存结果
    validator.results.append(result)

    # 打印结果
    status = "✓ 通过" if result.passed else "✗ 未通过"
    print(f"\n  状态: {status}")
    print(f"  年化收益率: {result.annual_return:.2%}")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    print(f"  最大回撤: {result.max_drawdown:.2%}")
    print(f"  胜率: {result.win_rate:.2%}")
    print(f"  交易次数: {result.total_trades}")
    print(f"  Calmar比率: {result.calmar_ratio:.2f}")
    print(f"  Sortino比率: {result.sortino_ratio:.2f}")

    if result.failure_reasons:
        print("\n  未通过原因:")
        for reason in result.failure_reasons:
            print(f"    - {reason}")

    return result


def analyze_target_gap(results: dict):
    """分析目标差距"""
    print("\n" + "=" * 80)
    print("目标差距分析")
    print("=" * 80)

    target_return = 10.0  # 1000%
    target_sharpe = 3.0

    avg_return = results["summary"]["avg_annual_return"]
    avg_sharpe = results["summary"]["avg_sharpe"]

    print(f"\n【收益目标】")
    print(f"  目标年化收益率: {target_return:.2%}")
    print(f"  实际平均收益率: {avg_return:.2%}")
    print(f"  差距: {target_return - avg_return:.2%}")
    print(f"  达成率: {avg_return / target_return:.2%}")

    print(f"\n【风险调整收益目标】")
    print(f"  目标夏普比率: {target_sharpe:.2f}")
    print(f"  实际平均夏普: {avg_sharpe:.2f}")
    print(f"  差距: {target_sharpe - avg_sharpe:.2f}")
    print(f"  达成率: {avg_sharpe / target_sharpe:.2%}")

    print("\n【关键问题】")
    if avg_return < target_return:
        print("  1. 策略收益率远低于目标，需要:")
        print("     - 提高交易频率")
        print("     - 增加杠杆使用")
        print("     - 优化信号准确性")
        print("     - 开发更高收益的策略")

    if avg_sharpe < target_sharpe:
        print("  2. 风险调整收益不足，需要:")
        print("     - 改进入场时机")
        print("     - 优化止损策略")
        print("     - 降低交易频率")
        print("     - 过滤低质量信号")

    print("\n【改进建议】")
    print("  1. 使用真实历史数据进行回测")
    print("  2. 增加策略组合，分散风险")
    print("  3. 引入机器学习优化信号")
    print("  4. 优化仓位管理，提高资金使用效率")
    print("  5. 开发更多类型的策略（事件驱动、统计套利等）")


if __name__ == "__main__":
    print("AlphaX 策略验证测试")
    print("=" * 80)

    # 测试动量策略
    momentum_results = test_momentum_strategy()

    # 测试突破策略
    breakout_result = test_breakout_strategy()

    # 分析目标差距
    analyze_target_gap(momentum_results)

    print("\n" + "=" * 80)
    print("验证测试完成")
    print("=" * 80)
