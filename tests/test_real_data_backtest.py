"""
真实数据回测验证

使用AKShare获取真实A股历史数据，验证策略有效性
目标：年化收益率100%（一年一倍）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Dict
import json

import numpy as np
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange

from alphax.backtest.engine import BacktestEngine, BacktestConfig
from alphax.risk import RiskLimits
from alphax.position import PositionConfig
from alphax.strategies.momentum_strategy import MultiFactorMomentumStrategy
from alphax.strategies.breakout_strategy import BreakoutStrategy
from alphax.strategies.moving_average_strategy import MovingAverageStrategy

# 尝试导入AKShare
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("警告：AKShare未安装，将使用模拟数据")


def get_stock_data_akshare(
    symbol: str,
    start_date: str,
    end_date: str
) -> List[BarData]:
    """
    使用AKShare获取股票历史数据
    
    Args:
        symbol: 股票代码（如：600519）
        start_date: 开始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）
    
    Returns:
        BarData列表
    """
    if not AKSHARE_AVAILABLE:
        raise ImportError("AKShare未安装")
    
    # 获取日K线数据
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="qfq"  # 前复权
    )
    
    if df.empty:
        raise ValueError(f"未获取到{symbol}的数据")
    
    bars = []
    for _, row in df.iterrows():
        bar = BarData(
            symbol=symbol,
            exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
            datetime=pd.to_datetime(row["日期"]),
            interval="d",
            volume=int(row["成交量"]),
            open_price=float(row["开盘"]),
            high_price=float(row["最高"]),
            low_price=float(row["最低"]),
            close_price=float(row["收盘"]),
            gateway_name="AKSHARE"
        )
        bar.vt_symbol = f"{symbol}.{bar.exchange.value}"
        bars.append(bar)
    
    return bars


def run_strategy_backtest(
    strategy_class,
    strategy_name: str,
    strategy_params: dict,
    symbol: str,
    bars: List[BarData],
    initial_capital: float = 1_000_000.0
) -> dict:
    """
    运行单策略回测
    
    Args:
        strategy_class: 策略类
        strategy_name: 策略名称
        strategy_params: 策略参数
        symbol: 标的代码
        bars: K线数据
        initial_capital: 初始资金
    
    Returns:
        回测结果字典
    """
    if not bars:
        return {"error": "无数据"}
    
    start_date = bars[0].datetime
    end_date = bars[-1].datetime
    
    # 创建回测配置
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=0.0003,  # 手续费0.03%
        slippage=0.0001,         # 滑点0.01%
        risk_limits=RiskLimits(),
        position_config=PositionConfig()
    )
    
    # 创建回测引擎
    engine = BacktestEngine(config)
    vt_symbol = bars[0].vt_symbol
    engine.add_data(vt_symbol, bars)
    engine.set_strategy(strategy_class, strategy_params)
    
    # 运行回测
    engine.run_backtesting()
    
    # 获取结果
    result = engine.get_result()
    
    return {
        "strategy_name": strategy_name,
        "symbol": symbol,
        "period": f"{start_date.date()} to {end_date.date()}",
        "total_days": len(bars),
        "result": result
    }


def analyze_backtest_result(backtest_result: dict) -> dict:
    """
    分析回测结果
    
    Args:
        backtest_result: 回测结果
    
    Returns:
        分析结果
    """
    if "error" in backtest_result:
        return {"error": backtest_result["error"]}
    
    result = backtest_result["result"]
    perf = result.get("performance", {})
    metrics = perf.get("metrics", {})
    stats = result.get("statistics", {})
    
    # 提取关键指标
    total_return = metrics.get("total_return", 0)
    annual_return = metrics.get("annual_return", 0)
    sharpe_ratio = metrics.get("sharpe_ratio", 0)
    max_drawdown = metrics.get("max_drawdown", 0)
    win_rate = metrics.get("win_rate", 0)
    
    # 目标对比（年化100%）
    target_return = 1.0  # 100%
    target_sharpe = 2.0
    target_max_dd = 0.20
    
    return {
        "strategy": backtest_result["strategy_name"],
        "symbol": backtest_result["symbol"],
        "period": backtest_result["period"],
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "total_trades": stats.get("total_trades", 0),
        "final_balance": stats.get("final_balance", 0),
        "target_return": target_return,
        "target_sharpe": target_sharpe,
        "target_max_dd": target_max_dd,
        "return_achievement": annual_return / target_return if target_return > 0 else 0,
        "sharpe_achievement": sharpe_ratio / target_sharpe if target_sharpe > 0 else 0,
        "passed": annual_return >= target_return and sharpe_ratio >= target_sharpe and max_drawdown <= target_max_dd
    }


def run_comprehensive_backtest():
    """
    运行综合回测测试
    测试多个策略在多个标的上的表现
    """
    print("=" * 80)
    print("AlphaX 真实数据回测验证")
    print("目标：年化收益率100%（一年一倍）")
    print("=" * 80)
    
    # 检查AKShare
    if not AKSHARE_AVAILABLE:
        print("\n错误：AKShare未安装，请先安装：pip install akshare")
        return
    
    # 测试标的（选择流动性好的大盘股）
    test_symbols = {
        "600519": "贵州茅台",
        "000858": "五粮液",
        "000001": "平安银行",
        "600036": "招商银行",
        "000333": "美的集团",
    }
    
    # 回测区间（最近3年）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*3)
    
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    print(f"\n回测区间：{start_date_str} 至 {end_date_str}")
    print(f"测试标的数：{len(test_symbols)}")
    
    # 策略配置
    strategies = [
        {
            "class": MultiFactorMomentumStrategy,
            "name": "多因子动量策略",
            "params": {
                "lookback_period": 20,
                "price_momentum_weight": 0.4,
                "volume_momentum_weight": 0.2,
                "vol_adj_momentum_weight": 0.3,
                "trend_strength_weight": 0.1,
                "long_threshold": 0.3,
                "short_threshold": -0.3,
                "exit_threshold": 0.05
            }
        },
        {
            "class": BreakoutStrategy,
            "name": "突破策略",
            "params": {
                "channel_period": 20,
                "breakout_threshold": 0.02,
                "volume_confirm": True,
                "volume_threshold": 1.5,
                "atr_period": 14,
                "atr_multiplier": 2.0
            }
        },
        {
            "class": MovingAverageStrategy,
            "name": "均线策略",
            "params": {
                "fast_window": 10,
                "slow_window": 30,
                "signal_threshold": 0.01
            }
        }
    ]
    
    # 存储所有结果
    all_results = []
    
    # 遍历每个标的
    for symbol, name in test_symbols.items():
        print(f"\n{'='*60}")
        print(f"测试标的：{name} ({symbol})")
        print('='*60)
        
        try:
            # 获取数据
            print(f"正在获取数据...")
            bars = get_stock_data_akshare(symbol, start_date_str, end_date_str)
            print(f"获取到 {len(bars)} 条数据")
            
            # 测试每个策略
            for strategy_config in strategies:
                print(f"\n  测试策略：{strategy_config['name']}")
                
                try:
                    # 运行回测
                    backtest_result = run_strategy_backtest(
                        strategy_config["class"],
                        strategy_config["name"],
                        strategy_config["params"],
                        symbol,
                        bars
                    )
                    
                    # 分析结果
                    analysis = analyze_backtest_result(backtest_result)
                    all_results.append(analysis)
                    
                    # 打印结果
                    if "error" not in analysis:
                        print(f"    年化收益率：{analysis['annual_return']:.2%} (目标：{analysis['target_return']:.0%})")
                        print(f"    夏普比率：{analysis['sharpe_ratio']:.2f} (目标：{analysis['target_sharpe']:.1f})")
                        print(f"    最大回撤：{analysis['max_drawdown']:.2%} (限制：{analysis['target_max_dd']:.0%})")
                        print(f"    胜率：{analysis['win_rate']:.2%}")
                        print(f"    交易次数：{analysis['total_trades']}")
                        status = "✓ 通过" if analysis['passed'] else "✗ 未通过"
                        print(f"    状态：{status}")
                    else:
                        print(f"    错误：{analysis['error']}")
                
                except Exception as e:
                    print(f"    回测失败：{e}")
        
        except Exception as e:
            print(f"  获取数据失败：{e}")
    
    # 汇总分析
    print("\n" + "=" * 80)
    print("汇总分析")
    print("=" * 80)
    
    if all_results:
        # 按策略分组统计
        strategy_stats = {}
        for result in all_results:
            if "error" in result:
                continue
            strategy = result["strategy"]
            if strategy not in strategy_stats:
                strategy_stats[strategy] = []
            strategy_stats[strategy].append(result)
        
        print("\n【各策略表现】")
        best_strategy = None
        best_avg_return = -float('inf')
        
        for strategy_name, results in strategy_stats.items():
            avg_return = np.mean([r["annual_return"] for r in results])
            avg_sharpe = np.mean([r["sharpe_ratio"] for r in results])
            avg_drawdown = np.mean([r["max_drawdown"] for r in results])
            pass_rate = sum([r["passed"] for r in results]) / len(results)
            
            print(f"\n  {strategy_name}:")
            print(f"    平均年化收益率：{avg_return:.2%}")
            print(f"    平均夏普比率：{avg_sharpe:.2f}")
            print(f"    平均最大回撤：{avg_drawdown:.2%}")
            print(f"    通过率：{pass_rate:.1%}")
            
            # 记录最优策略
            if avg_return > best_avg_return:
                best_avg_return = avg_return
                best_strategy = {
                    "name": strategy_name,
                    "avg_return": avg_return,
                    "avg_sharpe": avg_sharpe,
                    "avg_drawdown": avg_drawdown,
                    "pass_rate": pass_rate
                }
        
        # 找出最优策略
        print("\n【最优策略】")
        if best_strategy:
            print(f"  策略名称：{best_strategy['name']}")
            print(f"  平均年化收益率：{best_strategy['avg_return']:.2%}")
            print(f"  平均夏普比率：{best_strategy['avg_sharpe']:.2f}")
            print(f"  平均最大回撤：{best_strategy['avg_drawdown']:.2%}")
            print(f"  通过率：{best_strategy['pass_rate']:.1%}")
            
            # 保存最优策略信息
            save_best_strategy(best_strategy)
        
        # 目标达成情况
        total_tests = len([r for r in all_results if "error" not in r])
        passed_tests = len([r for r in all_results if r.get("passed", False)])
        
        print(f"\n【目标达成情况】")
        print(f"  总测试次数：{total_tests}")
        print(f"  通过次数：{passed_tests}")
        print(f"  整体通过率：{passed_tests/total_tests:.1%}" if total_tests > 0 else "  无有效测试")
        
        # 保存详细结果
        save_detailed_results(all_results)
    else:
        print("\n  无有效回测结果")


def save_best_strategy(best_strategy: dict):
    """保存最优策略信息到文档"""
    doc_content = f"""# AlphaX 最优策略报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 当前最优策略

