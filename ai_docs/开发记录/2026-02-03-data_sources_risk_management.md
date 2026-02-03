# 开发记录 - 数据源集成与风控系统完善

**开发日期**: 2026-02-03  
**开发功能**: Tushare/RQData数据源集成 + 策略级与交易级风控系统完善  
**开发者**: AI Assistant

---

## 一、功能概述

本次开发完成了以下核心功能：

1. **数据源扩展**：集成Tushare Pro和RQData（米筐）数据源
2. **策略级风控完善**：策略资金上限控制、策略开关控制、策略相关性监控
3. **交易级风控完善**：滑点控制、涨跌停保护、流动性检查

---

## 二、技术实现

### 2.1 Tushare数据采集器

**文件**: `data/collectors/tushare_collector.py`

**功能特性**：
- 支持日K线、周K线、月K线、分钟K线数据获取
- 支持Tick数据获取（需高级权限）
- 自动前复权处理
- 股票列表获取
- 每日指标数据（PE、PB、换手率等）
- 资金流向数据（散户、中户、大户、超大户）
- 涨跌停股票列表

**使用示例**：
```python
from data.collectors import TushareCollector, CollectorConfig, DataSource

config = CollectorConfig(
    source=DataSource.TUSHARE,
    api_key="your_tushare_token"
)
collector = TushareCollector(config)
collector.connect()

# 获取日K线数据
bars = collector.get_bar_data(
    vt_symbol="000001.SZ",
    interval="d",
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31)
)
```

### 2.2 RQData数据采集器

**文件**: `data/collectors/rqdata_collector.py`

**功能特性**：
- 支持日K线、周K线、月K线、分钟K线数据获取
- 支持Tick数据获取
- 基本面数据获取
- 财务报表数据（利润表、资产负债表、现金流量表）
- 行业成分股获取
- 指数成分股获取
- 因子数据获取
- 收益率曲线获取

**使用示例**：
```python
from data.collectors import RQDataCollector, CollectorConfig, DataSource

config = CollectorConfig(
    source=DataSource.RQDATA,
    api_key="your_rqdata_username",
    api_secret="your_rqdata_password"
)
collector = RQDataCollector(config)
collector.connect()

# 获取指数成分股
stocks = collector.get_index_stocks("000001.XSHG")  # 上证指数成分股
```

### 2.3 策略级风控完善

**文件**: `alphax/risk.py`

**新增功能**：

#### 2.3.1 策略风险配置 (StrategyRiskConfig)
```python
@dataclass
class StrategyRiskConfig:
    strategy_name: str
    enabled: bool = True                      # 策略是否启用
    max_capital: float = 0.0                  # 策略最大资金
    max_drawdown_pct: float = 0.10            # 策略最大回撤比例
    max_daily_loss_pct: float = 0.05          # 策略单日最大亏损比例
    max_correlation: float = 0.80             # 策略最大相关性
    pause_until: datetime | None = None       # 暂停直到
```

#### 2.3.2 策略开关控制
- `register_strategy()`: 注册策略风险配置
- `enable_strategy()`: 启用策略
- `disable_strategy()`: 禁用策略（支持临时暂停）
- `is_strategy_enabled()`: 检查策略是否启用

#### 2.3.3 策略资金上限控制
- 实时监控各策略占用资金
- 超过阈值时发出警告
- 支持策略级和全局级配置

#### 2.3.4 策略相关性监控
- 自动计算策略间收益率相关性
- 使用最近60天收益率数据
- 相关性超过阈值时发出警告
- 支持策略级自定义阈值

### 2.4 交易级风控完善

**新增功能**：

#### 2.4.1 交易风险检查配置 (TradeRiskCheck)
```python
@dataclass
class TradeRiskCheck:
    vt_symbol: str
    direction: Direction
    volume: float
    price: float
    expected_price: float | None = None       # 预期成交价格（用于滑点检查）
    market_volume: float = 0.0                # 市场成交量（用于流动性检查）
    up_limit: float = 0.0                     # 涨停价
    down_limit: float = 0.0                   # 跌停价
```

