"""
技术因子模块

实现常用的技术分析因子。
"""

import pandas as pd
import numpy as np
from typing import Optional

from .base import Factor, register_factor


class MomentumFactor(Factor):
    """
    动量因子

    计算价格动量，反映价格变化趋势。
    """

    def __init__(self, period: int = 20):
        """
        初始化动量因子

        Args:
            period: 计算周期，默认20日
        """
        super().__init__(
            name=f"momentum_{period}",
            description=f"{period}日价格动量因子"
        )
        self.set_params(period=period)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算动量因子

        Args:
            data: 包含close列的DataFrame

        Returns:
            动量因子值
        """
        period = self.params.get('period', 20)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算收益率
        returns = data['close'].pct_change(period)

        # 标准化
        momentum = (returns - returns.mean()) / returns.std()

        return momentum


class VolatilityFactor(Factor):
    """
    波动率因子

    计算价格波动率，反映价格变动幅度。
    """

    def __init__(self, period: int = 20, annualize: bool = True):
        """
        初始化波动率因子

        Args:
            period: 计算周期
            annualize: 是否年化
        """
        super().__init__(
            name=f"volatility_{period}",
            description=f"{period}日波动率因子"
        )
        self.set_params(period=period, annualize=annualize)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算波动率因子

        Args:
            data: 包含close列的DataFrame

        Returns:
            波动率因子值
        """
        period = self.params.get('period', 20)
        annualize = self.params.get('annualize', True)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算日收益率
        returns = data['close'].pct_change()

        # 计算滚动标准差
        volatility = returns.rolling(window=period).std()

        if annualize:
            volatility = volatility * np.sqrt(252)

        # 取倒数，低波动率得高分
        factor = 1 / (volatility + 1e-6)

        return factor


class VolumeFactor(Factor):
    """
    成交量因子

    分析成交量变化，反映市场参与度。
    """

    def __init__(self, period: int = 20):
        """
        初始化成交量因子

        Args:
            period: 计算周期
        """
        super().__init__(
            name=f"volume_{period}",
            description=f"{period}日成交量因子"
        )
        self.set_params(period=period)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算成交量因子

        Args:
            data: 包含volume列的DataFrame

        Returns:
            成交量因子值
        """
        period = self.params.get('period', 20)

        if 'volume' not in data.columns:
            raise ValueError("数据必须包含'volume'列")

        # 计算成交量均线
        volume_ma = data['volume'].rolling(window=period).mean()

        # 计算成交量比率
        volume_ratio = data['volume'] / (volume_ma + 1e-6)

        # 标准化
        factor = (volume_ratio - volume_ratio.mean()) / volume_ratio.std()

        return factor


class TrendFactor(Factor):
    """
    趋势因子

    基于均线系统判断趋势强度。
    """

    def __init__(self, short_period: int = 5, long_period: int = 20):
        """
        初始化趋势因子

        Args:
            short_period: 短期均线周期
            long_period: 长期均线周期
        """
        super().__init__(
            name=f"trend_{short_period}_{long_period}",
            description=f"{short_period}/{long_period}日均线趋势因子"
        )
        self.set_params(short_period=short_period, long_period=long_period)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算趋势因子

        Args:
            data: 包含close列的DataFrame

        Returns:
            趋势因子值
        """
        short_period = self.params.get('short_period', 5)
        long_period = self.params.get('long_period', 20)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算均线
        short_ma = data['close'].rolling(window=short_period).mean()
        long_ma = data['close'].rolling(window=long_period).mean()

        # 计算趋势强度
        trend_strength = (short_ma - long_ma) / (long_ma + 1e-6)

        # 结合价格位置
        price_position = (data['close'] - long_ma) / (long_ma + 1e-6)

        # 综合因子
        factor = trend_strength * 0.6 + price_position * 0.4

        return factor


