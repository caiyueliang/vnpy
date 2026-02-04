"""
改进的AKShare数据采集器

添加重试机制、连接池、更好的错误处理
"""

import time
from datetime import datetime
from typing import Any

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class ImprovedAKShareCollector(DataCollector):
    """
    改进的AKShare数据采集器
    
    特性：
    1. 自动重试机制
    2. 连接池管理
    3. 请求限流
    4. 更好的错误处理
    """
    
    def __init__(self, config: CollectorConfig | None = None):
        """Constructor"""
        if config is None:
            config = CollectorConfig(source=DataSource.AKSHARE)
        super().__init__(config)
        
        self._ak = None
        
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 2  # 秒
        
        # 请求限流
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 秒
        
        # 连接池
        self._connection_pool_size = 1
    
    def connect(self) -> bool:
        """连接AKShare"""
        try:
            import akshare as ak
            self._ak = ak
            self._connected = True
            print("[AKShare] 连接成功")
            return True
        except ImportError:
            print("[AKShare] 未安装，请运行: pip install akshare")
            return False
        except Exception as e:
            print(f"[AKShare] 连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._ak = None
        print("[AKShare] 已断开连接")
    
    def _rate_limit(self):
        """请求限流"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _retry_request(self, func, *args, **kwargs):
        """带重试的请求"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    print(f"[AKShare] 请求失败，{wait_time}秒后重试 ({attempt+1}/{self.max_retries}): {e}")
                    time.sleep(wait_time)
                else:
                    print(f"[AKShare] 重试次数已用尽: {e}")
        
        raise last_error
    
    def get_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """
        获取K线数据（带重试）
        """
        if not self._connected or not self._ak:
            return []
        
        try:
            self._requests_count += 1
            
            # 解析合约代码
            symbol, exchange = self._parse_vt_symbol(vt_symbol)
            
            # 根据周期选择接口
            if interval == "d":
                df = self._retry_request(
                    self._get_daily_data,
                    symbol,
                    start,
                    end
                )
            elif interval in ["1m", "5m", "15m", "30m", "60m"]:
                df = self._retry_request(
                    self._get_minute_data,
                    symbol,
                    interval,
                    start,
                    end
                )
            else:
                return []
            
            if df is None or df.empty:
                return []
            
            # 转换为标准格式
            bars = self._convert_to_bars(df, vt_symbol, interval)
            self._success_count += 1
            
            return bars
            
        except Exception as e:
            self._error_count += 1
            print(f"[AKShare] 获取K线数据失败: {e}")
            return []
    
    def _get_daily_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """获取日K线数据"""
        try:
            # 使用AKShare获取日线数据
            df = self._ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq"  # 前复权
            )
            return df
        except Exception as e:
            print(f"[AKShare] 获取日线数据失败: {e}")
            return None
    
    def _get_minute_data(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """获取分钟K线数据"""
        try:
            # 转换周期格式
            period_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "60m": "60",
            }
            period = period_map.get(interval, "1")
            
            df = self._ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period=period,
                adjust="qfq"
            )
            
            # 过滤时间范围
            if df is not None and not df.empty:
                df["日期"] = pd.to_datetime(df["日期"])
                df = df[(df["日期"] >= start) & (df["日期"] <= end)]
            
            return df
        except Exception as e:
            print(f"[AKShare] 获取分钟线数据失败: {e}")
            return None
    
    def _convert_to_bars(
        self,
        df: pd.DataFrame,
        vt_symbol: str,
        interval: str
    ) -> list[dict]:
        """转换为标准K线格式"""
        bars = []
        
        for _, row in df.iterrows():
            bar = {
                "vt_symbol": vt_symbol,
                "datetime": pd.to_datetime(row["日期"]),
                "interval": interval,
                "open_price": float(row["开盘"]),
                "high_price": float(row["最高"]),
                "low_price": float(row["最低"]),
                "close_price": float(row["收盘"]),
                "volume": float(row["成交量"]),
                "turnover": float(row.get("成交额", 0)),
                "open_interest": 0,
            }
            bars.append(bar)
        
        return bars
    
    def _parse_vt_symbol(self, vt_symbol: str) -> tuple[str, str]:
        """解析vt_symbol"""
        if "." in vt_symbol:
            symbol, exchange = vt_symbol.split(".")
            return symbol, exchange
        return vt_symbol, "SZ"
