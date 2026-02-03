# 开发记录 - 另类数据采集器、事件驱动策略、组合策略

**开发日期**: 2026-02-03  
**开发功能**: 另类数据采集器 + 事件驱动策略 + 组合策略  
**开发者**: AI Assistant

---

## 一、功能概述

本次开发完成了以下核心功能：

1. **另类数据采集器**：舆情数据、行业景气度、宏观指标
2. **事件驱动策略**：财报事件策略、资金流向事件策略、龙虎榜事件策略
3. **组合策略**：风险平价策略、因子轮动策略、智能资产配置策略

---

## 二、技术实现

### 2.1 另类数据采集器

**文件**: `data/collectors/alternative_collector.py` (711行)

#### 2.1.1 舆情数据

```python
# 获取个股新闻
news = collector.get_stock_news("000001", days=7)
# 包含：标题、内容、发布时间、来源、链接

# 获取个股公告
announcements = collector.get_stock_announcements("000001")
# 包含：公告标题、类别、发布日期、链接

# 获取投资者情绪
sentiment = collector.get_investor_sentiment()
# 包含：新增投资者数量、总投资者数量、环比增长率

# 获取个股热度排名
hot_ranks = collector.get_stock_hot_rank()
# 包含：排名、股票代码、热度值、涨跌幅
```

#### 2.1.2 行业景气度数据

```python
# 获取行业列表
industries = collector.get_industry_list()
# 包含：行业代码、名称、涨跌幅、换手率、成交额、涨跌家数

# 获取行业成分股
stocks = collector.get_industry_stocks("BK0475")
# 包含：股票代码、名称、价格、涨跌幅、换手率、成交额、市值

# 获取行业景气度指数
boom_index = collector.get_industry_boom_index("银行")
# 包含：景气度指数、20日收益率、波动率、成交量趋势

# 获取概念板块列表
concepts = collector.get_concept_list()
# 包含：概念代码、名称、涨跌幅、换手率等
```

#### 2.1.3 宏观指标数据

```python
# 获取宏观经济指标
macro = collector.get_macro_economic_indicators()
# 包含：GDP、CPI、PMI、货币供应量

# 获取利率数据
rates = collector.get_interest_rates()
# 包含：日期、1年期LPR、5年期LPR

# 获取汇率数据
exchange_rate = collector.get_exchange_rate("USD/CNY")
# 包含：日期、现汇买入价、现钞买入价、卖出价

# 获取国债收益率
treasury = collector.get_treasury_yield()
# 包含：中国/美国2年/5年/10年/30年国债收益率
```

### 2.2 事件驱动策略

**文件**: `alphax/strategies/event_driven_strategy.py` (606行)

#### 2.2.1 财报事件策略 (EarningsEventStrategy)

基于业绩预告进行交易：

```python
# 策略逻辑
if 预告类型 == "预增" and 净利润变动 > 20%:
    buy()  # 做多
elif 预告类型 == "预减" and 净利润变动 < -20%:
    short()  # 做空

# 持仓5个交易日后平仓
if 持仓天数 >= 5:
    close_position()
```

**核心参数**：
- `earnings_threshold`: 业绩预告变动阈值（默认20%）
- `holding_period`: 持仓周期（默认5交易日）

#### 2.2.2 资金流向事件策略 (CapitalFlowEventStrategy)

基于主力资金流向变化进行交易：

```python
# 策略逻辑
if 连续3日净流入 and 总净流入 > 1亿:
    buy()  # 做多
elif 连续3日净流出 and 总净流出 > 1亿:
    short()  # 做空

# 资金流向反转时平仓
if 多头持仓 and 资金流向转负:
    sell()
elif 空头持仓 and 资金流向转正:
    cover()
```

**核心参数**：
- `flow_threshold`: 资金流向阈值（默认1亿）
- `flow_consecutive_days`: 连续流入天数（默认3天）

#### 2.2.3 龙虎榜事件策略 (DragonTigerEventStrategy)

基于龙虎榜数据进行交易：

```python
# 策略逻辑
if 机构买入比例 > 60%:
    buy()  # 次日开盘做多
elif 机构卖出比例 > 60%:
    short()  # 次日开盘做空

# T+1制度，次日平仓
if 持仓天数 >= 1:
    close_position()
```

**核心参数**：
- `dragon_tiger_amount`: 龙虎榜金额阈值（默认5000万）
- `institution_buy_ratio`: 机构买入比例阈值（默认60%）

### 2.3 组合策略

**文件**: `alphax/strategies/portfolio_strategy.py` (690行)

#### 2.3.1 风险平价策略 (RiskParityStrategy)

基于风险贡献度进行资产配置：

```python
# 计算各资产波动率
volatility_i = std(returns_i) * sqrt(252)

# 风险平价权重
weight_i = (1 / volatility_i) / sum(1 / volatility_j)

# 根据目标波动率调整杠杆
leverage = target_volatility / portfolio_volatility
weight_i = weight_i * leverage

# 定期再平衡
if 再平衡周期到达:
    rebalance_portfolio()
```

**核心参数**：
- `risk_lookback`: 风险计算回看周期（默认60日）
- `target_volatility`: 目标波动率（默认年化15%）
- `rebalance_period`: 再平衡周期（默认20交易日）

#### 2.3.2 因子轮动策略 (FactorRotationStrategy)

基于因子表现进行动态调仓：

```python
# 定义因子
factors = {
    "momentum": 动量因子得分,
    "value": 价值因子得分,
    "quality": 质量因子得分,
    "low_volatility": 低波动因子得分,
}

# 计算因子表现
factor_performance = mean(factor_scores)

# 选择表现最好的N个因子
top_factors = top_n(factor_performance, n=3)

# 根据因子得分选择股票
stock_scores = sum(factor_score for factor in top_factors)
top_stocks = top_n(stock_scores, n=5)

# 定期轮动调整持仓
if 轮动周期到达:
    rotate_portfolio()
```

