"""
机器学习策略框架

提供机器学习相关的策略模板和工具：
1. 价格预测模型策略 - 基于回归模型预测价格走势
2. 分类模型策略 - 基于分类模型预测涨跌
3. 强化学习策略框架 - 基于强化学习的交易决策
"""

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Direction

from .template import StrategyTemplate, StrategyConfig


@dataclass
class MLStrategyConfig(StrategyConfig):
    """机器学习策略配置"""
    # 特征参数
    feature_window: int = 20                # 特征窗口大小
    prediction_horizon: int = 5             # 预测周期

    # 模型参数
    model_type: str = "lightgbm"            # 模型类型
    retrain_interval: int = 20              # 重训练间隔（交易日）

    # 交易参数
    confidence_threshold: float = 0.6       # 置信度阈值
    signal_threshold: float = 0.02          # 信号阈值（涨跌幅）

    # 风险管理
    max_position_hold_days: int = 5         # 最大持仓天数


class FeatureEngineer:
    """
    特征工程类

    从原始价格数据中提取机器学习特征
    """

    @staticmethod
    def extract_features(bars: list[BarData]) -> dict[str, float]:
        """
        提取特征

        Args:
            bars: K线数据列表

        Returns:
            特征字典
        """
        if len(bars) < 20:
            return {}

        closes = np.array([bar.close_price for bar in bars])
        highs = np.array([bar.high_price for bar in bars])
        lows = np.array([bar.low_price for bar in bars])
        volumes = np.array([bar.volume for bar in bars])

        features = {}

        # 价格特征
        features["close"] = closes[-1]
        features["returns_1d"] = (closes[-1] - closes[-2]) / closes[-2] if len(closes) > 1 else 0
        features["returns_5d"] = (closes[-1] - closes[-5]) / closes[-5] if len(closes) > 5 else 0
        features["returns_10d"] = (closes[-1] - closes[-10]) / closes[-10] if len(closes) > 10 else 0
        features["returns_20d"] = (closes[-1] - closes[0]) / closes[0] if len(closes) > 0 else 0

        # 移动平均线特征
        features["ma5"] = np.mean(closes[-5:]) if len(closes) >= 5 else closes[-1]
        features["ma10"] = np.mean(closes[-10:]) if len(closes) >= 10 else closes[-1]
        features["ma20"] = np.mean(closes[-20:]) if len(closes) >= 20 else closes[-1]

        features["close_ma5_ratio"] = closes[-1] / features["ma5"] - 1 if features["ma5"] > 0 else 0
        features["close_ma10_ratio"] = closes[-1] / features["ma10"] - 1 if features["ma10"] > 0 else 0
        features["close_ma20_ratio"] = closes[-1] / features["ma20"] - 1 if features["ma20"] > 0 else 0

        # 波动率特征
        features["volatility_5d"] = np.std(closes[-5:]) / np.mean(closes[-5:]) if len(closes) >= 5 else 0
        features["volatility_10d"] = np.std(closes[-10:]) / np.mean(closes[-10:]) if len(closes) >= 10 else 0
        features["volatility_20d"] = np.std(closes[-20:]) / np.mean(closes[-20:]) if len(closes) >= 20 else 0

        # 价格位置特征
        high_20d = np.max(highs[-20:]) if len(highs) >= 20 else highs[-1]
        low_20d = np.min(lows[-20:]) if len(lows) >= 20 else lows[-1]
        features["price_position"] = (closes[-1] - low_20d) / (high_20d - low_20d) if high_20d > low_20d else 0.5

        # 成交量特征
        features["volume"] = volumes[-1]
        features["volume_ma5"] = np.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
        features["volume_ma10"] = np.mean(volumes[-10:]) if len(volumes) >= 10 else volumes[-1]
        features["volume_ratio"] = volumes[-1] / features["volume_ma5"] if features["volume_ma5"] > 0 else 1

        # 技术指标特征
        features["atr"] = FeatureEngineer._calculate_atr(highs, lows, closes)
        features["rsi"] = FeatureEngineer._calculate_rsi(closes)

        return features

    @staticmethod
    def _calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """计算ATR"""
        if len(highs) < period + 1:
            return 0.0

        tr_values = []
        for i in range(1, len(highs)):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i-1])
            tr3 = abs(lows[i] - closes[i-1])
            tr_values.append(max(tr1, tr2, tr3))

        return np.mean(tr_values[-period:]) if len(tr_values) >= period else 0.0

    @staticmethod
    def _calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
        """计算RSI"""
        if len(closes) < period + 1:
            return 50.0

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


