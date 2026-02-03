# 开发记录 - 均值回归策略、基本面数据采集器、机器学习策略框架

**开发日期**: 2026-02-03  
**开发功能**: 均值回归策略 + 基本面数据采集器 + 机器学习策略框架  
**开发者**: AI Assistant

---

## 一、功能概述

本次开发完成了以下核心功能：

1. **均值回归策略**：统计套利策略、配对交易策略、波动率回归策略
2. **基本面数据采集器**：财务报表、业绩预告、股东持仓、龙虎榜数据
3. **机器学习策略框架**：价格预测策略、分类预测策略、强化学习框架

---

## 二、技术实现

### 2.1 均值回归策略

**文件**: `alphax/strategies/mean_reversion_strategy.py`

#### 2.1.1 统计套利策略 (StatisticalArbitrageStrategy)

基于价格序列的均值回归特性进行交易：

```python
# 策略逻辑
zscore = (price - mean) / std
if zscore > entry_threshold:  # 做空
    short()
elif zscore < -entry_threshold:  # 做多
    buy()
elif abs(zscore) < exit_threshold:  # 平仓
    close_position()
```

**核心参数**：
- `lookback_period`: 回看周期（默认20日）
- `entry_zscore`: 入场Z-Score阈值（默认2.0）
- `exit_zscore`: 出场Z-Score阈值（默认0.5）

#### 2.1.2 配对交易策略 (PairsTradingStrategy)

基于两只股票的协整关系进行交易：

```python
# 计算协整关系
hedge_ratio = slope(prices_b, prices_a)
spread = price_a - hedge_ratio * price_b
zscore = (spread - spread_mean) / spread_std

# 交易逻辑
if zscore > entry_threshold:  # 做空价差
    short(symbol_a)
    buy(symbol_b)
elif zscore < -entry_threshold:  # 做多价差
    buy(symbol_a)
    short(symbol_b)
```

**核心功能**：
- 自动计算最优对冲比例
- 协整检验（简化版ADF检验）
- 动态价差Z-Score计算

#### 2.1.3 波动率回归策略 (VolatilityMeanReversionStrategy)

基于波动率的均值回归特性：

```python
# 计算波动率
volatility = std(returns) * sqrt(252)
vol_percentile = percentile(volatility, historical_vols)

# 高波动率时反向交易
if vol_percentile > threshold and price_trend > 0:
    short()  # 预期回归
```

**核心参数**：
- `vol_lookback`: 波动率回看周期（默认20日）
- `vol_percentile`: 波动率分位数阈值（默认0.8）

### 2.2 基本面数据采集器

**文件**: `data/collectors/fundamental_collector.py`

#### 2.2.1 财务报表

```python
# 利润表
income = collector.get_income_statement("000001")
# 包含：营业收入、营业成本、净利润、EPS等

# 资产负债表
balance = collector.get_balance_sheet("000001")
# 包含：总资产、总负债、所有者权益等

# 现金流量表
cashflow = collector.get_cash_flow("000001")
# 包含：经营现金流、投资现金流、筹资现金流等

# 财务指标
indicators = collector.get_financial_indicators("000001")
# 包含：ROE、ROA、毛利率、净利率、资产负债率等
```

#### 2.2.2 业绩预告

```python
# 获取业绩预告
forecasts = collector.get_performance_forecast("000001")
# 包含：预告类型（预增/预减）、净利润变动幅度、业绩变动原因等

# 获取业绩快报
express = collector.get_performance_express()
# 包含：营业收入、净利润、同比增长率等
```

#### 2.2.3 股东持仓

```python
# 前十大股东
holders = collector.get_top10_holders("000001")
# 包含：股东名称、持股数量、持股比例、变动情况等

# 基金持仓
fund_holdings = collector.get_fund_holdings("000001")
# 包含：基金名称、持股数量、持股市值、占净值比例等
```

#### 2.2.4 龙虎榜

```python
# 龙虎榜列表
dragons = collector.get_dragon_tiger_list("20240201")
# 包含：股票代码、涨跌幅、买入额、卖出额、净额等

# 龙虎榜详情
detail = collector.get_dragon_tiger_detail("000001", "20240201")
# 包含：买入营业部、卖出营业部、成交金额等
```

### 2.3 机器学习策略框架

**文件**: `alphax/strategies/ml_strategy.py`

#### 2.3.1 特征工程 (FeatureEngineer)

```python
# 提取特征
features = FeatureEngineer.extract_features(bars)

# 包含特征：
# - 价格特征：returns_1d/5d/10d/20d
# - 移动平均：ma5/10/20, close_ma_ratio
# - 波动率：volatility_5d/10d/20d
# - 价格位置：price_position
# - 成交量：volume, volume_ma, volume_ratio
# - 技术指标：atr, rsi
```

#### 2.3.2 价格预测策略 (PricePredictionStrategy)

基于回归模型预测未来收益率：

```python
# 训练模型
model = GradientBoostingRegressor()
model.fit(X, y)  # X: 特征, y: 未来收益率

# 预测
predicted_return = model.predict(features)

# 交易信号
if predicted_return > threshold:
    buy()
elif predicted_return < -threshold:
    short()
```

**核心参数**：
- `feature_window`: 特征窗口（默认20日）
- `prediction_horizon`: 预测周期（默认5日）
- `retrain_interval`: 重训练间隔（默认20交易日）
- `signal_threshold`: 信号阈值（默认2%）

#### 2.3.3 分类预测策略 (ClassificationStrategy)

基于分类模型预测涨跌方向：

