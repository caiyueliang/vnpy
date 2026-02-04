"""
100只A股标的策略回测验证 (V3 - 简化版)

使用分布在各行业的100只A股进行策略回测，验证策略有效性
目标：验证是否能达到年化100%收益目标
"""

import sys
import traceback
from datetime import datetime, timedelta
from typing import Dict, List
import json
import random

import pandas as pd
import numpy as np

# 添加项目路径
sys.path.insert(0, r'e:\PythonProject\vnpy')

from alphax.backtest.engine import BacktestEngine, BacktestConfig
from alphax.evaluation import PerformanceEvaluator
from alphax.strategies.momentum_strategy import MultiFactorMomentumStrategy
from alphax.strategies.breakout_strategy import BreakoutStrategy
from alphax.strategies.moving_average_strategy import MovingAverageStrategy
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval


def get_exchange_from_symbol(symbol: str) -> Exchange:
    """根据标的代码获取交易所"""
    if ".SH" in symbol:
        return Exchange.SSE
    elif ".SZ" in symbol:
        return Exchange.SZSE
    return Exchange.SZSE


def get_vt_symbol(symbol: str) -> str:
    """生成正确的 vt_symbol 格式"""
    if ".SH" in symbol:
        return symbol.replace(".SH", ".SSE")
    elif ".SZ" in symbol:
        return symbol.replace(".SZ", ".SZSE")
    return symbol + ".SZSE"


# 100只分布在各行业的A股标的
STOCKS_100 = {
    "白酒": ["600519.SH", "000858.SZ", "000568.SZ", "002304.SZ", "600809.SH", "600887.SH", "603288.SH", "600276.SH", "000538.SZ", "603259.SH"],
    "银行金融": ["600036.SH", "601398.SH", "601288.SH", "601939.SH", "601988.SH", "601318.SH", "601628.SH", "600030.SH", "601688.SH", "600837.SH"],
    "新能源": ["300750.SZ", "601012.SH", "600438.SH", "002594.SZ", "601669.SH", "601727.SH", "600900.SH", "601985.SH", "600011.SH", "601016.SH"],
    "科技半导体": ["688981.SH", "603501.SH", "002371.SZ", "688012.SH", "603986.SH", "002049.SZ", "688008.SH", "300782.SZ", "600584.SH", "002156.SZ"],
    "汽车制造": ["601127.SH", "000625.SZ", "600104.SH", "601633.SH", "601238.SH", "000338.SZ", "600660.SH", "601766.SH", "601989.SH", "600031.SH"],
    "房地产基建": ["000002.SZ", "600048.SH", "001979.SZ", "600606.SH", "601668.SH", "601390.SH", "601800.SH", "601186.SH", "601117.SH", "600170.SH"],
    "石油化工": ["601857.SH", "600028.SH", "600938.SH", "002493.SZ", "600346.SH", "600309.SH", "002648.SZ", "600426.SH", "601233.SH", "603225.SH"],
    "有色钢铁": ["601899.SH", "603993.SH", "600111.SH", "600362.SH", "601600.SH", "600019.SH", "000932.SZ", "600507.SH", "002110.SZ", "600808.SH"],
    "通信传媒": ["600941.SH", "600050.SH", "601728.SH", "000063.SZ", "600498.SH", "603444.SH", "002624.SZ", "300413.SZ", "002027.SZ", "600088.SH"],
    "消费零售": ["601888.SH", "600859.SH", "002024.SZ", "601933.SH", "600729.SH", "002419.SZ", "600697.SH", "600827.SH", "000501.SZ", "600785.SH"],
}