class PricePredictionStrategy(StrategyTemplate):
    """
    价格预测策略

    基于机器学习回归模型预测未来价格走势，根据预测结果生成交易信号。

    策略逻辑：
    1. 提取历史价格特征
    2. 训练回归模型预测未来收益率
    3. 当预测收益率 > 阈值时，做多
    4. 当预测收益率 < -阈值时，做空
    5. 预测准确率下降时，触发模型重训练
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = MLStrategyConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in MLStrategyConfig.__dataclass_fields__}
        )

        # 模型状态
        self.model: Any = None
        self.is_model_trained: bool = False
        self.trade_count: int = 0
        self.prediction_history: list[dict] = []

        # 持仓状态
        self.position_entry_price: dict[str, float] = {}
        self.position_entry_date: dict[str, datetime] = {}

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("价格预测策略初始化完成")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("价格预测策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("价格预测策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.feature_window * 3:
                self.history_bars[vt_symbol].pop(0)

            # 检查是否需要重训练
            if self.trade_count >= self.config.retrain_interval:
                self._retrain_model(vt_symbol)
                self.trade_count = 0

            # 训练模型（首次）
            if not self.is_model_trained and len(self.history_bars[vt_symbol]) >= self.config.feature_window * 2:
                self._train_model(vt_symbol)

            # 生成交易信号
            if self.is_model_trained:
                self._generate_signals(vt_symbol, bar)

    def _train_model(self, vt_symbol: str) -> None:
        """
        训练模型

        Args:
            vt_symbol: 合约代码
        """
        try:
            from sklearn.ensemble import GradientBoostingRegressor

            bars = self.history_bars[vt_symbol]
            if len(bars) < self.config.feature_window * 2:
                return

            # 准备训练数据
            X, y = self._prepare_training_data(bars)

            if len(X) < 50:  # 最少需要50个样本
                return

            # 训练模型
            self.model = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42
            )
            self.model.fit(X, y)
            self.is_model_trained = True

            self.write_log(f"模型训练完成，样本数: {len(X)}")

        except ImportError:
            self.write_log("sklearn未安装，使用简化版预测")
            self._train_simple_model(bars)
        except Exception as e:
            self.write_log(f"模型训练失败: {e}")

    def _train_simple_model(self, bars: list[BarData]) -> None:
        """训练简化版模型（基于移动平均）"""
        self.is_model_trained = True
        self.write_log("使用简化版预测模型")

    def _retrain_model(self, vt_symbol: str) -> None:
        """重训练模型"""
        self.write_log("触发模型重训练")
        self._train_model(vt_symbol)

    def _prepare_training_data(
        self,
        bars: list[BarData]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        准备训练数据

        Args:
            bars: K线数据列表

        Returns:
            (特征矩阵, 目标向量)
        """
        X = []
        y = []

        window = self.config.feature_window
        horizon = self.config.prediction_horizon

        for i in range(window, len(bars) - horizon):
            # 提取特征
            window_bars = bars[i-window:i]
            features = FeatureEngineer.extract_features(window_bars)

            if not features:
                continue

            # 目标：未来收益率
            future_return = (bars[i+horizon].close_price - bars[i].close_price) / bars[i].close_price

            X.append(list(features.values()))
            y.append(future_return)

        return np.array(X), np.array(y)

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        bars = self.history_bars[vt_symbol]
        if len(bars) < self.config.feature_window:
            return

        # 提取当前特征
        features = FeatureEngineer.extract_features(bars[-self.config.feature_window:])
        if not features:
            return

        # 预测
        predicted_return = self._predict_return(features)

        position = self.get_position(vt_symbol)

        # 入场信号
        if position == 0:
            if predicted_return > self.config.signal_threshold:
                volume = self._calculate_position_size(vt_symbol)
                self.buy(vt_symbol, bar.close_price, volume)
                self.position_entry_price[vt_symbol] = bar.close_price
                self.position_entry_date[vt_symbol] = bar.datetime
                self.write_log(f"做多信号: 预测收益={predicted_return:.2%}, 价格={bar.close_price}")
                self.trade_count += 1

            elif predicted_return < -self.config.signal_threshold:
                volume = self._calculate_position_size(vt_symbol)
                self.short(vt_symbol, bar.close_price, volume)
                self.position_entry_price[vt_symbol] = bar.close_price
                self.position_entry_date[vt_symbol] = bar.datetime
                self.write_log(f"做空信号: 预测收益={predicted_return:.2%}, 价格={bar.close_price}")
                self.trade_count += 1

        # 出场信号
        else:
            exit_signal = False

            # 信号反转
            if position > 0 and predicted_return < -self.config.signal_threshold / 2:
                exit_signal = True
            elif position < 0 and predicted_return > self.config.signal_threshold / 2:
                exit_signal = True

            # 持仓时间超过限制
            if vt_symbol in self.position_entry_date:
                hold_days = (bar.datetime - self.position_entry_date[vt_symbol]).days
                if hold_days >= self.config.max_position_hold_days:
                    exit_signal = True
                    self.write_log(f"持仓时间到期平仓: {hold_days}天")

            if exit_signal:
                if position > 0:
                    self.sell(vt_symbol, bar.close_price, position)
                else:
                    self.cover(vt_symbol, bar.close_price, abs(position))
                self.trade_count += 1

    def _predict_return(self, features: dict[str, float]) -> float:
        """
        预测收益率

        Args:
            features: 特征字典

        Returns:
            预测收益率
        """
        try:
            if self.model is not None:
                X = np.array(list(features.values())).reshape(1, -1)
                return self.model.predict(X)[0]
        except Exception:
            pass

        # 简化版预测：基于趋势
        ma5_ratio = features.get("close_ma5_ratio", 0)
        ma10_ratio = features.get("close_ma10_ratio", 0)
        return (ma5_ratio + ma10_ratio) / 2

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """计算仓位大小"""
        return 100  # 简化版