class MeanReversionFactor(Factor):
    """
    均值回归因子

    基于价格偏离均线的程度判断回归潜力。
    """

    def __init__(self, period: int = 20, std_multiplier: float = 2.0):
        """
        初始化均值回归因子

        Args:
            period: 计算周期
            std_multiplier: 标准差倍数
        """
        super().__init__(
            name=f"mean_reversion_{period}",
            description=f"{period}日均值回归因子"
        )
        self.set_params(period=period, std_multiplier=std_multiplier)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算均值回归因子

        Args:
            data: 包含close列的DataFrame

        Returns:
            均值回归因子值（越高表示越偏离均值，有回归潜力）
        """
        period = self.params.get('period', 20)
        std_multiplier = self.params.get('std_multiplier', 2.0)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算均线和标准差
        ma = data['close'].rolling(window=period).mean()
        std = data['close'].rolling(window=period).std()

        # 计算Z-score（偏离程度）
        zscore = (data['close'] - ma) / (std + 1e-6)

        # 取绝对值表示偏离程度，越高越有回归潜力
        factor = -zscore  # 负值表示回归方向

        return factor


class RSIFactor(Factor):
    """
    RSI因子

    基于相对强弱指标判断超买超卖。
    """

    def __init__(self, period: int = 14):
        """
        初始化RSI因子

        Args:
            period: RSI计算周期
        """
        super().__init__(
            name=f"rsi_{period}",
            description=f"{period}日RSI因子"
        )
        self.set_params(period=period)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算RSI因子

        Args:
            data: 包含close列的DataFrame

        Returns:
            RSI因子值（标准化后的，超买为负，超卖为正）
        """
        period = self.params.get('period', 14)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算价格变化
        delta = data['close'].diff()

        # 分离上涨和下跌
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # 计算平均涨跌
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # 计算RSI
        rs = avg_gain / (avg_loss + 1e-6)
        rsi = 100 - (100 / (1 + rs))

        # 标准化：超买(>70)为负，超卖(<30)为正
        factor = (50 - rsi) / 50

        return factor


class MACDFactor(Factor):
    """
    MACD因子

    基于MACD指标判断趋势和动量。
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """
        初始化MACD因子

        Args:
            fast: 快线周期
            slow: 慢线周期
            signal: 信号线周期
        """
        super().__init__(
            name=f"macd_{fast}_{slow}_{signal}",
            description=f"MACD因子({fast},{slow},{signal})"
        )
        self.set_params(fast=fast, slow=slow, signal=signal)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算MACD因子

        Args:
            data: 包含close列的DataFrame

        Returns:
            MACD因子值
        """
        fast = self.params.get('fast', 12)
        slow = self.params.get('slow', 26)
        signal = self.params.get('signal', 9)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算EMA
        ema_fast = data['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = data['close'].ewm(span=slow, adjust=False).mean()

        # 计算MACD线
        macd_line = ema_fast - ema_slow

        # 计算信号线
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()

        # 计算柱状图
        histogram = macd_line - signal_line

        # 综合因子
        factor = histogram / (data['close'] + 1e-6) * 100

        return factor


class BollingerFactor(Factor):
    """
    布林带因子

    基于布林带判断价格位置和波动。
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        """
        初始化布林带因子

        Args:
            period: 计算周期
            std_dev: 标准差倍数
        """
        super().__init__(
            name=f"bollinger_{period}",
            description=f"{period}日布林带因子"
        )
        self.set_params(period=period, std_dev=std_dev)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算布林带因子

        Args:
            data: 包含close/high/low列的DataFrame

        Returns:
            布林带因子值
        """
        period = self.params.get('period', 20)
        std_dev = self.params.get('std_dev', 2.0)

        if 'close' not in data.columns:
            raise ValueError("数据必须包含'close'列")

        # 计算中轨和带宽
        middle = data['close'].rolling(window=period).mean()
        std = data['close'].rolling(window=period).std()

        upper = middle + std_dev * std
        lower = middle - std_dev * std

        # 计算%b指标（价格在布林带中的位置）
        percent_b = (data['close'] - lower) / (upper - lower + 1e-6)

        # 标准化：0.5为中心，偏离越大因子绝对值越大
        factor = (percent_b - 0.5) * 2

        # 反转：接近上轨为负（卖出），接近下轨为正（买入）
        factor = -factor

        return factor


# 注册所有技术因子
register_factor(MomentumFactor(5), "technical")
register_factor(MomentumFactor(10), "technical")
register_factor(MomentumFactor(20), "technical")
register_factor(MomentumFactor(60), "technical")

register_factor(VolatilityFactor(20), "technical")
register_factor(VolatilityFactor(60), "technical")

register_factor(VolumeFactor(20), "technical")

register_factor(TrendFactor(5, 20), "technical")
register_factor(TrendFactor(10, 30), "technical")
register_factor(TrendFactor(20, 60), "technical")

register_factor(MeanReversionFactor(20), "technical")
register_factor(MeanReversionFactor(60), "technical")

register_factor(RSIFactor(14), "technical")
register_factor(RSIFactor(6), "technical")

register_factor(MACDFactor(), "technical")

register_factor(BollingerFactor(), "technical")