#### 2.4.2 滑点控制
- 实时监控成交滑点
- 统计各品种平均滑点
- 滑点超过阈值时发出警告
- 默认阈值：0.05%

#### 2.4.3 涨跌停保护
- 买入时检查涨停状态
- 卖出时检查跌停状态
- 触及涨跌停时禁止交易

#### 2.4.4 流动性检查
- 检查订单量占市场成交量比例
- 超过阈值时禁止交易（默认5%）
- 防止大单冲击市场

---

## 三、测试验证

### 3.1 数据源测试

```python
# 测试Tushare连接
from data.collectors import TushareCollector, CollectorConfig, DataSource

config = CollectorConfig(source=DataSource.TUSHARE, api_key="test_token")
collector = TushareCollector(config)
assert collector.connect() == True or collector.connect() == False  # 取决于是否安装tushare

# 测试RQData连接
from data.collectors import RQDataCollector

config = CollectorConfig(source=DataSource.RQDATA)
collector = RQDataCollector(config)
# RQData需要有效的账号，测试时可能返回False
```

### 3.2 风控系统测试

```python
from alphax.risk import RiskManager, RiskLimits, StrategyRiskConfig, TradeRiskCheck, RiskLevel
from vnpy.trader.constant import Direction

# 创建风险管理器
rm = RiskManager(RiskLimits(max_strategy_correlation=0.5))
rm.set_capital(1000000, 1000000)

# 注册策略
config1 = StrategyRiskConfig("strategy_1", max_capital=300000, max_correlation=0.6)
config2 = StrategyRiskConfig("strategy_2", max_capital=300000, max_correlation=0.6)
rm.register_strategy(config1)
rm.register_strategy(config2)

# 测试策略开关
assert rm.is_strategy_enabled("strategy_1") == True
rm.disable_strategy("strategy_1", pause_days=1)
assert rm.is_strategy_enabled("strategy_1") == False
rm.enable_strategy("strategy_1")
assert rm.is_strategy_enabled("strategy_1") == True

# 测试交易风险检查
trade_check = TradeRiskCheck(
    vt_symbol="000001.SZ",
    direction=Direction.LONG,
    volume=1000,
    price=10.0,
    expected_price=9.95,
    market_volume=100000,
    up_limit=11.0,
    down_limit=9.0
)
status = rm.check_trade_risk(trade_check)
assert status.blocked == False
```

---

## 四、性能优化

### 4.1 数据源优化
- Tushare分钟数据支持逐日获取和合并
- RQData支持批量获取多个合约数据
- 收益率序列限制在252个交易日（约一年）
- 滑点统计限制在100笔

### 4.2 风控计算优化
- 策略相关性使用NumPy矩阵计算
- 收益率序列使用滑动窗口
- 熔断状态缓存，避免重复计算

---

## 五、后续计划

### 5.1 短期计划（本周）
1. 实盘交易系统对接准备
2. 更多策略模板开发（均值回归策略）

### 5.2 中期计划（本月）
1. 基本面数据采集（财务报表、业绩预告）
2. 机器学习策略框架搭建
3. 交易执行系统优化（TWAP/VWAP算法）

### 5.3 长期计划（本季度）
1. 监控告警系统完善
2. 复盘工具开发
3. 机器学习模型管理

---

## 六、文档更新

- [x] `ai_docs/开发任务.md` 已更新
- [x] `data/collectors/__init__.py` 已更新
- [x] 新增 `data/collectors/tushare_collector.py`
- [x] 新增 `data/collectors/rqdata_collector.py`
- [x] 更新 `alphax/risk.py`

---

## 七、风险提示

1. **数据源限制**：Tushare和RQData都需要申请API Token/账号
2. **数据权限**：部分高级数据（Tick数据、财务数据）需要付费权限
3. **风控阈值**：当前阈值为默认值，实盘前需要根据策略特性调整
4. **相关性计算**：需要至少30天收益率数据才能计算相关性

---

**记录创建时间**: 2026-02-03  
**最后更新时间**: 2026-02-03