class ClassificationStrategy(StrategyTemplate):
    """
    分类预测策略

    基于机器学习分类模型预测涨跌方向，根据预测结果生成交易信号。

    策略逻辑：
    1. 提取历史价格特征
    2. 训练分类模型预测涨跌（三分类：涨、跌、平）
    3. 当预测上涨概率 > 置信度阈值时，做多
    4. 当预测下跌概率 > 置信度阈值时，做空
    5. 使用概率加权仓位管理
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = MLStrategyConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in MLStrategyConfig.__dataclass_fields__}
        )

        # 模型状态
        self.model: Any = None
        self.is_model_trained: bool = False
        self.trade_count: int = 0

        # 预测准确率跟踪
        self.prediction_accuracy: float = 0.5
        self.correct_predictions: int = 0
        self.total_predictions: int = 0

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("分类预测策略初始化完成")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("分类预测策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("分类预测策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.feature_window * 3:
                self.history_bars[vt_symbol].pop(0)

            # 检查是否需要重训练
            if self.trade_count >= self.config.retrain_interval:
                self._retrain_model(vt_symbol)
                self.trade_count = 0

            # 训练模型（首次）
            if not self.is_model_trained and len(self.history_bars[vt_symbol]) >= self.config.feature_window * 2:
                self._train_model(vt_symbol)

            # 生成交易信号
            if self.is_model_trained:
                self._generate_signals(vt_symbol, bar)

    def _train_model(self, vt_symbol: str) -> None:
        """
        训练分类模型

        Args:
            vt_symbol: 合约代码
        """
        try:
            from sklearn.ensemble import GradientBoostingClassifier

            bars = self.history_bars[vt_symbol]
            if len(bars) < self.config.feature_window * 2:
                return

            # 准备训练数据
            X, y = self._prepare_classification_data(bars)

            if len(X) < 50:
                return

            # 训练模型
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42
            )
            self.model.fit(X, y)
            self.is_model_trained = True

            self.write_log(f"分类模型训练完成，样本数: {len(X)}")

        except ImportError:
            self.write_log("sklearn未安装，使用简化版分类")
            self.is_model_trained = True
        except Exception as e:
            self.write_log(f"模型训练失败: {e}")

    def _retrain_model(self, vt_symbol: str) -> None:
        """重训练模型"""
        self.write_log("触发模型重训练")
        self._train_model(vt_symbol)

    def _prepare_classification_data(
        self,
        bars: list[BarData]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        准备分类训练数据

        Args:
            bars: K线数据列表

        Returns:
            (特征矩阵, 标签向量)
        """
        X = []
        y = []

        window = self.config.feature_window
        horizon = self.config.prediction_horizon

        for i in range(window, len(bars) - horizon):
            # 提取特征
            window_bars = bars[i-window:i]
            features = FeatureEngineer.extract_features(window_bars)

            if not features:
                continue

            # 标签：涨跌分类
            future_return = (bars[i+horizon].close_price - bars[i].close_price) / bars[i].close_price

            if future_return > self.config.signal_threshold:
                label = 1  # 涨
            elif future_return < -self.config.signal_threshold:
                label = -1  # 跌
            else:
                label = 0  # 平

            X.append(list(features.values()))
            y.append(label)

        return np.array(X), np.array(y)

    def _generate_signals(self, vt_symbol: str, bar: BarData) -> None:
        """
        生成交易信号

        Args:
            vt_symbol: 合约代码
            bar: K线数据
        """
        bars = self.history_bars[vt_symbol]
        if len(bars) < self.config.feature_window:
            return

        # 提取当前特征
        features = FeatureEngineer.extract_features(bars[-self.config.feature_window:])
        if not features:
            return

        # 预测
        prediction, probabilities = self._predict_class(features)

        # 获取上涨概率
        up_prob = probabilities.get(1, 0)
        down_prob = probabilities.get(-1, 0)

        position = self.get_position(vt_symbol)

        # 入场信号
        if position == 0:
            if up_prob > self.config.confidence_threshold:
                # 根据概率调整仓位
                position_scale = up_prob
                volume = self._calculate_position_size(vt_symbol) * position_scale
                self.buy(vt_symbol, bar.close_price, volume)
                self.write_log(f"做多信号: 上涨概率={up_prob:.2%}, 价格={bar.close_price}")
                self.trade_count += 1

            elif down_prob > self.config.confidence_threshold:
                position_scale = down_prob
                volume = self._calculate_position_size(vt_symbol) * position_scale
                self.short(vt_symbol, bar.close_price, volume)
                self.write_log(f"做空信号: 下跌概率={down_prob:.2%}, 价格={bar.close_price}")
                self.trade_count += 1

        # 出场信号
        else:
            exit_signal = False

            # 信号反转或置信度不足
            if position > 0 and (prediction == -1 or up_prob < 0.5):
                exit_signal = True
            elif position < 0 and (prediction == 1 or down_prob < 0.5):
                exit_signal = True

            if exit_signal:
                if position > 0:
                    self.sell(vt_symbol, bar.close_price, position)
                else:
                    self.cover(vt_symbol, bar.close_price, abs(position))
                self.trade_count += 1

    def _predict_class(self, features: dict[str, float]) -> tuple[int, dict[int, float]]:
        """
        预测分类

        Args:
            features: 特征字典

        Returns:
            (预测类别, 各类别概率)
        """
        try:
            if self.model is not None:
                X = np.array(list(features.values())).reshape(1, -1)
                prediction = self.model.predict(X)[0]
                probabilities = self.model.predict_proba(X)[0]

                # 转换为字典
                classes = self.model.classes_
                prob_dict = {int(c): p for c, p in zip(classes, probabilities)}

                return int(prediction), prob_dict
        except Exception:
            pass

        # 简化版预测
        ma5_ratio = features.get("close_ma5_ratio", 0)
        if ma5_ratio > self.config.signal_threshold:
            return 1, {1: 0.6, 0: 0.3, -1: 0.1}
        elif ma5_ratio < -self.config.signal_threshold:
            return -1, {-1: 0.6, 0: 0.3, 1: 0.1}
        else:
            return 0, {0: 0.5, 1: 0.25, -1: 0.25}

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """计算仓位大小"""
        return 100


