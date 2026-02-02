# 开发记录 - 数据库系统与回测框架

**日期**: 2026-02-02  
**开发功能**: 数据库系统搭建与回测验证系统开发  
**优先级**: P0

---

## 一、数据库系统搭建

### 1.1 项目结构

```
data/
├── __init__.py
├── collectors/          # 数据采集器（已完成）
│   ├── __init__.py
│   ├── base.py          # 采集器基类
│   └── akshare_collector.py  # AKShare采集器
├── cleaners/            # 数据清洗（已完成）
│   ├── __init__.py
│   └── data_cleaner.py  # 数据清洗器
└── storage/             # 数据存储（已完成）
    ├── __init__.py
    ├── database.py      # 数据库管理器
    ├── timeseries.py    # 时序数据库
    ├── relational.py    # 关系数据库
    └── cache.py         # 缓存数据库
```

### 1.2 核心功能实现

#### 1.2.1 数据库管理器 (DatabaseManager)

统一管理多种数据库连接：

```python
from data.storage import DatabaseManager, DBConfig

# 配置数据库
config = DBConfig(
    influxdb_host="localhost",
    influxdb_port=8086,
    postgres_host="localhost",
    postgres_port=5432,
    redis_host="localhost",
    redis_port=6379
)

# 连接数据库
db = DatabaseManager(config)
db.connect()

# 使用数据库
db.save_bar_data(bars)
db.load_bar_data(vt_symbol, interval, start, end)
db.cache_set("key", value)
db.cache_get("key")
```

#### 1.2.2 时序数据库 (TimeSeriesDB)

- **主要功能**: 存储Tick和K线行情数据
- **支持数据库**: InfluxDB (优先), SQLite (fallback)
- **数据表结构**:
  - `bar_data`: K线数据表
  - `tick_data`: Tick数据表

#### 1.2.3 关系数据库 (RelationalDB)

- **主要功能**: 存储交易记录、账户信息、策略配置
- **支持数据库**: PostgreSQL (优先), SQLite (fallback)
- **数据表结构**:
  - `trades`: 交易记录表
  - `orders`: 订单记录表
  - `positions`: 持仓记录表
  - `account`: 账户资金表
  - `strategies`: 策略配置表
  - `daily_returns`: 每日收益表

#### 1.2.4 缓存数据库 (CacheDB)

- **主要功能**: 高速缓存实时数据、计算结果
- **支持数据库**: Redis (优先), 内存字典 (fallback)
- **功能特性**:
  - 自动过期机制
  - 命中率统计
  - 键模式匹配

### 1.3 数据采集系统

#### 1.3.1 采集器基类 (DataCollector)

```python
from data.collectors import DataCollector, CollectorConfig, DataSource

class MyCollector(DataCollector):
    def connect(self) -> bool:
        # 实现连接逻辑
        pass
    
    def get_bar_data(self, vt_symbol, interval, start, end):
        # 实现数据获取
        pass
```

#### 1.3.2 AKShare采集器

- **功能**: 获取A股免费行情数据
- **支持数据**:
  - 日K线数据
  - 分钟K线数据 (1m/5m/15m/30m/60m)
  - 实时行情
  - 股票列表

```python
from data.collectors import AKShareCollector

collector = AKShareCollector()
collector.connect()

# 获取日K线
bars = collector.get_bar_data(
    vt_symbol="000001.SZ",
    interval="d",
    start=datetime(2023, 1, 1),
    end=datetime(2023, 12, 31)
)

# 获取股票列表
stocks = collector.get_stock_list()
```

### 1.4 数据清洗系统

#### 1.4.1 数据清洗器 (DataCleaner)

```python
from data.cleaners import DataCleaner, DataQualityIssue

cleaner = DataCleaner()

# 清洗数据
cleaned_bars = cleaner.clean_bar_data(raw_bars)

# 检查数据质量
report = cleaner.check_data_quality(bars)
print(f"缺失率: {report.missing_rate:.2%}")
print(f"异常率: {report.outlier_rate:.2%}")
```

#### 1.4.2 支持的数据质量问题检测

- 缺失值检测与填充
- 异常值检测与处理
- 重复数据检测与删除
- 负价格检测
- OHLC关系验证
- 数据连续性检查

---

## 二、回测验证系统开发

### 2.1 项目结构

```
alphax/backtest/
├── __init__.py
├── engine.py       # 回测引擎
└── result.py       # 回测结果处理

alphax/strategies/
├── __init__.py
├── template.py     # 策略模板
└── moving_average_strategy.py  # 均线策略示例
```

### 2.2 核心功能实现

#### 2.2.1 回测引擎 (BacktestEngine)

