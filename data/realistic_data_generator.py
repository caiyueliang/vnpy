"""
改进的模拟数据生成器

使用真实的市场统计特征生成更真实的模拟数据
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval


# A股市场真实统计特征（基于历史数据）
MARKET_FEATURES = {
    "日收益率分布": {
        "mean": 0.0005,      # 平均日收益率 0.05%
        "std": 0.02,         # 日收益率标准差 2%
        "skew": -0.3,        # 负偏（下跌更多）
        "kurt": 5.0,          # 尖峰（极端值）
    },
    "波动率分布": {
        "mean": 0.02,         # 平均日波动率 2%
        "std": 0.01,
        "min": 0.005,
        "max": 0.05,
    },
    "成交量特征": {
        "avg_turnover_ratio": 0.05,  # 平均换手率 5%
        "volume_volatility": 0.3,   # 成交量波动率
    },
    "行业特征": {
        "白酒": {"beta": 1.2, "volatility": 0.025},
        "银行金融": {"beta": 0.8, "volatility": 0.015},
        "新能源": {"beta": 1.5, "volatility": 0.035},
        "科技半导体": {"beta": 1.4, "volatility": 0.03},
        "汽车制造": {"beta": 1.3, "volatility": 0.028},
        "房地产基建": {"beta": 1.1, "volatility": 0.022},
        "石油化工": {"beta": 1.0, "volatility": 0.02},
        "有色钢铁": {"beta": 1.2, "volatility": 0.025},
        "通信传媒": {"beta": 1.1, "volatility": 0.022},
        "消费零售": {"beta": 1.0, "volatility": 0.018},
    },
}


class RealisticDataGenerator:
    """
    真实模拟数据生成器
    
    特性：
    1. 使用真实的市场统计特征
    2. 行业差异化
    3. 动量效应
    4. 均值回归
    5. 波动率聚集
    """
    
    def __init__(self, seed: int = None):
        """Constructor"""
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)
    
    def _get_sector_features(self, symbol: str, sector: str = None) -> dict:
        """获取行业特征"""
        if sector and sector in MARKET_FEATURES["行业特征"]:
            return MARKET_FEATURES["行业特征"][sector]
        
        for sector_name, symbols in STOCKS_100.items():
            if symbol in symbols:
                return MARKET_FEATURES["行业特征"][sector_name]
        return MARKET_FEATURES["行业特征"]["银行金融"]  # 默认
    
    def _generate_price_path(
        self,
        base_price: float,
        volatility: float,
        beta: float,
        num_days: int,
        trend: float = 0.0002
    ) -> List[float]:
        """
        生成价格路径
        
        使用几何布朗运动，加入动量效应和均值回归
        """
        prices = [base_price]
        current_price = base_price
        
        # 动量参数
        momentum_strength = 0.3
        mean_reversion_strength = 0.1
        
        for i in range(num_days):
            # 基础收益率（市场趋势 + 行业Beta）
            base_return = trend + beta * np.random.normal(0, 0.01)
            
            # 动量效应（过去收益率影响）
            momentum = 0.0
            if len(prices) >= 5:
                past_returns = []
                for j in range(len(prices)-5, len(prices)-1):
                    if j >= 0 and j+1 < len(prices):
                        past_returns.append((prices[j+1] - prices[j]) / prices[j])
                if past_returns:
                    momentum = np.mean(past_returns) * momentum_strength
            
            # 均值回归（价格偏离长期均值时回归）
            mean_reversion = 0.0
            if len(prices) >= 20:
                long_term_mean = np.mean(prices[-20:])
                mean_reversion = (long_term_mean - current_price) / current_price * mean_reversion_strength
            
            # 波动率聚集（高波动后跟随高波动）
            vol_adjustment = 0.0
            if len(prices) >= 10:
                recent_returns = []
                for j in range(len(prices)-10, len(prices)-1):
                    if j >= 0 and j+1 < len(prices):
                        recent_returns.append(abs((prices[j+1] - prices[j]) / prices[j]))
                if recent_returns:
                    recent_volatility = np.std(recent_returns)
                    vol_adjustment = (recent_volatility - volatility) * 0.5
            
            # 综合收益率
            total_volatility = volatility * (1 + vol_adjustment)
            daily_return = base_return + momentum + mean_reversion
            
            # 应用波动率
            price_change = current_price * daily_return * total_volatility
            
            # 添加随机噪声
            noise = np.random.normal(0, volatility * current_price * 0.5)
            
            current_price = current_price + price_change + noise
            current_price = max(current_price, base_price * 0.5)  # 价格下限
            
            prices.append(current_price)
        
        return prices
    
    def _generate_ohlc(
        self,
        prices: List[float],
        base_volume: float
    ) -> List[dict]:
        """
        生成OHLC数据
        
        基于日内波动率生成
        """
        ohlc_data = []
        
        for i, close_price in enumerate(prices):
            # 日内波动率（基于日收益率）
            if i > 0:
                daily_return = abs((close_price - prices[i-1]) / prices[i-1])
                intraday_volatility = daily_return * 0.3
            else:
                intraday_volatility = 0.01
            
            # 开盘价（基于前一日收盘价）
            if i > 0:
                open_price = prices[i-1] * (1 + np.random.normal(0, intraday_volatility * 0.5))
            else:
                open_price = close_price
            
            # 最高价和最低价
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, intraday_volatility)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, intraday_volatility)))
            
            # 成交量（基于价格变动）
            if i > 0:
                price_change = abs(close_price - prices[i-1]) / prices[i-1]
                volume_change = 1 + price_change * 5 + np.random.normal(0, 0.3)
                volume = base_volume * volume_change
            else:
                volume = base_volume
            
            # 确保成交量为正整数
            volume = max(int(volume), 100000)
            
            ohlc_data.append({
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            })
        
        return ohlc_data
    
    def generate_stock_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        sector: str = None
    ) -> List[BarData]:
        """
        生成单只股票数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            sector: 行业（可选）
        
        Returns:
            K线数据列表
        """
        # 获取行业特征
        sector_features = self._get_sector_features(symbol, sector)
        
        # 基础价格（根据行业调整）
        base_price = random.uniform(10, 200) * sector_features["beta"]
        volatility = sector_features["volatility"]
        beta = sector_features["beta"]
        
        # 生成交易日
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        num_days = len(dates)
        
        # 生成价格路径
        prices = self._generate_price_path(
            base_price=base_price,
            volatility=volatility,
            beta=beta,
            num_days=num_days
        )
        
        # 生成OHLC
        ohlc_data = self._generate_ohlc(prices, base_price * 10000)
        
        # 转换为BarData对象
        bars = []
        
        # 解析交易所
        if ".SH" in symbol:
            exchange = Exchange.SSE
        elif ".SZ" in symbol:
            exchange = Exchange.SZSE
        else:
            exchange = Exchange.SZSE
        
        # 生成正确的vt_symbol
        if ".SH" in symbol:
            vt_symbol = symbol.replace(".SH", ".SSE")
        elif ".SZ" in symbol:
            vt_symbol = symbol.replace(".SZ", ".SZSE")
        else:
            vt_symbol = symbol + ".SZSE"
        
        for date, ohlc in zip(dates, ohlc_data):
            bar = BarData(
                symbol=symbol.split(".")[0],
                exchange=exchange,
                datetime=date,
                interval=Interval.DAILY,
                open_price=round(ohlc["open"], 2),
                high_price=round(ohlc["high"], 2),
                low_price=round(ohlc["low"], 2),
                close_price=round(ohlc["close"], 2),
                volume=ohlc["volume"],
                open_interest=0,
                gateway_name="BACKTEST"
            )
            bars.append(bar)
        
        return vt_symbol, bars
    
    def generate_multiple_stocks(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        progress_callback: callable = None
    ) -> Dict[str, List[BarData]]:
        """
        批量生成多只股票数据
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            progress_callback: 进度回调
        
        Returns:
            股票数据字典
        """
        all_data = {}
        
        print(f"\n开始生成 {len(symbols)} 只股票模拟数据...")
        print(f"时间范围: {start_date.date()} 至 {end_date.date()}")
        print(f"使用真实市场统计特征")
        
        for i, symbol in enumerate(symbols, 1):
            try:
                vt_symbol, bars = self.generate_stock_data(symbol, start_date, end_date)
                
                if bars and len(bars) > 50:
                    all_data[vt_symbol] = bars
                    print(f"[{i}/{len(symbols)}] ✓ {symbol} ({len(bars)}条)")
                else:
                    print(f"[{i}/{len(symbols)}] ✗ {symbol} (数据不足)")
                
                # 进度回调
                if progress_callback:
                    progress_callback(i, len(symbols), symbol, len(bars) if bars else 0)
            
            except Exception as e:
                print(f"[{i}/{len(symbols)}] ✗ {symbol} (错误: {e})")
        
        print(f"\n成功生成 {len(all_data)} 只股票数据")
        return all_data


# 100只A股标的
STOCKS_100 = {
    "白酒": ["600519.SH", "000858.SZ", "000568.SZ", "002304.SZ", "600809.SH", "600887.SH", "603288.SH", "600276.SH", "000538.SZ", "603259.SH"],
    "银行金融": ["600036.SH", "601398.SH", "601288.SH", "601939.SH", "601988.SH", "601318.SH", "601628.SH", "600030.SH", "601688.SH", "600837.SH"],
    "新能源": ["300750.SZ", "601012.SH", "600438.SH", "002594.SZ", "601669.SH", "601727.SH", "600900.SH", "601985.SH", "600011.SH", "601016.SH"],
    "科技半导体": ["688981.SH", "603501.SH", "002371.SZ", "688012.SH", "603986.SH", "002049.SZ", "688008.SH", "300782.SZ", "600584.SH", "002156.SZ"],
    "汽车制造": ["601127.SH", "000625.SZ", "600104.SH", "601633.SH", "601238.SH", "000338.SZ", "600660.SH", "601766.SH", "601989.SH", "600031.SH"],
    "房地产基建": ["000002.SZ", "600048.SH", "001979.SZ", "600606.SH", "601668.SH", "601390.SH", "601800.SH", "601186.SH", "601117.SH", "600170.SH"],
    "石油化工": ["601857.SH", "600028.SH", "600938.SH", "002493.SZ", "600346.SH", "600309.SH", "002648.SZ", "600426.SH", "601233.SH", "603225.SH"],
    "有色钢铁": ["601899.SH", "603993.SH", "600111.SH", "600362.SH", "601600.SH", "600019.SH", "000932.SZ", "600507.SH", "002110.SZ", "600808.SH"],
    "通信传媒": ["600941.SH", "600050.SH", "601728.SH", "000063.SZ", "600498.SH", "603444.SH", "002624.SZ", "300413.SZ", "002027.SZ", "600088.SH"],
    "消费零售": ["601888.SH", "600859.SH", "002024.SZ", "601933.SH", "600729.SH", "002419.SZ", "600697.SH", "600827.SH", "000501.SZ", "600785.SH"],
}


def get_all_symbols() -> List[str]:
    """获取所有100只标的代码"""
    symbols = []
    for sector, stocks in STOCKS_100.items():
        symbols.extend(stocks)
    return symbols