```python
# 训练分类模型
model = GradientBoostingClassifier()
model.fit(X, y)  # y: -1(跌), 0(平), 1(涨)

# 预测概率
prediction, probabilities = model.predict_proba(features)
up_prob = probabilities[1]
down_prob = probabilities[-1]

# 交易信号
if up_prob > confidence_threshold:
    buy(position_scale=up_prob)
elif down_prob > confidence_threshold:
    short(position_scale=down_prob)
```

**核心参数**：
- `confidence_threshold`: 置信度阈值（默认0.6）
- 概率加权仓位管理

#### 2.3.4 强化学习框架 (RLStrategyFramework)

基于强化学习的交易决策框架：

```python
# 状态空间
state = [price_features, technical_indicators, position_status]

# 动作空间
action = 0  # 持仓
action = 1  # 买入
action = 2  # 卖出
action = 3  # 空仓

# 奖励函数
reward = price_change if long_position else -price_change

# 经验缓存
experience = {
    "state": state,
    "action": action,
    "reward": reward,
    "next_state": next_state
}
```

**注意**：这是一个框架类，需要配合具体的RL算法（如DQN、PPO等）使用。

---

## 三、使用示例

### 3.1 均值回归策略

```python
from alphax.strategies import (
    StatisticalArbitrageStrategy,
    PairsTradingStrategy,
    MeanReversionConfig
)

# 统计套利策略
config = MeanReversionConfig(
    lookback_period=20,
    entry_zscore=2.0,
    exit_zscore=0.5
)
strategy = StatisticalArbitrageStrategy(
    backtest_engine,
    "StatArb_001",
    ["000001.SZ"],
    config.__dict__
)

# 配对交易策略
pair_config = MeanReversionConfig(
    lookback_period=60,
    entry_zscore=2.0,
    coint_threshold=0.05
)
pair_strategy = PairsTradingStrategy(
    backtest_engine,
    "PairTrade_001",
    ["000001.SZ", "000002.SZ"],  # 两个相关股票
    pair_config.__dict__
)
```

### 3.2 基本面数据采集

```python
from data.collectors import FundamentalCollector

collector = FundamentalCollector()
collector.connect()

# 获取财务报表
income = collector.get_income_statement("000001")
balance = collector.get_balance_sheet("000001")
cashflow = collector.get_cash_flow("000001")

# 获取财务指标
indicators = collector.get_financial_indicators("000001")
for indicator in indicators:
    print(f"ROE: {indicator['roe']:.2%}")
    print(f"毛利率: {indicator['gross_margin']:.2%}")

# 获取业绩预告
forecasts = collector.get_performance_forecast()
for forecast in forecasts:
    if forecast['forecast_type'] == '预增':
        print(f"{forecast['symbol']}: 预增 {forecast['profit_change_min']:.0f}%-{forecast['profit_change_max']:.0f}%")
```

### 3.3 机器学习策略

```python
from alphax.strategies import (
    PricePredictionStrategy,
    ClassificationStrategy,
    MLStrategyConfig
)

# 价格预测策略
config = MLStrategyConfig(
    feature_window=20,
    prediction_horizon=5,
    signal_threshold=0.02,
    retrain_interval=20
)
ml_strategy = PricePredictionStrategy(
    backtest_engine,
    "ML_Price_Predict",
    ["000001.SZ"],
    config.__dict__
)

# 分类预测策略
cls_config = MLStrategyConfig(
    confidence_threshold=0.65,
    signal_threshold=0.015
)
cls_strategy = ClassificationStrategy(
    backtest_engine,
    "ML_Classify",
    ["000001.SZ"],
    cls_config.__dict__
)
```

---

## 四、性能优化

### 4.1 策略优化
- 特征计算使用NumPy向量化操作
- 模型重训练间隔可配置，避免过度训练
- 支持简化版模型（当sklearn未安装时）

### 4.2 数据采集优化
- 金额解析支持中文单位（亿、万）
- 异常值处理，确保数据质量
- 统计信息跟踪（请求数、成功率等）

---

## 五、后续计划

### 5.1 短期计划（本周）
1. 实盘交易系统对接准备
2. 事件驱动策略开发（财报事件、资金流向事件）

### 5.2 中期计划（本月）
1. 组合策略开发（风险平价、因子轮动）
2. 交易执行系统优化（TWAP/VWAP算法）
3. 另类数据采集（舆情、行业景气度）

### 5.3 长期计划（本季度）
1. 监控告警系统完善
2. 复盘工具开发
3. 机器学习模型管理（A/B测试、自动重训练）

---

## 六、文档更新

- [x] `ai_docs/开发任务.md` 已更新
- [x] `alphax/strategies/__init__.py` 已更新
- [x] `data/collectors/__init__.py` 已更新
- [x] 新增 `alphax/strategies/mean_reversion_strategy.py`
- [x] 新增 `alphax/strategies/ml_strategy.py`
- [x] 新增 `data/collectors/fundamental_collector.py`

---

## 七、风险提示

1. **均值回归策略风险**：
   - 价格可能长期偏离均值（趋势行情）
   - 需要合理设置止损
   - 协整关系可能随时间变化

2. **机器学习策略风险**：
   - 过拟合风险
   - 模型需要定期重训练
   - 特征有效性可能随市场变化

3. **基本面数据限制**：
   - 财务报表有滞后性
   - 业绩预告可能存在偏差
   - 龙虎榜数据仅反映短期资金流向

---

**记录创建时间**: 2026-02-03  
**最后更新时间**: 2026-02-03
