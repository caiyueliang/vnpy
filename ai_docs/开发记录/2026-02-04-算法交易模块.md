# 开发记录 - 算法交易模块

**日期**: 2026-02-04  
**功能模块**: 算法交易模块 (alphax/execution/)  
**开发状态**: 已完成

---

## 1. 功能概述

本次开发完成了算法交易模块，实现了多种算法订单执行策略，用于优化大单执行效果，降低市场冲击成本。

### 实现算法
1. **TWAP** (Time-Weighted Average Price) - 时间加权平均价格
2. **VWAP** (Volume-Weighted Average Price) - 成交量加权平均价格
3. **Iceberg** - 冰山订单

---

## 2. 技术实现

### 2.1 模块架构

```
alphax/execution/
├── __init__.py          # 模块导出
└── algo_trading.py      # 算法交易核心实现
```

### 2.2 核心组件

#### 1. AlgoTemplate (算法模板基类)
- 定义算法订单生命周期管理
- 子订单管理
- 市场数据处理 (Tick/Bar)
- 成交回调处理
- 统计信息收集

#### 2. TWAPAlgo (TWAP算法)
**核心逻辑**:
- 将总数量均分为N个切片
- 在时间区间内均匀执行
- 支持随机化切片大小（±20%）
- 避免规律性暴露

**配置参数**:
- `slice_count`: 切片数量（默认10）
- `randomize`: 是否随机化（默认True）
- `random_range`: 随机范围（默认±20%）

#### 3. VWAPAlgo (VWAP算法)
**核心逻辑**:
- 基于历史成交量分布生成执行计划
- 在成交量大的时段多下单
- 自适应调整（根据实际/预期成交量比率）
- 默认U型成交量分布（A股特征）

**配置参数**:
- `volume_profile`: 成交量分布
- `participation_rate`: 市场参与率（默认10%）
- `adaptive`: 是否自适应调整（默认True）

#### 4. IcebergAlgo (冰山订单)
**核心逻辑**:
- 大单拆分为多个小单
- 每次只显示一部分（display_size）
- 成交后立即发送下一个
- 支持随机化显示数量

**配置参数**:
- `display_size`: 显示数量（默认100）
- `variance_pct`: 数量变化范围（默认±20%）
- `refresh_condition`: 刷新条件

#### 5. AlgoEngine (算法引擎)
- 管理所有算法订单
- 统一市场数据分发
- 成交回调处理
- 统计信息汇总

---

## 3. 关键特性

### 3.1 算法特性对比

| 特性 | TWAP | VWAP | Iceberg |
|------|------|------|---------|
| 执行依据 | 时间 | 成交量 | 事件驱动 |
| 切片数量 | 固定 | 基于分布 | 动态 |
| 价格目标 | 时间均价 | 市场VWAP | 最优执行 |
| 适用场景 | 流动性好 | 成交量分布稳定 | 避免暴露意图 |
| 市场冲击 | 低 | 较低 | 最低 |

### 3.2 风险控制

- **滑点控制**: 最大滑点限制（默认0.2%）
- **数量限制**: 最小/最大订单数量限制
- **时间控制**: 开始/结束时间设置
- **紧急程度**: 可调整执行 urgency_factor

### 3.3 统计监控

- 完成率跟踪
- 成交均价计算
- 滑点统计
- 子订单管理
- 活跃算法列表

---

## 4. 使用示例

### 4.1 创建TWAP算法订单

```python
from alphax.execution import AlgoEngine, AlgoType, TWAPConfig
from vnpy.trader.constant import Direction, Offset

# 创建引擎
engine = AlgoEngine()
engine.set_callbacks(send_order_func, cancel_order_func)

# 配置TWAP
config = TWAPConfig(
    slice_count=20,
    randomize=True,
    random_range=0.2,
    interval_seconds=60
)

# 创建算法订单
algo_id = engine.create_algo(
    algo_type=AlgoType.TWAP,
    vt_symbol="000001.SZ",
    direction=Direction.LONG,
    offset=Offset.OPEN,
    volume=10000,
    price=10.5,
    config=config
)

# 启动算法
engine.start_algo(algo_id)

# 查询状态
stats = engine.get_algo_stats(algo_id)
print(f"完成率: {stats['fill_rate']:.2%}")
print(f"成交均价: {stats['avg_fill_price']:.2f}")
```

