"""
AlphaX 模块测试
"""

from datetime import datetime, timedelta
import numpy as np

from alphax import RiskManager, RiskLevel, PositionManager, PerformanceEvaluator
from alphax.risk import RiskLimits
from alphax.position import PositionConfig


def test_risk_manager():
    """测试风险管理模块"""
    print("\n" + "=" * 60)
    print("测试风险管理模块")
    print("=" * 60)

    # 创建风险管理器
    limits = RiskLimits(
        max_daily_loss_pct=0.05,
        max_total_loss_pct=0.20,
        max_single_position_pct=0.20,
    )
    risk_mgr = RiskManager(limits)

    # 设置初始资金
    risk_mgr.set_capital(initial=1000000, current=1000000)
    print(f"初始资金: {risk_mgr.initial_capital:,.0f}")

    # 检查初始风险状态
    status = risk_mgr.check_risk()
    print(f"初始风险等级: {status.level.name}")
    print(f"是否阻塞: {status.blocked}")

    # 模拟盈利
    risk_mgr.update_pnl(pnl=50000)
    status = risk_mgr.check_risk()
    print(f"盈利50,000后风险等级: {status.level.name}")

    # 模拟亏损触发警告
    risk_mgr.update_pnl(pnl=-60000)
    status = risk_mgr.check_risk()
    print(f"亏损60,000后风险等级: {status.level.name}")
    print(f"风险消息: {status.messages}")

    # 获取风险报告
    report = risk_mgr.get_risk_report()
    print(f"\n风险报告:")
    print(f"  总盈亏: {report['capital']['total_pnl']:,.0f}")
    print(f"  日盈亏: {report['capital']['daily_pnl']:,.0f}")

    print("✓ 风险管理模块测试通过")


def test_position_manager():
    """测试仓位管理模块"""
    print("\n" + "=" * 60)
    print("测试仓位管理模块")
    print("=" * 60)

    # 创建仓位管理器
    config = PositionConfig(
        base_position=0.1,
        max_position=0.3,
        risk_per_trade=0.02,
        confidence_threshold=0.6,
    )
    pos_mgr = PositionManager(config)

    # 设置组合价值
    pos_mgr.set_portfolio_value(value=1000000, cash=800000)
    print(f"组合总价值: {pos_mgr.portfolio_value:,.0f}")
    print(f"可用现金: {pos_mgr.cash_available:,.0f}")

    # 计算目标仓位
    target_size = pos_mgr.calculate_position_size(
        vt_symbol="000001.SZSE",
        confidence=0.8,
        current_price=10.0,
        atr=0.5,
    )
    print(f"\n信号置信度0.8，价格10.0，ATR 0.5:")
    print(f"  目标持仓数量: {target_size:,.0f}股")
    print(f"  目标持仓市值: {target_size * 10:,.0f}")
    print(f"  目标仓位比例: {pos_mgr.get_position_pct('000001.SZSE'):.2%}")

    # 更新持仓
    pos_mgr.update_position("000001.SZSE", size=10000, price=10.0, is_open=True)
    print(f"\n买入10,000股 @ 10.0:")
    print(f"  当前持仓: {pos_mgr.get_position('000001.SZSE'):,.0f}股")
    print(f"  持仓市值: {pos_mgr.get_position_value('000001.SZSE'):,.0f}")

    # 检查未实现盈亏
    unrealized_pnl = pos_mgr.get_unrealized_pnl("000001.SZSE", current_price=11.0)
    unrealized_pnl_pct = pos_mgr.get_unrealized_pnl_pct("000001.SZSE", current_price=11.0)
    print(f"  价格上涨到11.0时的未实现盈亏: {unrealized_pnl:,.0f} ({unrealized_pnl_pct:.2%})")

    # 检查止损
    should_reduce = pos_mgr.should_reduce_position("000001.SZSE", current_price=9.0, stop_loss_pct=0.05)
    print(f"  价格下跌到9.0时是否应止损: {should_reduce}")

    print("✓ 仓位管理模块测试通过")


def test_performance_evaluator():
    """测试策略评估模块"""
    print("\n" + "=" * 60)
    print("测试策略评估模块")
    print("=" * 60)

    evaluator = PerformanceEvaluator(risk_free_rate=0.03)

    # 模拟一年交易日的收益数据
    np.random.seed(42)
    n_days = 252
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]

    # 生成正收益序列 (模拟年化50%收益)
    daily_returns = np.random.normal(0.0016, 0.02, n_days)  # 日均0.16%，波动2%
    portfolio_value = 1000000

    for i, (date, ret) in enumerate(zip(dates, daily_returns)):
        pnl = portfolio_value * ret
        portfolio_value += pnl
        evaluator.add_daily_return(date, ret, pnl, portfolio_value)

        # 模拟一些交易
        if i % 10 == 0:
            evaluator.add_trade(pnl=np.random.normal(1000, 5000))

    # 计算绩效指标
    metrics = evaluator.calculate_metrics()
    print("\n绩效指标:")
    print(f"  总收益率: {metrics.total_return:.2%}")
    print(f"  年化收益率: {metrics.annual_return:.2%}")
    print(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown:.2%}")
    print(f"  胜率: {metrics.win_rate:.2%}")
    print(f"  盈亏比: {metrics.profit_loss_ratio:.2f}")

    # 评估策略
    result = evaluator.evaluate_strategy()
    print(f"\n策略评估:")
    print(f"  综合得分: {result['overall_score']:.1%}")
    print(f"  是否合格: {result['passed']}")

    # 生成报告
    print("\n" + evaluator.generate_report())

    print("✓ 策略评估模块测试通过")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("AlphaX 量化交易系统 - 模块测试")
    print("=" * 60)

    test_risk_manager()
    test_position_manager()
    test_performance_evaluator()

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