class RLStrategyFramework(StrategyTemplate):
    """
    强化学习策略框架

    基于强化学习的交易决策框架。策略通过与市场环境交互，
    学习最优的交易策略。

    状态空间：价格特征、技术指标、持仓状态等
    动作空间：买入、卖出、持仓、空仓
    奖励函数：基于收益、风险调整收益等

    注意：这是一个框架类，需要配合具体的RL算法（如DQN、PPO等）使用
    """

    def __init__(
        self,
        backtest_engine: Any,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """Constructor"""
        super().__init__(backtest_engine, strategy_name, vt_symbols, setting)

        # 策略配置
        self.config = MLStrategyConfig(
            name=strategy_name,
            vt_symbols=vt_symbols,
            **{k: v for k, v in setting.items() if k in MLStrategyConfig.__dataclass_fields__}
        )

        # RL状态
        self.state: np.ndarray | None = None
        self.last_action: int = 0
        self.last_price: float = 0.0

        # 经验缓存（用于训练）
        self.experience_buffer: list[dict] = []
        self.buffer_size: int = 10000

    def on_strategy_init(self) -> None:
        """策略初始化"""
        self.write_log("强化学习策略框架初始化完成")
        self.write_log("注意：这是一个框架类，需要配合具体的RL算法使用")

    def on_strategy_start(self) -> None:
        """策略启动"""
        self.write_log("强化学习策略启动")

    def on_strategy_stop(self) -> None:
        """策略停止"""
        self.write_log("强化学习策略停止")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """
        K线数据回调

        Args:
            bars: K线数据字典
        """
        if not self.trading:
            return

        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_bars[vt_symbol].append(bar)
            if len(self.history_bars[vt_symbol]) > self.config.feature_window * 3:
                self.history_bars[vt_symbol].pop(0)

            if len(self.history_bars[vt_symbol]) < self.config.feature_window:
                continue

            # 构建状态
            self.state = self._build_state(vt_symbol, bar)

            # 选择动作（由子类实现）
            action = self._select_action(self.state)

            # 执行动作
            self._execute_action(vt_symbol, bar, action)

            # 存储经验
            if self.last_price > 0:
                reward = self._calculate_reward(bar)
                self._store_experience(self.state, self.last_action, reward, self.state)

            self.last_action = action
            self.last_price = bar.close_price

    def _build_state(self, vt_symbol: str, bar: BarData) -> np.ndarray:
        """
        构建状态向量

        Args:
            vt_symbol: 合约代码
            bar: K线数据

        Returns:
            状态向量
        """
        bars = self.history_bars[vt_symbol]
        features = FeatureEngineer.extract_features(bars[-self.config.feature_window:])

        # 添加持仓信息到状态
        position = self.get_position(vt_symbol)
        features["position"] = 1 if position > 0 else (-1 if position < 0 else 0)
        features["position_size"] = abs(position) / 1000 if position != 0 else 0

        return np.array(list(features.values()))

    def _execute_action(self, vt_symbol: str, bar: BarData, action: int) -> None:
        """
        执行动作

        Args:
            vt_symbol: 合约代码
            bar: K线数据
            action: 动作 (0=持仓, 1=买入, 2=卖出, 3=空仓)
        """
        position = self.get_position(vt_symbol)

        if action == 1 and position <= 0:  # 买入
            if position < 0:
                self.cover(vt_symbol, bar.close_price, abs(position))
            volume = self._calculate_position_size(vt_symbol)
            self.buy(vt_symbol, bar.close_price, volume)

        elif action == 2 and position >= 0:  # 卖出
            if position > 0:
                self.sell(vt_symbol, bar.close_price, position)
            volume = self._calculate_position_size(vt_symbol)
            self.short(vt_symbol, bar.close_price, volume)

        elif action == 3 and position != 0:  # 空仓
            if position > 0:
                self.sell(vt_symbol, bar.close_price, position)
            elif position < 0:
                self.cover(vt_symbol, bar.close_price, abs(position))

    def _calculate_reward(self, bar: BarData) -> float:
        """
        计算奖励

        Args:
            bar: K线数据

        Returns:
            奖励值
        """
        # 基于价格变化的奖励
        price_change = (bar.close_price - self.last_price) / self.last_price

        # 根据持仓方向调整奖励
        if self.last_action == 1:  # 多头
            return price_change
        elif self.last_action == 2:  # 空头
            return -price_change
        else:
            return 0.0

    def _store_experience(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray
    ) -> None:
        """
        存储经验

        Args:
            state: 当前状态
            action: 动作
            reward: 奖励
            next_state: 下一状态
        """
        experience = {
            "state": state,
            "action": action,
            "reward": reward,
            "next_state": next_state,
        }

        self.experience_buffer.append(experience)

        if len(self.experience_buffer) > self.buffer_size:
            self.experience_buffer.pop(0)

    @abstractmethod
    def _select_action(self, state: np.ndarray) -> int:
        """
        选择动作（由子类实现）

        Args:
            state: 当前状态

        Returns:
            动作
        """
        pass

    def _calculate_position_size(self, vt_symbol: str) -> float:
        """计算仓位大小"""
        return 100
