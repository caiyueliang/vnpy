"""
AKShare数据采集器

使用AKShare获取A股免费行情数据
"""

from datetime import datetime
from typing import Any

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class AKShareCollector(DataCollector):
    """
    AKShare数据采集器

    使用AKShare获取A股行情数据，包括：
    - 日K线数据
    - 分钟K线数据
    - 实时行情
    - 基本面数据
    """

    def __init__(self, config: CollectorConfig | None = None) -> None:
        """Constructor"""
        if config is None:
            config = CollectorConfig(source=DataSource.AKSHARE)
        super().__init__(config)

        self._ak = None

    def connect(self) -> bool:
        """
        连接AKShare

        Returns:
            是否连接成功
        """
        try:
            import akshare as ak
            self._ak = ak
            self._connected = True
            return True
        except ImportError:
            print("AKShare未安装，请运行: pip install akshare")
            return False
        except Exception as e:
            print(f"AKShare连接失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._ak = None

    def get_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """
        获取K线数据

        Args:
            vt_symbol: 合约代码 (如 "000001.SZ")
            interval: 时间周期 (d/1m/5m/15m/30m/60m)
            start: 开始时间
            end: 结束时间

        Returns:
            K线数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            # 解析合约代码
            symbol, exchange = self._parse_vt_symbol(vt_symbol)

            # 根据周期选择接口
            if interval == "d":
                df = self._get_daily_data(symbol, start, end)
            elif interval in ["1m", "5m", "15m", "30m", "60m"]:
                df = self._get_minute_data(symbol, interval, start, end)
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
            print(f"获取K线数据失败: {e}")
            return []

    def get_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """
        获取Tick数据

        Note: AKShare暂不支持历史Tick数据
        """
        print("AKShare暂不支持历史Tick数据")
        return []

    def _parse_vt_symbol(self, vt_symbol: str) -> tuple[str, str]:
        """
        解析vt_symbol

        Args:
            vt_symbol: 合约代码 (如 "000001.SZ")

        Returns:
            (symbol, exchange)
        """
        if "." in vt_symbol:
            symbol, exchange = vt_symbol.split(".")
            return symbol, exchange
        return vt_symbol, "SZ"

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
            print(f"获取日线数据失败: {e}")
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
            print(f"获取分钟线数据失败: {e}")
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

    def get_stock_list(self) -> list[dict]:
        """
        获取A股股票列表

        Returns:
            股票列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            df = self._ak.stock_zh_a_spot_em()

            stocks = []
            for _, row in df.iterrows():
                stock = {
                    "symbol": row["代码"],
                    "name": row["名称"],
                    "exchange": "SZ" if row["代码"].startswith(("00", "30")) else "SH",
                    "price": float(row.get("最新价", 0)),
                    "change_pct": float(row.get("涨跌幅", 0)),
                }
                stocks.append(stock)

            return stocks

        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []

    def get_realtime_quotes(self, symbols: list[str]) -> list[dict]:
        """
        获取实时行情

        Args:
            symbols: 股票代码列表

        Returns:
            实时行情列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            quotes = []

            for symbol in symbols:
                try:
                    df = self._ak.stock_zh_a_spot_em()
                    df = df[df["代码"] == symbol]

                    if not df.empty:
                        row = df.iloc[0]
                        quote = {
                            "symbol": symbol,
                            "price": float(row.get("最新价", 0)),
                            "change": float(row.get("涨跌额", 0)),
                            "change_pct": float(row.get("涨跌幅", 0)),
                            "volume": float(row.get("成交量", 0)),
                            "turnover": float(row.get("成交额", 0)),
                            "bid_price": float(row.get("买一", 0)),
                            "ask_price": float(row.get("卖一", 0)),
                            "bid_volume": float(row.get("买一量", 0)),
                            "ask_volume": float(row.get("卖一量", 0)),
                        }
                        quotes.append(quote)
                except Exception as e:
                    print(f"获取{symbol}实时行情失败: {e}")

            return quotes

        except Exception as e:
            print(f"获取实时行情失败: {e}")
            return []
