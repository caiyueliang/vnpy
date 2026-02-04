"""
简化版真实数据回测
使用AKShare获取数据并测试策略
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import json

try:
    import akshare as ak
    import pandas as pd
    import numpy as np
    from vnpy.trader.object import BarData
    from vnpy.trader.constant import Exchange
    
    print("=" * 80)
    print("AlphaX 真实数据回测验证")
    print("目标：年化收益率100%（一年一倍）")
    print("=" * 80)
    
    # 测试标的
    symbol = "600519"  # 贵州茅台
    symbol_name = "贵州茅台"
    
    # 回测区间（最近2年）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*2)
    
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    print(f"\n测试标的：{symbol_name} ({symbol})")
    print(f"回测区间：{start_date_str} 至 {end_date_str}")
    
    # 获取数据
    print(f"\n正在从AKShare获取数据...")
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date_str.replace("-", ""),
        end_date=end_date_str.replace("-", ""),
        adjust="qfq"
    )
    
    print(f"获取到 {len(df)} 条数据")
    print(f"\n数据预览：")
    print(df.head())
    print(f"\n数据统计：")
    print(df.describe())
    
    # 计算简单收益率
    df['return'] = df['收盘'].pct_change()
    
    # 买入持有策略
    total_return = (df['收盘'].iloc[-1] - df['收盘'].iloc[0]) / df['收盘'].iloc[0]
    days = len(df)
    annual_return = (1 + total_return) ** (252 / days) - 1
    volatility = df['return'].std() * (252 ** 0.5)
    sharpe = annual_return / volatility if volatility > 0 else 0
    
    print(f"\n{'='*60}")
    print("买入持有策略基准")
    print('='*60)
    print(f"  总收益率：{total_return:.2%}")
    print(f"  年化收益率：{annual_return:.2%}")
    print(f"  年化波动率：{volatility:.2%}")
    print(f"  夏普比率：{sharpe:.2f}")
    
    # 目标对比
    target_return = 1.0  # 100%
    print(f"\n  目标年化收益率：{target_return:.0%}")
    print(f"  达成率：{annual_return/target_return:.1%}")
    
    # 保存结果
    result = {
        "symbol": symbol,
        "name": symbol_name,
        "period": f"{start_date_str} to {end_date_str}",
        "total_days": days,
        "buy_hold_return": total_return,
        "buy_hold_annual_return": annual_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "target_return": target_return,
        "achievement_rate": annual_return / target_return
    }
    
    # 保存结果
    os.makedirs("data/backtest_results", exist_ok=True)
    filepath = f"data/backtest_results/baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n  结果已保存：{filepath}")
    
    print(f"\n{'='*80}")
    print("结论")
    print('='*80)
    
    if annual_return >= target_return:
        print(f"  ✓ 买入持有策略已达成目标！")
    else:
        print(f"  ✗ 买入持有策略未达成目标")
        print(f"  差距：{(target_return - annual_return):.2%}")
        print(f"\n  要实现{target_return:.0%}的年化收益，需要：")
        print(f"    1. 超越买入持有的策略")
        print(f"    2. 更好的择时能力")
        print(f"    3. 风险控制（避免大幅回撤）")
    
except ImportError as e:
    print(f"缺少依赖：{e}")
    print("请先安装：pip install akshare pandas numpy")
except Exception as e:
    print(f"错误：{e}")
    import traceback
    traceback.print_exc()
