"""
100只A股标的策略回测验证

使用分布在各行业的100只A股进行策略回测，验证策略有效性
目标：验证是否能达到年化100%收益目标
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
from alphax.backtest.result import BacktestResult
from alphax.strategies.momentum_strategy import MultiFactorMomentumStrategy
from alphax.strategies.breakout_strategy import BreakoutStrategy
from alphax.strategies.moving_average_strategy import MovingAverageStrategy
from data.collectors.akshare_collector import AKShareCollector
from data.collectors.base import CollectorConfig, DataSource
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval


def get_exchange_from_symbol(symbol: str) -> Exchange:
    """根据标的代码获取交易所"""
    if ".SH" in symbol:
        return Exchange.SSE  # 上海证券交易所
    elif ".SZ" in symbol:
        return Exchange.SZSE  # 深圳证券交易所
    return Exchange.SZSE


# 100只分布在各行业的A股标的
STOCKS_100 = {
    # 白酒/食品饮料 (10只)
    "白酒": [
        "600519.SH",  # 贵州茅台
        "000858.SZ",  # 五粮液
        "000568.SZ",  # 泸州老窖
        "002304.SZ",  # 洋河股份
        "600809.SH",  # 山西汾酒
        "600887.SH",  # 伊利股份
        "603288.SH",  # 海天味业
        "600276.SH",  # 恒瑞医药
        "000538.SZ",  # 云南白药
        "603259.SH",  # 药明康德
    ],
    # 银行/金融 (10只)
    "银行金融": [
        "600036.SH",  # 招商银行
        "601398.SH",  # 工商银行
        "601288.SH",  # 农业银行
        "601939.SH",  # 建设银行
        "601988.SH",  # 中国银行
        "601318.SH",  # 中国平安
        "601628.SH",  # 中国人寿
        "600030.SH",  # 中信证券
        "601688.SH",  # 华泰证券
        "600837.SH",  # 海通证券
    ],
    # 新能源/电力 (10只)
    "新能源": [
        "300750.SZ",  # 宁德时代
        "601012.SH",  # 隆基绿能
        "600438.SH",  # 通威股份
        "002594.SZ",  # 比亚迪
        "601669.SH",  # 中国电建
        "601727.SH",  # 上海电气
        "600900.SH",  # 长江电力
        "601985.SH",  # 中国核电
        "600011.SH",  # 华能国际
        "601016.SH",  # 节能风电
    ],
    # 科技/半导体 (10只)
    "科技半导体": [
        "688981.SH",  # 中芯国际
        "603501.SH",  # 韦尔股份
        "002371.SZ",  # 北方华创
        "688012.SH",  # 中微公司
        "603986.SH",  # 兆易创新
        "002049.SZ",  # 紫光国微
        "688008.SH",  # 澜起科技
        "300782.SZ",  # 卓胜微
        "600584.SH",  # 长电科技
        "002156.SZ",  # 通富微电
    ],
    # 汽车/制造 (10只)
    "汽车制造": [
        "601127.SH",  # 赛力斯
        "000625.SZ",  # 长安汽车
        "600104.SH",  # 上汽集团
        "601633.SH",  # 长城汽车
        "601238.SH",  # 广汽集团
        "000338.SZ",  # 潍柴动力
        "600660.SH",  # 福耀玻璃
        "601766.SH",  # 中国中车
        "601989.SH",  # 中国重工
        "600031.SH",  # 三一重工
    ],
    # 房地产/基建 (10只)
    "房地产基建": [
        "000002.SZ",  # 万科A
        "600048.SH",  # 保利发展
        "001979.SZ",  # 招商蛇口
        "600606.SH",  # 绿地控股
        "601668.SH",  # 中国建筑
        "601390.SH",  # 中国中铁
        "601800.SH",  # 中国交建
        "601186.SH",  # 中国铁建
        "601117.SH",  # 中国化学
        "600170.SH",  # 上海建工
    ],
    # 石油/化工 (10只)
    "石油化工": [
        "601857.SH",  # 中国石油
        "600028.SH",  # 中国石化
        "600938.SH",  # 中国海油
        "002493.SZ",  # 荣盛石化
        "600346.SH",  # 恒力石化
        "600309.SH",  # 万华化学
        "002648.SZ",  # 卫星化学
        "600426.SH",  # 华鲁恒升
        "601233.SH",  # 桐昆股份
        "603225.SH",  # 新凤鸣
    ],
    # 有色/钢铁 (10只)
    "有色钢铁": [
        "601899.SH",  # 紫金矿业
        "603993.SH",  # 洛阳钼业
        "600111.SH",  # 北方稀土
        "600362.SH",  # 江西铜业
        "601600.SH",  # 中国铝业
        "600019.SH",  # 宝钢股份
        "000932.SZ",  # 华菱钢铁
        "600507.SH",  # 方大特钢
        "002110.SZ",  # 三钢闽光
        "600808.SH",  # 马钢股份
    ],
    # 通信/传媒 (10只)
    "通信传媒": [
        "600941.SH",  # 中国移动
        "600050.SH",  # 中国联通
        "601728.SH",  # 中国电信
        "000063.SZ",  # 中兴通讯
        "600498.SH",  # 烽火通信
        "603444.SH",  # 吉比特
        "002624.SZ",  # 完美世界
        "300413.SZ",  # 芒果超媒
        "002027.SZ",  # 分众传媒
        "600088.SH",  # 中视传媒
    ],
    # 消费/零售 (10只)
    "消费零售": [
        "601888.SH",  # 中国中免
        "600859.SH",  # 王府井
        "002024.SZ",  # 苏宁易购
        "601933.SH",  # 永辉超市
        "600729.SH",  # 重庆百货
        "002419.SZ",  # 天虹股份
        "600697.SH",  # 欧亚集团
        "600827.SH",  # 百联股份
        "000501.SZ",  # 武商集团
        "600785.SH",  # 新华百货
    ],
}


def get_all_symbols() -> List[str]:
    """获取所有100只标的代码"""
    symbols = []
    for sector, stocks in STOCKS_100.items():
        symbols.extend(stocks)
    return symbols


def download_stock_data(
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    interval: str = "d"
) -> Dict[str, List[BarData]]:
    """
    下载股票历史数据

    Args:
        symbols: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期
        interval: 数据周期

    Returns:
        股票数据字典
    """
    print(f"开始下载 {len(symbols)} 只股票数据...")
    print(f"时间范围: {start_date.date()} 至 {end_date.date()}")

    collector = AKShareCollector()
    if not collector.connect():
        print("AKShare连接失败")
        return {}

    all_data = {}
    success_count = 0
    failed_symbols = []

    for i, symbol in enumerate(symbols, 1):
        try:
            print(f"[{i}/{len(symbols)}] 下载 {symbol}...", end=" ")

            bars = collector.get_bar_data(symbol, interval, start_date, end_date)

            if bars and len(bars) > 50:  # 至少50根K线
                # 转换为BarData对象
                bar_objects = []
                exchange = get_exchange_from_symbol(symbol)
                for bar in bars:
                    bar_obj = BarData(
                        symbol=symbol.split(".")[0],
                        exchange=exchange,
                        datetime=bar["datetime"],
                        interval=Interval.DAILY,
                        open_price=bar["open"],
                        high_price=bar["high"],
                        low_price=bar["low"],
                        close_price=bar["close"],
                        volume=bar["volume"],
                        open_interest=0,
                        gateway_name="BACKTEST"
                    )
                    bar_objects.append(bar_obj)

                all_data[symbol] = bar_objects
                success_count += 1
                print(f"✓ ({len(bar_objects)}条)")
            else:
                print(f"✗ (数据不足)")
                failed_symbols.append(symbol)

        except Exception as e:
            print(f"✗ (错误: {e})")
            failed_symbols.append(symbol)

    collector.disconnect()

    print(f"\n数据下载完成: {success_count}/{len(symbols)} 只股票")
    if failed_symbols:
        print(f"失败标的: {failed_symbols}")

    return all_data


def run_strategy_backtest(
    strategy_class,
    strategy_name: str,
    strategy_params: dict,
    data: Dict[str, List[BarData]],
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = 10_000_000.0
) -> BacktestResult:
    """
    运行策略回测

    Args:
        strategy_class: 策略类
        strategy_name: 策略名称
        strategy_params: 策略参数
        data: 股票数据
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金

    Returns:
        回测结果
    """
    print(f"\n{'='*60}")
    print(f"策略回测: {strategy_name}")
    print(f"{'='*60}")

    # 创建回测配置
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=0.0003,  # 0.03%
        slippage=0.0001,  # 0.01%
    )

    # 创建回测引擎
    engine = BacktestEngine(config)

    # 添加数据
    for symbol, bars in data.items():
        engine.add_data(symbol, bars)

    # 设置策略
    engine.set_strategy(strategy_class, strategy_params)

    # 运行回测
    try:
        result = engine.run_backtest()
        return result
    except Exception as e:
        print(f"回测失败: {e}")
        traceback.print_exc()
        return None


def print_backtest_result(result: BacktestResult, strategy_name: str):
    """打印回测结果"""
    if not result:
        print("回测结果为空")
        return

    print(f"\n{'='*60}")
    print(f"回测结果: {strategy_name}")
    print(f"{'='*60}")

    # 基本指标
    print(f"\n【收益指标】")
    print(f"  初始资金: {result.initial_capital:,.2f}")
    print(f"  最终资金: {result.final_capital:,.2f}")
    print(f"  总收益率: {result.total_return:+.2%}")
    print(f"  年化收益率: {result.annual_return:+.2%}")
    print(f"  目标年化(100%): {'✓ 达成' if result.annual_return >= 1.0 else '✗ 未达成'}")

    # 风险指标
    print(f"\n【风险指标】")
    print(f"  最大回撤: {result.max_drawdown:.2%}")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    print(f"  胜率: {result.win_rate:.2%}")
    print(f"  盈亏比: {result.profit_loss_ratio:.2f}")

    # 交易统计
    print(f"\n【交易统计】")
    print(f"  总交易次数: {result.total_trades}")
    print(f"  盈利次数: {result.winning_trades}")
    print(f"  亏损次数: {result.losing_trades}")
    print(f"  平均持仓天数: {result.avg_holding_days:.1f}")

    # 评估
    print(f"\n【综合评估】")
    score = 0

    # 收益率评分
    if result.annual_return >= 1.0:
        score += 40
        print(f"  ✓ 年化收益率达标 (+40分)")
    elif result.annual_return >= 0.5:
        score += 25
        print(f"  △ 年化收益率较好 (+25分)")
    elif result.annual_return > 0:
        score += 10
        print(f"  △ 年化收益率一般 (+10分)")
    else:
        print(f"  ✗ 年化收益率为负 (0分)")

    # 风险评分
    if result.max_drawdown <= 0.20:
        score += 20
        print(f"  ✓ 最大回撤控制良好 (+20分)")
    elif result.max_drawdown <= 0.30:
        score += 10
        print(f"  △ 最大回撤一般 (+10分)")
    else:
        print(f"  ✗ 最大回撤过大 (0分)")

    # 夏普比率评分
    if result.sharpe_ratio >= 2.0:
        score += 20
        print(f"  ✓ 夏普比率优秀 (+20分)")
    elif result.sharpe_ratio >= 1.0:
        score += 10
        print(f"  △ 夏普比率一般 (+10分)")
    else:
        print(f"  ✗ 夏普比率较低 (0分)")

    # 胜率评分
    if result.win_rate >= 0.55:
        score += 20
        print(f"  ✓ 胜率较高 (+20分)")
    elif result.win_rate >= 0.45:
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


def compare_strategies(results: Dict[str, BacktestResult]):
    """对比多个策略的结果"""
    print(f"\n{'='*80}")
    print("策略对比分析")
    print(f"{'='*80}")

    # 创建对比表格
    comparison_data = []
    for name, result in results.items():
        if result:
            comparison_data.append({
                "策略": name,
                "总收益率": f"{result.total_return:+.2%}",
                "年化收益率": f"{result.annual_return:+.2%}",
                "最大回撤": f"{result.max_drawdown:.2%}",
                "夏普比率": f"{result.sharpe_ratio:.2f}",
                "胜率": f"{result.win_rate:.2%}",
                "交易次数": result.total_trades,
            })

    df = pd.DataFrame(comparison_data)
    print("\n", df.to_string(index=False))

    # 找出最优策略
    valid_results = {k: v for k, v in results.items() if v is not None}

    if valid_results:
        best_annual = max(valid_results.items(), key=lambda x: x[1].annual_return)
        best_sharpe = max(valid_results.items(), key=lambda x: x[1].sharpe_ratio)
        best_drawdown = min(valid_results.items(), key=lambda x: x[1].max_drawdown)

        print(f"\n【最优策略】")
        print(f"  最高年化收益: {best_annual[0]} ({best_annual[1].annual_return:+.2%})")
        print(f"  最高夏普比率: {best_sharpe[0]} ({best_sharpe[1].sharpe_ratio:.2f})")
        print(f"  最低最大回撤: {best_drawdown[0]} ({best_drawdown[1].max_drawdown:.2%})")

        # 综合推荐
        print(f"\n【策略推荐】")

        # 计算综合得分
        strategy_scores = {}
        for name, result in valid_results.items():
            score = 0
            # 年化收益权重40%
            score += min(result.annual_return * 40, 40)
            # 夏普比率权重20%
            score += min(result.sharpe_ratio * 10, 20)
            # 回撤控制权重20%
            score += max(0, 20 - result.max_drawdown * 100)
            # 胜率权重20%
            score += result.win_rate * 20

            strategy_scores[name] = score

        recommended = max(strategy_scores.items(), key=lambda x: x[1])
        print(f"  综合推荐: {recommended[0]} (得分: {recommended[1]:.1f})")

        return recommended[0]

    return None


def save_results_to_json(results: Dict[str, BacktestResult], filename: str):
    """保存回测结果到JSON"""
    output = {}
    for name, result in results.items():
        if result:
            output[name] = {
                "total_return": result.total_return,
                "annual_return": result.annual_return,
                "max_drawdown": result.max_drawdown,
                "sharpe_ratio": result.sharpe_ratio,
                "win_rate": result.win_rate,
                "profit_loss_ratio": result.profit_loss_ratio,
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
            }

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
    start_date = end_date - timedelta(days=365*3)  # 3年历史数据

    print(f"\n回测时间范围: {start_date.date()} 至 {end_date.date()}")

    # 获取所有标的
    all_symbols = get_all_symbols()
    print(f"标的数量: {len(all_symbols)} 只")

    # 显示行业分布
    print("\n行业分布:")
    for sector, stocks in STOCKS_100.items():
        print(f"  {sector}: {len(stocks)}只")

    # 下载数据
    print("\n" + "="*80)
    stock_data = download_stock_data(all_symbols, start_date, end_date)

    if len(stock_data) < 50:
        print(f"\n警告: 仅获取到 {len(stock_data)} 只股票数据，数量不足")
        print("尝试使用备用方案: 减少标的数量")
        # 如果数据不足，使用已有数据继续

    if not stock_data:
        print("\n错误: 未能获取任何股票数据，回测无法继续")
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
    results = {}
    scores = {}

    for config in strategies_config:
        try:
            result = run_strategy_backtest(
                strategy_class=config["class"],
                strategy_name=config["name"],
                strategy_params=config["params"],
                data=stock_data,
                start_date=start_date,
                end_date=end_date,
                initial_capital=10_000_000.0,  # 1000万初始资金
            )

            if result:
                results[config["name"]] = result
                score = print_backtest_result(result, config["name"])
                scores[config["name"]] = score

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
        print(f"回测标的: {len(stock_data)} 只A股")
        print(f"时间范围: {start_date.date()} 至 {end_date.date()}")
        print(f"测试策略: {len(results)} 个")

        if recommended_strategy:
            print(f"\n推荐策略: {recommended_strategy}")
            rec_result = results[recommended_strategy]
            print(f"  - 年化收益率: {rec_result.annual_return:+.2%}")
            print(f"  - 距离目标(100%): {(rec_result.annual_return - 1.0):+.2%}")

            if rec_result.annual_return >= 1.0:
                print(f"\n✓ 恭喜！策略已达到年化100%收益目标！")
            else:
                gap = 1.0 - rec_result.annual_return
                print(f"\n△ 策略年化收益率为 {rec_result.annual_return:.2%}")
                print(f"  距离100%目标还差 {gap:.2%}")
                print(f"\n建议:")
                print(f"  1. 优化策略参数")
                print(f"  2. 尝试策略组合")
                print(f"  3. 增加更多因子")
                print(f"  4. 优化仓位管理")

    print(f"\n{'='*80}")
    print("回测完成")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