**策略名称**：{best_strategy['name']}

## 性能指标

| 指标 | 数值 | 目标 | 状态 |
|------|------|------|------|
| 平均年化收益率 | {best_strategy['avg_return']:.2%} | 100% | {'✓ 达成' if best_strategy['avg_return'] >= 1.0 else '✗ 未达成'} |
| 平均夏普比率 | {best_strategy['avg_sharpe']:.2f} | 2.0 | {'✓ 达成' if best_strategy['avg_sharpe'] >= 2.0 else '✗ 未达成'} |
| 平均最大回撤 | {best_strategy['avg_drawdown']:.2%} | ≤20% | {'✓ 通过' if best_strategy['avg_drawdown'] <= 0.20 else '✗ 超标'} |
| 测试通过率 | {best_strategy['pass_rate']:.1%} | - | - |

## 策略说明

{best_strategy['name']}在回测中表现最优，建议：

1. **优先实盘测试**：使用该策略进行小资金实盘验证
2. **参数优化**：进一步优化策略参数
3. **组合配置**：考虑与其他策略组合使用

## 风险提示

- 回测结果不代表未来表现
- 建议先用小资金实盘测试
- 严格遵循风险管理规则

---
*本报告由AlphaX系统自动生成*
"""
    
    # 保存到开发记录目录
    os.makedirs("ai_docs/开发记录", exist_ok=True)
    filepath = f"ai_docs/开发记录/{datetime.now().strftime('%Y-%m-%d')}-最优策略报告.md"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(doc_content)
    
    print(f"\n  最优策略报告已保存：{filepath}")


def save_detailed_results(all_results: list):
    """保存详细回测结果"""
    # 转换为DataFrame
    df_data = []
    for result in all_results:
        if "error" not in result:
            df_data.append({
                "strategy": result["strategy"],
                "symbol": result["symbol"],
                "annual_return": result["annual_return"],
                "sharpe_ratio": result["sharpe_ratio"],
                "max_drawdown": result["max_drawdown"],
                "win_rate": result["win_rate"],
                "total_trades": result["total_trades"],
                "passed": result["passed"]
            })
    
    if df_data:
        df = pd.DataFrame(df_data)
        
        # 保存为CSV
        os.makedirs("data/backtest_results", exist_ok=True)
        csv_path = f"data/backtest_results/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"\n  详细结果已保存：{csv_path}")
        
        # 保存为JSON
        json_path = f"data/backtest_results/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(df_data, f, ensure_ascii=False, indent=2)
        print(f"  JSON结果已保存：{json_path}")


if __name__ == "__main__":
    run_comprehensive_backtest()
