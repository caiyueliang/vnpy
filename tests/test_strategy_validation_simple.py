"""
策略验证测试 - 简化版

直接测试回测引擎和策略，评估是否能达到目标收益
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
from vnpy.trader.constant import Exchange, Direction, Offset, Status

from alphax.backtest.engine import BacktestEngine, BacktestConfig
from alphax.risk import RiskLimits
from alphax.position import PositionConfig
from alphax.strategies.momentum_strategy import MultiFactorMomentumStrategy


def generate_mock_data(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    trend: str = "random"
) -> List[BarData]:
    """
    生成模拟K线数据
    """
    bars = []
    current_date = start_date
    price = 100.0
    base_volume = 1000000

    if trend == "up":
        drift = 0.0005
    elif trend == "down":
        drift = -0.0005
    elif trend == "trending":
        drift = 0.0003
    else:
        drift = 0.0

    volatility = 0.02
    days = 0

    while current_date <= end_date:
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue

        if trend == "trending":
            if days % 20 < 10:
                daily_drift = abs(drift) * 2
            else:
                daily_drift = -abs(drift) * 2
        else:
            daily_drift = drift

        change = np.random.normal(daily_drift, volatility)

        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.005)))
        low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.005)))
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
        bar.vt_symbol = f"{symbol}.SSE"

        bars.append(bar)
        price = close_price
        current_date += timedelta(days=1)
        days += 1

    return bars


def test_strategy_performance():
    """测试策略性能"""
    print("\n" + "=" * 80)
    print("AlphaX 策略性能验证")
    print("=" * 80)

    # 生成2年模拟数据
    end_date = datetime(2024, 12, 31)
    start_date = end_date - timedelta(days=730)

    print(f"\n回测区间: {start_date.date()} 至 {end_date.date()}")
    print(f"初始资金: ¥1,000,000")

    # 生成不同市场环境的数据
    test_symbols = {
        "600519": ("贵州茅台", "trending"),
        "000001": ("平安银行", "random"),
        "000858": ("五粮液", "up"),
    }

    results_summary = []

    for symbol, (name, trend) in test_symbols.items():
        print(f"\n{'='*60}")
        print(f"测试标的: {name} ({symbol}) - {trend}市场")
        print('='*60)

        bars = generate_mock_data(symbol, start_date, end_date, trend)
        print(f"数据条数: {len(bars)}")

        # 创建回测配置
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            initial_capital=1_000_000.0,
            commission_rate=0.0003,
            slippage=0.0001,
            risk_limits=RiskLimits(),
            position_config=PositionConfig()
        )

        # 创建回测引擎
        engine = BacktestEngine(config)
        vt_symbol = f"{symbol}.SSE"
        engine.add_data(vt_symbol, bars)

        # 设置策略参数
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

        engine.set_strategy(MultiFactorMomentumStrategy, strategy_params)

        # 运行回测
        engine.run_backtesting()

        # 获取结果
        result = engine.get_result()
        perf = result.get("performance", {})
        metrics = perf.get("metrics", {})
        stats = result.get("statistics", {})

        # 打印结果
        total_return = metrics.get("total_return", 0)
        annual_return = metrics.get("annual_return", 0)
        sharpe = metrics.get("sharpe_ratio", 0)
        max_dd = metrics.get("max_drawdown", 0)
        win_rate = metrics.get("win_rate", 0)

        print(f"\n【回测结果】")
        print(f"  总收益率: {total_return:.2%}")
        print(f"  年化收益率: {annual_return:.2%}")
        print(f"  夏普比率: {sharpe:.2f}")
        print(f"  最大回撤: {max_dd:.2%}")
        print(f"  胜率: {win_rate:.2%}")
        print(f"  交易次数: {stats.get('total_trades', 0)}")
        print(f"  最终资金: ¥{stats.get('final_balance', 0):,.2f}")

        # 目标对比
        target_return = 10.0  # 1000%
        target_sharpe = 3.0
        target_max_dd = 0.20

        print(f"\n【目标对比】")
        print(f"  年化收益目标: {target_return:.2%} | 实际: {annual_return:.2%} | 达成率: {annual_return/target_return:.1%}")
        print(f"  夏普比率目标: {target_sharpe:.2f} | 实际: {sharpe:.2f} | 达成率: {sharpe/target_sharpe:.1%}")
        print(f"  最大回撤限制: {target_max_dd:.2%} | 实际: {max_dd:.2%} | {'✓ 通过' if max_dd <= target_max_dd else '✗ 超标'}")

        results_summary.append({
            "symbol": symbol,
            "name": name,
            "trend": trend,
            "annual_return": annual_return,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "win_rate": win_rate,
            "trades": stats.get('total_trades', 0)
        })

    # 汇总分析
    print("\n" + "=" * 80)
    print("汇总分析")
    print("=" * 80)

    avg_return = np.mean([r["annual_return"] for r in results_summary])
    avg_sharpe = np.mean([r["sharpe"] for r in results_summary])
    avg_max_dd = np.mean([r["max_dd"] for r in results_summary])

    print(f"\n【平均表现】")
    print(f"  平均年化收益率: {avg_return:.2%}")
    print(f"  平均夏普比率: {avg_sharpe:.2f}")
    print(f"  平均最大回撤: {avg_max_dd:.2%}")

    print(f"\n【目标差距】")
    print(f"  收益目标: {target_return:.2%}")
    print(f"  实际平均: {avg_return:.2%}")
    print(f"  差距: {target_return - avg_return:.2%}")
    print(f"  达成率: {avg_return/target_return:.1%}")

    print(f"\n【结论】")
    if avg_return < target_return * 0.1:
        print("  ⚠️ 策略收益率远低于目标（差距超过90%）")
        print("  可能原因:")
        print("    1. 模拟数据缺乏真实市场特征")
        print("    2. 策略参数需要优化")
        print("    3. 需要组合多个策略")
        print("    4. 需要更高频的交易策略")
    elif avg_return < target_return * 0.5:
        print("  ⚠️ 策略收益率低于目标（差距超过50%）")
        print("  需要进一步优化策略")
    else:
        print("  ✓ 策略表现接近目标")

    return results_summary


def analyze_what_is_needed():
    """分析实现目标需要什么"""
    print("\n" + "=" * 80)
    print("实现'一年十倍'目标的路径分析")
    print("=" * 80)

    target_return = 10.0  # 1000%

    print(f"\n【数学分析】")
    print(f"  目标: 年化收益率 {target_return:.0%}")
    print(f"  月均需要: {(target_return ** (1/12) - 1):.2%}")
    print(f"  日均需要: {(target_return ** (1/252) - 1):.3%}")

    print(f"\n【现实对比】")
    print(f"  巴菲特长期年化: ~20%")
    print(f"  顶级对冲基金: ~30-50%")
    print(f"  文艺复兴大奖章: ~66%（费后）")
    print(f"  我们的目标: {target_return:.0%}")

    print(f"\n【实现路径】")
    print(f"  1. 策略层面:")
    print(f"     - 多策略组合（趋势+均值回归+事件驱动+ML）")
    print(f"     - 高频交易（日内多次交易）")
    print(f"     - 杠杆使用（谨慎控制风险）")
    print(f"     - 选股优化（集中持有强势股）")

    print(f"\n  2. 执行层面:")
    print(f"     - 低延迟执行")
    print(f"     - 滑点控制 < 0.05%")
    print(f"     - 成交率 > 95%")
    print(f"     - 算法交易优化")

    print(f"\n  3. 风险管理:")
    print(f"     - 严格止损（单笔亏损 < 2%）")
    print(f"     - 仓位控制（单票 < 20%）")
    print(f"     - 回撤控制（最大 < 20%）")
    print(f"     - 动态调整")

    print(f"\n【关键成功因素】")
    print(f"  1. 数据优势: 独家数据源、另类数据")
    print(f"  2. 算法优势: 机器学习、深度学习")
    print(f"  3. 执行优势: 低延迟、高成交率")
    print(f"  4. 风控优势: 严格纪律、动态调整")

    print(f"\n【风险提示】")
    print(f"  ⚠️ 年化1000%的目标极其激进")
    print(f"  ⚠️ 需要承担极高的风险")
    print(f"  ⚠️ 可能面临巨额亏损")
    print(f"  ⚠️ 建议先用小资金实盘测试")


if __name__ == "__main__":
    print("AlphaX 策略验证与目标分析")
    print("=" * 80)

    # 运行策略测试
    results = test_strategy_performance()

    # 分析实现路径
    analyze_what_is_needed()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
