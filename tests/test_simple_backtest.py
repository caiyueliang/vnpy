"""
简化的策略回测验证

使用简化的资金管理逻辑，避免复杂的冻结资金计算
"""

import sys
import traceback
from datetime import datetime, timedelta
from typing import Dict, List
import json

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
from alphax.risk import RiskLimits
from alphax.position import PositionConfig

from data.realistic_data_generator import RealisticDataGenerator, STOCKS_100


def run_simple_backtest(
    strategy_class,
    strategy_name: str,
    strategy_params: dict,
    data: Dict[str, List[BarData]],
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = 1_000_000.0
) -> dict:
    """
    运行简化的回测
    
    简化逻辑：
    1. 不使用冻结资金
    2. 直接从balance扣除/增加交易金额
    3. 持仓盈亏通过市值变化计算
    """
    print(f"\n{'='*60}")
    print(f"策略回测: {strategy_name}")
    print(f"{'='*60}")

    # 禁用风控，专注于策略逻辑
    risk_limits = RiskLimits(
        max_single_position_pct=1.0,  # 禁用持仓限制
        max_daily_loss_pct=1.0,  # 禁用日亏损限制
        max_total_loss_pct=1.0,  # 禁用总亏损限制
        max_strategy_drawdown_pct=1.0,  # 禁用策略回撤限制
        max_single_trade_loss_pct=1.0,  # 禁用单笔亏损限制
        max_order_size=1000000,  # 禁用订单数量限制
    )

    # 简化仓位配置
    position_config = PositionConfig(
        base_position=0.05,  # 基础仓位 5%
        max_position=0.10,   # 最大仓位 10%
        risk_per_trade=0.02,
    )

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=0.0003,
        slippage=0.0001,
        risk_limits=risk_limits,
        position_config=position_config,
    )

    engine = BacktestEngine(config)

    for symbol, bars in data.items():
        engine.add_data(symbol, bars)

    engine.set_strategy(strategy_class, strategy_params)

    try:
        engine.run_backtesting()
        
        # 手动计算绩效指标
        metrics = engine.evaluator.calculate_metrics()
        
        # 手动计算收益率
        if len(engine.daily_results) > 0:
            final_balance = engine.balance
            total_return = (final_balance - initial_capital) / initial_capital
            
            # 计算年化收益率
            days = len(engine.daily_results)
            annual_return = (1 + total_return) ** (252 / days) - 1 if days > 0 else 0
            
            # 计算每日收益率序列
            daily_returns = []
            prev_balance = initial_capital
            for date, result in sorted(engine.daily_results.items()):
                if result.balance > 0:
                    daily_ret = (result.balance - prev_balance) / prev_balance
                    daily_returns.append(daily_ret)
                    prev_balance = result.balance
            
            if daily_returns:
                returns_series = pd.Series(daily_returns)
                metrics.total_return = total_return
                metrics.annual_return = annual_return
                metrics.daily_return_mean = float(np.mean(daily_returns))
                metrics.daily_return_std = float(np.std(daily_returns))
                
                # 计算最大回撤
                cumulative = (1 + returns_series).cumprod()
                running_max = cumulative.expanding().max()
                drawdown = (cumulative - running_max) / running_max
                metrics.max_drawdown = float(drawdown.min())
                
                # 计算夏普比率
                if metrics.daily_return_std > 0:
                    excess_return = metrics.daily_return_mean - 0.03 / 252
                    metrics.sharpe_ratio = excess_return / metrics.daily_return_std * np.sqrt(252)
        
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
    print("AlphaX - 100只A股标的策略回测验证（简化版本）")
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

    # 数据层：生成改进的模拟数据
    print("\n" + "="*80)
    print("数据层：开始生成改进的模拟数据")
    print("="*80)
    
    data_generator = RealisticDataGenerator(seed=42)
    
    stock_data = data_generator.generate_multiple_stocks(
        symbols=all_symbols,
        start_date=start_date,
        end_date=end_date,
        progress_callback=lambda i, total, symbol, count: 
            print(f"[{i}/{total}] {symbol} ({count}条)")
    )

    if len(stock_data) < 50:
        print(f"\n警告: 仅生成 {len(stock_data)} 只股票数据，数量不足")
        return

    print(f"\n实际回测标的数量: {len(stock_data)} 只")

    # 策略参数配置（优化参数）
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
                "long_threshold": 0.2,
                "short_threshold": -0.2,
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

    # 策略层：运行回测
    print("\n" + "="*80)
    print("策略层：开始策略回测")
    print("="*80)
    
    results = []

    for config in strategies_config:
        try:
            result = run_simple_backtest(
                strategy_class=config["class"],
                strategy_name=config["name"],
                strategy_params=config["params"],
                data=stock_data,
                start_date=start_date,
                end_date=end_date,
                initial_capital=1_000_000.0,  # 降低初始资金，避免数值过大
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
        result_file = f"data/backtest_results/100stocks_simple_{timestamp}.json"
        save_results_to_json(results, result_file)

        # 总结
        print(f"\n{'='*80}")
        print("回测总结")
        print(f"{'='*80}")
        print(f"回测标的: {len(stock_data)} 只A股（改进模拟数据）")
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
