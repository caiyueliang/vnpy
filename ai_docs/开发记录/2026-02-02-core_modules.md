# AlphaX 核心模块开发记录

**日期**: 2026-02-02  
**功能**: 核心风险管理与仓位管理模块  
**版本**: v1.0.0  
**开发者**: AI Assistant

---

## 1. 开发概述

今日完成了 AlphaX 量化交易系统的核心基础模块开发，实现了项目规则文档中定义的风险管理和仓位管理体系。

## 2. 已完成模块

### 2.1 风险管理模块 (`alphax/risk.py`)

#### 功能特性
- **三级风控体系**：
  - Level 1: 账户级风控（单日/总亏损限制、持仓集中度）
  - Level 2: 策略级风控（策略回撤监控）
  - Level 3: 交易级风控（订单数量、单笔风险）
- **熔断机制**：三级熔断（暂停当日/清仓/暂停一周）
- **风险报告**：实时风险状态监控

#### 核心类
- `RiskLevel`: 风险等级枚举 (NORMAL/WARNING/DANGER/CRITICAL)
- `RiskLimits`: 风险限制配置数据类
- `RiskStatus`: 风险状态数据类
- `RiskManager`: 风险管理器主类

#### 关键方法
- `set_capital()`: 设置初始资金
- `update_pnl()`: 更新盈亏并检查风险
- `check_risk()`: 检查整体风险状态
- `check_order()`: 检查订单风险
- `get_risk_report()`: 获取风险报告

### 2.2 仓位管理模块 (`alphax/position.py`)

#### 功能特性
- **动态仓位计算**：基于信号强度和ATR的风险平价仓位计算
- **ATR计算**：基于真实波幅的动态仓位调整
- **持仓管理**：成本计算、市值跟踪、止损检查
- **再平衡**：基于信号强度的仓位再平衡

#### 核心类
- `PositionConfig`: 仓位配置数据类
- `PositionManager`: 仓位管理器主类

#### 关键方法
- `set_portfolio_value()`: 设置组合价值
- `calculate_atr()`: 计算ATR指标
- `calculate_position_size()`: 计算目标仓位大小
- `update_position()`: 更新持仓
- `should_reduce_position()`: 检查是否需要减仓（止损）
- `get_rebalance_targets()`: 获取再平衡目标仓位

#### 动态仓位计算公式
```python
position_size = min(
    base_position * (confidence / 0.6),      # 基于信号强度
    max_position * portfolio_value,           # 单品种上限
    portfolio_value * risk_per_trade / (atr * multiplier)  # 风险平价
)
```

### 2.3 策略评估模块 (`alphax/evaluation.py`)

#### 功能特性
- **绩效指标计算**：收益、风险、风险调整收益、交易指标
- **策略评估**：根据项目规则文档的标准进行评估
- **报告生成**：自动生成详细的绩效评估报告

#### 核心类
- `PerformanceMetrics`: 绩效指标数据类
- `PerformanceEvaluator`: 策略绩效评估器

#### 评估标准（符合项目规则）
- 年化收益率 >= 50%
- 夏普比率 >= 2.0
- 最大回撤 <= 15%
- 胜率 >= 55%
- 盈亏比 >= 1.5

#### 关键方法
- `add_daily_return()`: 添加每日收益数据
- `add_trade()`: 添加交易盈亏
- `calculate_metrics()`: 计算绩效指标
- `evaluate_strategy()`: 评估策略是否符合标准
- `generate_report()`: 生成评估报告

## 3. 项目结构

```
alphax/
├── __init__.py          # 模块入口，导出核心类
├── risk.py              # 风险管理模块 (262行)
├── position.py          # 仓位管理模块 (311行)
└── evaluation.py        # 策略评估模块 (317行)

tests/
└── test_alphax.py       # 模块测试脚本 (166行)
```

## 4. 代码质量

### 4.1 代码检查
- ✅ **Ruff 检查**：通过（无错误、无警告）
- ✅ **Mypy 检查**：通过（类型注解完整）

### 4.2 测试覆盖
- ✅ 风险管理模块测试通过
- ✅ 仓位管理模块测试通过
- ✅ 策略评估模块测试通过

### 4.3 代码规范
- 所有函数都有完整的类型注解
- 所有类都有详细的docstring
- 遵循PEP 8代码风格
- 使用Python 3.10+新特性（如 `X | None` 类型注解）

## 5. 使用示例

### 5.1 风险管理
```python
from alphax import RiskManager
from alphax.risk import RiskLimits

# 创建风险管理器
limits = RiskLimits(
    max_daily_loss_pct=0.05,
    max_total_loss_pct=0.20,
    max_single_position_pct=0.20,
)
risk_mgr = RiskManager(limits)

# 设置资金
risk_mgr.set_capital(initial=1000000, current=1000000)

# 更新盈亏并检查风险
status = risk_mgr.update_pnl(pnl=-60000)
print(f"风险等级: {status.level.name}")
print(f"是否阻塞: {status.blocked}")
```

### 5.2 仓位管理
```python
from alphax import PositionManager
from alphax.position import PositionConfig

# 创建仓位管理器
config = PositionConfig(
    base_position=0.1,
    max_position=0.3,
    risk_per_trade=0.02,
)
pos_mgr = PositionManager(config)

# 设置组合价值
pos_mgr.set_portfolio_value(value=1000000, cash=800000)

# 计算目标仓位
target_size = pos_mgr.calculate_position_size(
    vt_symbol="000001.SZSE",
    confidence=0.8,
    current_price=10.0,
    atr=0.5,
)
```

### 5.3 策略评估
```python
from alphax import PerformanceEvaluator

# 创建评估器
evaluator = PerformanceEvaluator(risk_free_rate=0.03)

# 添加每日收益数据
evaluator.add_daily_return(date, ret, pnl, portfolio_value)

# 计算绩效指标
metrics = evaluator.calculate_metrics()
print(f"年化收益率: {metrics.annual_return:.2%}")
print(f"夏普比率: {metrics.sharpe_ratio:.2f}")

# 生成报告
print(evaluator.generate_report())
```

## 6. 技术亮点

1. **类型安全**：完整的类型注解，通过mypy严格检查
2. **配置灵活**：使用dataclass实现可配置的风险和仓位参数
3. **熔断机制**：多级熔断保护，防止极端情况下的重大损失
4. **风险平价**：基于ATR的动态仓位计算，实现风险均衡分配
5. **评估标准**：严格按照项目规则文档的绩效标准进行评估

## 7. 下一步计划

1. **策略模块**：开发多因子选股策略模板
2. **执行引擎**：实现交易执行和订单管理
3. **数据集成**：集成vnpy.alpha的ML模型能力
4. **监控告警**：添加实时监控和告警系统

## 8. 更新记录

| 时间 | 更新内容 | 版本 |
|------|----------|------|
| 2026-02-02 | 初始版本，完成核心模块开发 | v1.0.0 |

---

**备注**: 本文档记录了AlphaX项目的开发历程，每次更新都会同步到项目规则文件中。