**核心参数**：
- `factor_lookback`: 因子表现回看周期（默认20日）
- `top_n_factors`: 选择前N个因子（默认3个）
- `rebalance_period`: 轮动周期（默认20交易日）

#### 2.3.3 智能资产配置策略 (SmartAssetAllocationStrategy)

基于市场状态进行动态资产配置：

```python
# 评估市场状态
trend_score = 均线排列得分 + 价格位置得分
vol_score = 波动率得分
market_state_score = trend_score + vol_score

# 判断市场状态
if score > 0.5:
    state = "bull"  # 牛市
elif score < 0.2:
    state = "bear"  # 熊市
else:
    state = "neutral"  # 震荡市

# 调整资产配置
if state == "bull":
    allocation = {"stocks": 0.80, "bonds": 0.15, "cash": 0.05}
elif state == "bear":
    allocation = {"stocks": 0.30, "bonds": 0.40, "cash": 0.30}
else:
    allocation = {"stocks": 0.50, "bonds": 0.35, "cash": 0.15}
```

**核心参数**：
- `max_asset_weight`: 单资产最大权重（默认40%）
- `min_asset_weight`: 单资产最小权重（默认5%）
- `rebalance_period`: 再平衡周期（默认20交易日）

---

## 三、使用示例

### 3.1 另类数据采集

```python
from data.collectors import AlternativeCollector

collector = AlternativeCollector()
collector.connect()

# 获取舆情数据
news = collector.get_stock_news("000001", days=7)
for item in news:
    print(f"{item['publish_time']}: {item['title']}")

# 获取行业景气度
industries = collector.get_industry_list()
for industry in industries[:5]:
    print(f"{industry['name']}: 涨跌幅{industry['change_pct']:.2f}%")

# 获取宏观指标
macro = collector.get_macro_economic_indicators()
print(f"GDP同比: {macro['gdp']['gdp_yoy']:.2f}%")
print(f"CPI同比: {macro['cpi']['cpi_yoy']:.2f}%")
print(f"制造业PMI: {macro['pmi']['manufacturing_pmi']:.2f}")
```

### 3.2 事件驱动策略

```python
from alphax.strategies import (
    EarningsEventStrategy,
    CapitalFlowEventStrategy,
    EventDrivenConfig
)

# 财报事件策略
config = EventDrivenConfig(
    earnings_threshold=0.20,
    holding_period=5
)
earnings_strategy = EarningsEventStrategy(
    backtest_engine,
    "EarningsEvent",
    ["000001.SZ", "000002.SZ"],
    config.__dict__
)

# 资金流向事件策略
flow_config = EventDrivenConfig(
    flow_threshold=1e8,
    flow_consecutive_days=3
)
flow_strategy = CapitalFlowEventStrategy(
    backtest_engine,
    "CapitalFlowEvent",
    ["000001.SZ", "000002.SZ"],
    flow_config.__dict__
)
```

### 3.3 组合策略

```python
from alphax.strategies import (
    RiskParityStrategy,
    FactorRotationStrategy,
    PortfolioConfig
)

# 风险平价策略
config = PortfolioConfig(
    target_volatility=0.15,
    rebalance_period=20
)
risk_parity = RiskParityStrategy(
    backtest_engine,
    "RiskParity",
    ["000001.SZ", "000002.SZ", "000333.SZ", "000858.SZ"],
    config.__dict__
)

# 因子轮动策略
rotation_config = PortfolioConfig(
    top_n_factors=3,
    rebalance_period=20
)
factor_rotation = FactorRotationStrategy(
    backtest_engine,
    "FactorRotation",
    ["000001.SZ", "000002.SZ", "000333.SZ", "000858.SZ", "002415.SZ"],
    rotation_config.__dict__
)
```

---

## 四、性能优化

### 4.1 数据采集优化
- 金额解析支持中文单位（亿、万、%）
- 异常值处理，确保数据质量
- 统计信息跟踪（请求数、成功率等）

### 4.2 策略优化
- 特征计算使用NumPy向量化操作
- 定期再平衡避免过度交易
- 事件缓存机制避免重复处理

---

## 五、后续计划

### 5.1 短期计划（本周）
1. 实盘交易系统对接准备
2. 交易执行系统优化（TWAP/VWAP算法）

### 5.2 中期计划（本月）
1. 复盘工具开发
2. 机器学习模型管理（A/B测试、自动重训练）
3. 监控告警系统完善

### 5.3 长期计划（本季度）
1. 知识积累系统
2. 性能优化
3. 合规与伦理检查

---

## 六、文档更新

- [x] `ai_docs/开发任务.md` 已更新
- [x] `alphax/strategies/__init__.py` 已更新
- [x] `data/collectors/__init__.py` 已更新
- [x] 新增 `data/collectors/alternative_collector.py`
- [x] 新增 `alphax/strategies/event_driven_strategy.py`
- [x] 新增 `alphax/strategies/portfolio_strategy.py`

---

## 七、风险提示

1. **另类数据限制**：
   - 舆情数据可能存在滞后性
   - 行业景气度指数为简化计算，仅供参考
   - 宏观指标发布频率较低

2. **事件驱动策略风险**：
   - 事件信号可能存在延迟
   - 市场可能已提前反应
   - 需要严格的风险控制

3. **组合策略风险**：
   - 风险平价策略在市场极端情况下可能失效
   - 因子轮动策略依赖因子有效性
   - 智能资产配置需要准确的市场状态判断

---

**记录创建时间**: 2026-02-03  
**最后更新时间**: 2026-02-03