def generate_mock_stock_data(
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    trend_bias: float = 0.0002
) -> Dict[str, List[BarData]]:
    """生成模拟股票数据"""
    print(f"生成 {len(symbols)} 只股票模拟数据...")
    print(f"时间范围: {start_date.date()} 至 {end_date.date()}")

    all_data = {}
    dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    print(f"交易日数量: {len(dates)}")

    for symbol in symbols:
        try:
            base_price = random.uniform(10, 200)
            volatility = random.uniform(0.015, 0.035)
            bars = []
            current_price = base_price

            # 使用正确的 vt_symbol 格式
            vt_symbol = get_vt_symbol(symbol)

            for date in dates:
                daily_return = np.random.normal(trend_bias, volatility)
                open_price = current_price * (1 + np.random.normal(0, volatility * 0.3))
                close_price = current_price * (1 + daily_return)
                high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, volatility * 0.2)))
                low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, volatility * 0.2)))
                volume = random.uniform(1000000, 10000000)

                bar = BarData(
                    symbol=symbol.split(".")[0],
                    exchange=get_exchange_from_symbol(symbol),
                    datetime=date,
                    interval=Interval.DAILY,
                    open_price=round(open_price, 2),
                    high_price=round(high_price, 2),
                    low_price=round(low_price, 2),
                    close_price=round(close_price, 2),
                    volume=round(volume, 0),
                    open_interest=0,
                    gateway_name="BACKTEST"
                )
                bars.append(bar)
                current_price = close_price

            all_data[vt_symbol] = bars
        except Exception as e:
            print(f"生成 {symbol} 数据失败: {e}")

    print(f"成功生成 {len(all_data)} 只股票数据")
    return all_data


def run_strategy_backtest(
    strategy_class,
    strategy_name: str,
    strategy_params: dict,
    data: Dict[str, List[BarData]],
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = 10_000_000.0
) -> dict:
    """运行策略回测并返回结果"""
    print(f"\n{'='*60}")
    print(f"策略回测: {strategy_name}")
    print(f"{'='*60}")

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=0.0003,
        slippage=0.0001,
    )

    engine = BacktestEngine(config)

    for symbol, bars in data.items():
        engine.add_data(symbol, bars)

    engine.set_strategy(strategy_class, strategy_params)

    try:
        engine.run_backtesting()
        # 从评估器获取结果
        metrics = engine.evaluator.calculate_metrics()

        return {
            "strategy_name": strategy_name,
            "initial_capital": initial_capital,
            "final_capital": engine.balance,
            "total_return": metrics.total_return,
            "annual_return": metrics.annual_return,
            "max_drawdown": metrics.max_drawdown,
            "sharpe_ratio": metrics.sharpe_ratio,
            "win_rate": metrics.win_rate,
            "profit_loss_ratio": metrics.profit_loss_ratio,
            "total_trades": metrics.total_trades,
            "winning_trades": metrics.max_consecutive_wins,
            "losing_trades": metrics.max_consecutive_losses,
        }
    except Exception as e:
        print(f"回测失败: {e}")
        traceback.print_exc()
        return None