```python
from alphax.backtest import BacktestEngine, BacktestConfig
from datetime import datetime

# 配置回测
config = BacktestConfig(
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 12, 31),
    initial_capital=1_000_000,
    commission_rate=0.0003,
    slippage=0.0001
)

# 创建引擎
engine = BacktestEngine(config)

# 加载数据
engine.add_data("000001.SSE", bars)

# 设置策略
engine.set_strategy(MyStrategy, setting={"param1": 10})

# 运行回测
engine.run_backtesting()

# 获取结果
result = engine.get_result()
print(engine.generate_report())
```

#### 2.2.2 回测配置 (BacktestConfig)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| start_date | - | 回测开始日期 |
| end_date | - | 回测结束日期 |
| initial_capital | 1,000,000 | 初始资金 |
| commission_rate | 0.0003 | 手续费率 (0.03%) |
| slippage | 0.0001 | 滑点 (0.01%) |
| size | 1 | 合约乘数 |
| mode | "bar" | 回测模式 (bar/tick) |

#### 2.2.3 回测结果 (BacktestResult)

提供丰富的结果分析功能：

- **指标计算**: 年化收益、夏普比率、最大回撤等
- **可视化**: 权益曲线、回撤曲线、月度收益热力图
- **报告生成**: 文本报告、Excel导出

### 2.3 策略框架

#### 2.3.1 策略模板 (StrategyTemplate)

```python
from alphax.strategies import StrategyTemplate

class MyStrategy(StrategyTemplate):
    def on_strategy_init(self):
        # 策略初始化
        pass
    
    def on_bars(self, bars):
        # 处理K线数据
        for vt_symbol, bar in bars.items():
            # 生成交易信号
            if self.should_buy(bar):
                self.buy(vt_symbol, bar.close_price, volume)
```

#### 2.3.2 均线策略示例 (MovingAverageStrategy)

- **策略逻辑**: 双均线交叉产生交易信号
- **买入信号**: 短期均线上穿长期均线
- **卖出信号**: 短期均线下穿长期均线

```python
from alphax.strategies import MovingAverageStrategy

# 设置策略参数
setting = {
    "fast_window": 10,   # 短期均线周期
    "slow_window": 20,   # 长期均线周期
}

engine.set_strategy(MovingAverageStrategy, setting=setting)
```

### 2.4 风控集成

回测引擎集成了完整的风控体系：

1. **账户级风控**: 单日最大亏损、总亏损限制
2. **策略级风控**: 策略最大回撤、资金上限
3. **交易级风控**: 单笔订单限制、持仓集中度
4. **熔断机制**: 三级熔断自动触发

### 2.5 绩效评估

自动评估策略是否符合项目标准：

| 指标 | 目标值 | 评估标准 |
|------|--------|----------|
| 年化收益率 | ≥ 50% | 必须达到 |
| 夏普比率 | ≥ 2.0 | 必须达到 |
| 最大回撤 | ≤ 15% | 必须达到 |
| 胜率 | ≥ 55% | 必须达到 |
| 盈亏比 | ≥ 1.5 | 必须达到 |

综合得分 ≥ 80% 视为合格策略

---

## 三、代码质量

### 3.1 类型注解

所有函数都添加了完整的类型注解：

```python
def load_bar_data(
    self,
    vt_symbol: str,
    interval: str,
    start: datetime,
    end: datetime
) -> list[BarData]:
    ...
```

### 3.2 错误处理

完善的异常捕获和处理机制：

```python
try:
    self._cursor.execute(sql, params)
    self._connection.commit()
    return True
except Exception as e:
    self._connection.rollback()
    print(f"SQL执行失败: {e}")
    return False
```

### 3.3 文档字符串

所有类和函数都包含详细的docstring：

```python
class BacktestEngine:
    """
    回测引擎

    实现基于历史数据的策略回测，集成风控和仓位管理

    Args:
        config: 回测配置对象

    Example:
        >>> config = BacktestConfig(start_date=..., end_date=...)
        >>> engine = BacktestEngine(config)
        >>> engine.run_backtesting()
    """
```

---

## 四、测试验证

### 4.1 运行测试

```bash
# 运行单元测试
python tests/test_alphax.py
```

### 4.2 测试结果

- ✓ 风险管理模块测试通过
- ✓ 仓位管理模块测试通过
- ✓ 策略评估模块测试通过

---

## 五、后续计划

### 5.1 待优化项

1. **数据库性能优化**: 批量插入、连接池管理
2. **回测速度优化**: 向量化计算、并行回测
3. **数据质量监控**: 完整性检查、异常值检测

### 5.2 下一步开发

1. 完善数据采集系统（Tushare、RQData等）
2. 开发更多策略模板（趋势跟踪、均值回归等）
3. 实盘交易系统对接
4. 监控告警系统开发

---

## 六、参考文档

- [开发任务清单](../开发任务.md)
- [开发规范](../开发规范.md)
- [项目规则](../../.trae/rules/project_rules.md)