### 4.2 创建VWAP算法订单

```python
from alphax.execution import VWAPConfig

# 配置VWAP（使用默认成交量分布）
config = VWAPConfig(
    participation_rate=0.1,  # 占市场成交量10%
    adaptive=True,           # 自适应调整
    interval_seconds=30
)

algo_id = engine.create_algo(
    algo_type=AlgoType.VWAP,
    vt_symbol="000001.SZ",
    direction=Direction.LONG,
    offset=Offset.OPEN,
    volume=50000,
    config=config
)

engine.start_algo(algo_id)
```

### 4.3 创建冰山订单

```python
from alphax.execution import IcebergConfig

# 配置冰山订单
config = IcebergConfig(
    display_size=500,      # 每次显示500股
    variance_pct=0.2,      # 数量变化±20%
    min_order_size=100,
    max_order_size=1000
)

algo_id = engine.create_algo(
    algo_type=AlgoType.ICEBERG,
    vt_symbol="000001.SZ",
    direction=Direction.LONG,
    offset=Offset.OPEN,
    volume=100000,
    config=config
)

engine.start_algo(algo_id)
```

### 4.4 市场数据回调

```python
# Tick数据回调
def on_tick(tick):
    engine.on_tick(tick.vt_symbol, tick)

# K线数据回调
def on_bar(bar):
    engine.on_bar(bar.vt_symbol, bar)

# 成交回调
def on_trade(trade):
    # 解析algo_id（从order_id中提取）
    algo_id = parse_algo_id(trade.order_id)
    engine.on_order_filled(
        algo_id=algo_id,
        order_id=trade.order_id,
        price=trade.price,
        volume=trade.volume
    )
```

---

## 5. 算法执行流程

### 5.1 TWAP执行流程

```
1. 生成执行计划
   └── 将总数量分为N个切片
   └── 计算每个切片的执行时间
   └── 随机化切片大小

2. 时间驱动执行
   └── 到达切片时间
   └── 计算订单价格
   └── 发送子订单
   └── 标记切片已执行

3. 完成检测
   └── 所有切片执行完毕
   └── 或达到结束时间
   └── 更新算法状态为COMPLETED
```

### 5.2 VWAP执行流程

```
1. 生成执行计划
   └── 加载/生成成交量分布
   └── 根据分布计算各时段数量
   └── 归一化确保总量匹配

2. 时间驱动执行
   └── 到达切片时间
   └── 自适应调整（如启用）
   └── 发送子订单

3. 自适应调整
   └── 跟踪实际/预期成交量
   └── 计算调整因子
   └── 动态调整后续切片数量
```

### 5.3 冰山订单执行流程

```
1. 事件驱动
   └── 无活跃子订单时
   └── 计算显示数量
   └── 发送子订单

2. 成交驱动
   └── 子订单完全成交
   └── 立即触发下一个
   └── 循环直到完成
```

---

## 6. 性能优化

### 6.1 执行优化
- 切片大小随机化，避免规律性
- 自适应调整，适应市场变化
- 价格偏移随机化，减少冲击

### 6.2 内存优化
- 价格历史限制100条
- 子订单及时清理
- 统计信息按需计算

---

## 7. 测试验证

### 7.1 单元测试
- 算法配置验证
- 切片计算验证
- 成交量分布生成验证
- 子订单管理验证

### 7.2 集成测试
- 算法引擎全流程测试
- 市场数据回调测试
- 成交回调测试
- 统计信息验证

---

## 8. 后续计划

1. **智能路由**: 根据市场条件自动选择最优算法
2. **机器学习优化**: 基于历史数据优化切片策略
3. **实时监控**: 算法执行实时监控面板
4. **回测支持**: 算法订单回测验证

---

## 9. 技术债务

- 暂无

---

**记录创建时间**: 2026-02-04  
**记录更新时间**: 2026-02-04