def print_backtest_result(result: dict, strategy_name: str):
    """打印回测结果"""
    if not result:
        print("回测结果为空")
        return 0

    print(f"\n{'='*60}")
    print(f"回测结果: {strategy_name}")
    print(f"{'='*60}")

    print(f"\n【收益指标】")
    print(f"  初始资金: {result['initial_capital']:,.2f}")
    print(f"  最终资金: {result['final_capital']:,.2f}")
    print(f"  总收益率: {result['total_return']:+.2%}")
    print(f"  年化收益率: {result['annual_return']:+.2%}")
    print(f"  目标年化(100%): {'✓ 达成' if result['annual_return'] >= 1.0 else '✗ 未达成'}")

    print(f"\n【风险指标】")
    print(f"  最大回撤: {result['max_drawdown']:.2%}")
    print(f"  夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"  胜率: {result['win_rate']:.2%}")
    print(f"  盈亏比: {result['profit_loss_ratio']:.2f}")

    print(f"\n【交易统计】")
    print(f"  总交易次数: {result['total_trades']}")

    print(f"\n【综合评估】")
    score = 0

    if result['annual_return'] >= 1.0:
        score += 40
        print(f"  ✓ 年化收益率达标 (+40分)")
    elif result['annual_return'] >= 0.5:
        score += 25
        print(f"  △ 年化收益率较好 (+25分)")
    elif result['annual_return'] > 0:
        score += 10
        print(f"  △ 年化收益率一般 (+10分)")
    else:
        print(f"  ✗ 年化收益率为负 (0分)")

    if result['max_drawdown'] <= 0.20:
        score += 20
        print(f"  ✓ 最大回撤控制良好 (+20分)")
    elif result['max_drawdown'] <= 0.30:
        score += 10
        print(f"  △ 最大回撤一般 (+10分)")
    else:
        print(f"  ✗ 最大回撤过大 (0分)")

    if result['sharpe_ratio'] >= 2.0:
        score += 20
        print(f"  ✓ 夏普比率优秀 (+20分)")
    elif result['sharpe_ratio'] >= 1.0:
        score += 10
        print(f"  △ 夏普比率一般 (+10分)")
    else:
        print(f"  ✗ 夏普比率较低 (0分)")

    if result['win_rate'] >= 0.55:
        score += 20
        print(f"  ✓ 胜率较高 (+20分)")
    elif result['win_rate'] >= 0.45:
        score += 10
        print(f"  △ 胜率一般 (+10分)")
    else:
        print(f"  ✗ 胜率较低 (0分)")

    print(f"\n  综合评分: {score}/100")

    if score >= 80:
        print(f"  评级: ★★★★★ 优秀策略")
    elif score >= 60:
        print(f"  评级: ★★★★☆ 良好策略")
    elif score >= 40:
        print(f"  评级: ★★★☆☆ 一般策略")
    else:
        print(f"  评级: ★★☆☆☆ 需优化")

    return score


def compare_strategies(results: List[dict]):
    """对比多个策略的结果"""
    print(f"\n{'='*80}")
    print("策略对比分析")
    print(f"{'='*80}")

    comparison_data = []
    for result in results:
        if result:
            comparison_data.append({
                "策略": result['strategy_name'],
                "总收益率": f"{result['total_return']:+.2%}",
                "年化收益率": f"{result['annual_return']:+.2%}",
                "最大回撤": f"{result['max_drawdown']:.2%}",
                "夏普比率": f"{result['sharpe_ratio']:.2f}",
                "胜率": f"{result['win_rate']:.2%}",
                "交易次数": result['total_trades'],
            })

    df = pd.DataFrame(comparison_data)
    print("\n", df.to_string(index=False))

    valid_results = [r for r in results if r is not None]

    if valid_results:
        best_annual = max(valid_results, key=lambda x: x['annual_return'])
        best_sharpe = max(valid_results, key=lambda x: x['sharpe_ratio'])

        print(f"\n【最优策略】")
        print(f"  最高年化收益: {best_annual['strategy_name']} ({best_annual['annual_return']:+.2%})")
        print(f"  最高夏普比率: {best_sharpe['strategy_name']} ({best_sharpe['sharpe_ratio']:.2f})")

        # 综合推荐
        print(f"\n【策略推荐】")
        strategy_scores = {}
        for result in valid_results:
            score = 0
            score += min(result['annual_return'] * 40, 40)
            score += min(result['sharpe_ratio'] * 10, 20)
            score += max(0, 20 - result['max_drawdown'] * 100)
            score += result['win_rate'] * 20
            strategy_scores[result['strategy_name']] = score

        recommended = max(strategy_scores.items(), key=lambda x: x[1])
        print(f"  综合推荐: {recommended[0]} (得分: {recommended[1]:.1f})")

        return recommended[0]

    return None


def save_results_to_json(results: List[dict], filename: str):
    """保存回测结果到JSON"""
    output = {}
    for result in results:
        if result:
            output[result['strategy_name']] = result

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {filename}")


def main():
    """主函数"""
    print("="*80)
    print("AlphaX - 100只A股标的策略回测验证")
    print("目标: 验证策略是否能达到年化100%收益")
    print("="*80)

    # 设置时间范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*2)  # 2年历史数据

    print(f"\n回测时间范围: {start_date.date()} 至 {end_date.date()}")

    # 获取所有标的
    all_symbols = []
    for sector, stocks in STOCKS_100.items():
        all_symbols.extend(stocks)

    print(f"标的数量: {len(all_symbols)} 只")
    print("\n行业分布:")
    for sector, stocks in STOCKS_100.items():
        print(f"  {sector}: {len(stocks)}只")

    # 生成模拟数据
    print("\n" + "="*80)
    stock_data = generate_mock_stock_data(all_symbols, start_date, end_date, trend_bias=0.0003)

    if not stock_data:
        print("\n错误: 未能生成股票数据")
        return

    print(f"\n实际回测标的数量: {len(stock_data)} 只")

    # 策略参数配置
    strategies_config = [
        {
            "name": "多因子动量策略",
            "class": MultiFactorMomentumStrategy,
            "params": {
                "lookback_period": 20,
                "price_momentum_weight": 0.4,
                "volume_momentum_weight": 0.2,
                "vol_adj_momentum_weight": 0.3,
                "trend_strength_weight": 0.1,
                "long_threshold": 0.3,
                "short_threshold": -0.3,
                "exit_threshold": 0.05,
            }
        },
        {
            "name": "突破策略",
            "class": BreakoutStrategy,
            "params": {
                "breakout_type": "channel",
                "channel_period": 20,
                "atr_period": 14,
                "atr_multiplier": 2.0,
                "use_volume_filter": True,
                "volume_threshold": 1.5,
                "use_trend_filter": True,
                "trend_period": 20,
                "use_whipsaw_filter": True,
                "use_trailing_stop": True,
                "trailing_stop_atr_mult": 3.0,
            }
        },
        {
            "name": "双均线策略",
            "class": MovingAverageStrategy,
            "params": {
                "fast_window": 10,
                "slow_window": 20,
            }
        },
    ]

    # 运行回测
    results = []

    for config in strategies_config:
        try:
            result = run_strategy_backtest(
                strategy_class=config["class"],
                strategy_name=config["name"],
                strategy_params=config["params"],
                data=stock_data,
                start_date=start_date,
                end_date=end_date,
                initial_capital=10_000_000.0,
            )

            if result:
                results.append(result)
                print_backtest_result(result, config["name"])

        except Exception as e:
            print(f"\n策略 {config['name']} 回测失败: {e}")
            traceback.print_exc()

    # 策略对比
    if results:
        recommended_strategy = compare_strategies(results)

        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"data/backtest_results/100stocks_comparison_{timestamp}.json"
        save_results_to_json(results, result_file)

        # 总结
        print(f"\n{'='*80}")
        print("回测总结")
        print(f"{'='*80}")
        print(f"回测标的: {len(stock_data)} 只A股（模拟数据）")
        print(f"时间范围: {start_date.date()} 至 {end_date.date()}")
        print(f"测试策略: {len(results)} 个")

        if recommended_strategy:
            print(f"\n推荐策略: {recommended_strategy}")
            rec_result = next(r for r in results if r['strategy_name'] == recommended_strategy)
            print(f"  - 年化收益率: {rec_result['annual_return']:+.2%}")
            print(f"  - 距离目标(100%): {(rec_result['annual_return'] - 1.0):+.2%}")

            if rec_result['annual_return'] >= 1.0:
                print(f"\n✓ 恭喜！策略已达到年化100%收益目标！")
            else:
                gap = 1.0 - rec_result['annual_return']
                print(f"\n△ 策略年化收益率为 {rec_result['annual_return']:.2%}")
                print(f"  距离100%目标还差 {gap:.2%}")
                print(f"\n建议:")
                print(f"  1. 优化策略参数")
                print(f"  2. 尝试策略组合")
                print(f"  3. 增加更多因子")
                print(f"  4. 优化仓位管理")

    print(f"\n{'='*80}")
    print("回测完成")
    print("="*80)


if __name__ == "__main__":
    main()
