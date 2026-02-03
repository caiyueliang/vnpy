"""
RQData数据采集器

使用米筐RQData获取A股行情数据
需要申请RQData的账号和许可证
"""

from datetime import datetime, time
from typing import Any

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class RQDataCollector(DataCollector):
    """
    RQData数据采集器

    使用米筐RQData获取A股行情数据，包括：
    - 日K线数据
    - 分钟K线数据
    - Tick数据
    - 基本面数据
    - 财务数据
    - 行业数据
    - 指数数据

    注意：需要申请RQData的账号和许可证
    官网：https://www.ricequant.com
    """

    def __init__(self, config: CollectorConfig | None = None) -> None:
        """Constructor"""
        if config is None:
            config = CollectorConfig(source=DataSource.RQDATA)
        super().__init__(config)

        self._rq = None

    def connect(self) -> bool:
        """
        连接RQData

        Returns:
            是否连接成功
        """
        try:
            import rqdatac as rq

            # 初始化RQData
            if self.config.api_key and self.config.api_secret:
                rq.init(self.config.api_key, self.config.api_secret)
            else:
                # 尝试使用本地配置文件
                rq.init()

            self._rq = rq

            # 测试连接
            self._rq.get_price(
                "000001.XSHE",
                start_date="2024-01-01",
                end_date="2024-01-02",
                frequency="1d"
            )

            self._connected = True
            return True

        except ImportError:
            print("RQData未安装，请运行: pip install rqdatac")
            return False
        except Exception as e:
            print(f"RQData连接失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._rq = None

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
            interval: 时间周期 (d/w/m/1m/5m/15m/30m/60m)
            start: 开始时间
            end: 结束时间

        Returns:
            K线数据列表
        """
        if not self._connected or not self._rq:
            return []

        try:
            self._requests_count += 1

            # 转换为RQData格式
            rq_symbol = self._to_rq_symbol(vt_symbol)

            # 转换周期格式
            freq_map = {
                "d": "1d",
                "w": "1w",
                "m": "1M",
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "60m": "60m",
            }
            frequency = freq_map.get(interval, "1d")

            # 获取数据
            df = self._rq.get_price(
                rq_symbol,
                start_date=start,
                end_date=end,
                frequency=frequency
            )

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

        Args:
            vt_symbol: 合约代码
            start: 开始时间
            end: 结束时间

        Returns:
            Tick数据列表
        """
        if not self._connected or not self._rq:
            return []

        try:
            self._requests_count += 1

            rq_symbol = self._to_rq_symbol(vt_symbol)

            # 获取Tick数据
            df = self._rq.get_price(
                rq_symbol,
                start_date=start,
                end_date=end,
                frequency="tick"
            )

            if df is None or df.empty:
                return []

            ticks = []
            for timestamp, row in df.iterrows():
                tick = {
                    "vt_symbol": vt_symbol,
                    "datetime": timestamp.to_pydatetime(),
                    "price": float(row.get("last", 0)),
                    "volume": int(row.get("volume", 0)),
                    "amount": float(row.get("total_turnover", 0)),
                    "bid_price_1": float(row.get("bid", 0)),
                    "ask_price_1": float(row.get("ask", 0)),
                    "bid_volume_1": int(row.get("bid_volume", 0)),
                    "ask_volume_1": int(row.get("ask_volume", 0)),
                }
                ticks.append(tick)

            self._success_count += 1
            return ticks

        except Exception as e:
            self._error_count += 1
            print(f"获取Tick数据失败: {e}")
            return []

    def _to_rq_symbol(self, vt_symbol: str) -> str:
        """
        将vt_symbol转换为RQData格式

        Args:
            vt_symbol: 合约代码 (如 "000001.SZ")

        Returns:
            RQData格式代码 (如 "000001.XSHE")
        """
        if "." in vt_symbol:
            symbol, exchange = vt_symbol.split(".")
            exchange_map = {
                "SZ": "XSHE",  # 深交所
                "SH": "XSHG",  # 上交所
                "BJ": "XBSE",  # 北交所
            }
            rq_exchange = exchange_map.get(exchange, exchange)
            return f"{symbol}.{rq_exchange}"
        return vt_symbol

    def _from_rq_symbol(self, rq_symbol: str) -> str:
        """
        将RQData格式转换为vt_symbol

        Args:
            rq_symbol: RQData代码 (如 "000001.XSHE")

        Returns:
            vt_symbol (如 "000001.SZ")
        """
        if "." in rq_symbol:
            symbol, exchange = rq_symbol.split(".")
            exchange_map = {
                "XSHE": "SZ",
                "XSHG": "SH",
                "XBSE": "BJ",
            }
            vt_exchange = exchange_map.get(exchange, exchange)
            return f"{symbol}.{vt_exchange}"
        return rq_symbol

    def _convert_to_bars(
        self,
        df: pd.DataFrame,
        vt_symbol: str,
        interval: str
    ) -> list[dict]:
        """转换为标准K线格式"""
        bars = []

        for timestamp, row in df.iterrows():
            try:
                bar = {
                    "vt_symbol": vt_symbol,
                    "datetime": timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp,
                    "interval": interval,
                    "open_price": float(row.get("open", 0)),
                    "high_price": float(row.get("high", 0)),
                    "low_price": float(row.get("low", 0)),
                    "close_price": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                    "turnover": float(row.get("total_turnover", 0)),
                    "open_interest": 0,
                }
                bars.append(bar)
            except Exception as e:
                print(f"转换K线数据失败: {e}")
                continue

        return bars

    def get_stock_list(self) -> list[dict]:
        """
        获取A股股票列表

        Returns:
            股票列表
        """
        if not self._connected or not self._rq:
            return []

        try:
            # 获取所有A股
            df = self._rq.all_instruments(type="CS")

            stocks = []
            for _, row in df.iterrows():
                stock = {
                    "symbol": row["order_book_id"].split(".")[0],
                    "name": row.get("symbol", ""),
                    "exchange": self._from_rq_symbol(row["order_book_id"]).split(".")[1],
                    "list_date": row.get("listed_date", ""),
                    "de_listed_date": row.get("de_listed_date", ""),
                }
                stocks.append(stock)

            return stocks

        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []

    def get_fundamentals(
        self,
        vt_symbol: str,
        fields: list[str] | None = None,
        trade_date: str | None = None
    ) -> dict:
        """
        获取基本面数据

        Args:
            vt_symbol: 合约代码
            fields: 字段列表
            trade_date: 交易日期 (YYYYMMDD)

        Returns:
            基本面数据
        """
        if not self._connected or not self._rq:
            return {}

        try:
            rq_symbol = self._to_rq_symbol(vt_symbol)

            if trade_date:
                date = datetime.strptime(trade_date, "%Y%m%d")
            else:
                date = datetime.now()

            # 获取基本面数据
            df = self._rq.get_fundamentals(
                self._rq.query(self._rq.financials).filter(
                    self._rq.financials.stock_code == rq_symbol
                ),
                entry_date=date,
                interval="1q"
            )

            if df is None or df.empty:
                return {}

            return df.iloc[0].to_dict()

        except Exception as e:
            print(f"获取基本面数据失败: {e}")
            return {}

    def get_financial_report(
        self,
        vt_symbol: str,
        report_type: str = "income",
        quarter: str | None = None
    ) -> list[dict]:
        """
        获取财务报表数据

        Args:
            vt_symbol: 合约代码
            report_type: 报表类型 (income/balance/cash_flow)
            quarter: 季度 (如 "2024q1")

        Returns:
            财务报表数据列表
        """
        if not self._connected or not self._rq:
            return []

        try:
            rq_symbol = self._to_rq_symbol(vt_symbol)

            # 获取财务数据
            if report_type == "income":
                df = self._rq.get_financials(
                    rq_symbol,
                    fields=[
                        "total_operating_revenue",
                        "operating_revenue",
                        "total_operating_cost",
                        "operating_cost",
                        "operating_profit",
                        "total_profit",
                        "net_profit",
                        "eps",
                    ]
                )
            elif report_type == "balance":
                df = self._rq.get_financials(
                    rq_symbol,
                    fields=[
                        "total_assets",
                        "total_liabilities",
                        "equity",
                        "cash_and_equivalents",
                    ]
                )
            elif report_type == "cash_flow":
                df = self._rq.get_financials(
                    rq_symbol,
                    fields=[
                        "net_operating_cash_flow",
                        "net_investing_cash_flow",
                        "net_financing_cash_flow",
                    ]
                )
            else:
                return []

            if df is None or df.empty:
                return []

            reports = []
            for timestamp, row in df.iterrows():
                report = {
                    "quarter": timestamp.strftime("%Yq%q"),
                    "data": row.to_dict(),
                }
                reports.append(report)

            return reports

        except Exception as e:
            print(f"获取财务报表失败: {e}")
            return []

    def get_industry_stocks(self, industry_code: str) -> list[dict]:
        """
        获取行业成分股

        Args:
            industry_code: 行业代码

        Returns:
            成分股列表
        """
        if not self._connected or not self._rq:
            return []

        try:
            # 获取行业成分股
            stocks = self._rq.get_industry_stocks(industry_code)

            result = []
            for rq_symbol in stocks:
                vt_symbol = self._from_rq_symbol(rq_symbol)
                result.append({
                    "vt_symbol": vt_symbol,
                    "rq_symbol": rq_symbol,
                })

            return result

        except Exception as e:
            print(f"获取行业成分股失败: {e}")
            return []

    def get_index_stocks(self, index_symbol: str) -> list[dict]:
        """
        获取指数成分股

        Args:
            index_symbol: 指数代码 (如 "000001.XSHG")

        Returns:
            成分股列表
        """
        if not self._connected or not self._rq:
            return []

        try:
            rq_index = self._to_rq_symbol(index_symbol)

            # 获取指数成分股
            stocks = self._rq.get_index_stocks(rq_index)

            result = []
            for rq_symbol in stocks:
                vt_symbol = self._from_rq_symbol(rq_symbol)
                result.append({
                    "vt_symbol": vt_symbol,
                    "rq_symbol": rq_symbol,
                })

            return result

        except Exception as e:
            print(f"获取指数成分股失败: {e}")
            return []

    def get_factor_data(
        self,
        vt_symbols: list[str],
        factor_name: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """
        获取因子数据

        Args:
            vt_symbols: 合约代码列表
            factor_name: 因子名称
            start: 开始时间
            end: 结束时间

        Returns:
            因子数据DataFrame
        """
        if not self._connected or not self._rq:
            return None

        try:
            # 转换为RQData格式
            rq_symbols = [self._to_rq_symbol(s) for s in vt_symbols]

            # 获取因子数据
            df = self._rq.get_factor_values(
                rq_symbols,
                factor_name,
                start_date=start,
                end_date=end
            )

            return df

        except Exception as e:
            print(f"获取因子数据失败: {e}")
            return None

    def get_yield_curve(self, date: datetime | None = None) -> list[dict]:
        """
        获取收益率曲线

        Args:
            date: 日期

        Returns:
            收益率曲线数据
        """
        if not self._connected or not self._rq:
            return []

        try:
            if date is None:
                date = datetime.now()

            # 获取收益率曲线
            df = self._rq.get_yield_curve(date)

            if df is None or df.empty:
                return []

            curves = []
            for _, row in df.iterrows():
                curve = {
                    "maturity": row.get("maturity", ""),
                    "yield": float(row.get("yield", 0)),
                }
                curves.append(curve)

            return curves

        except Exception as e:
            print(f"获取收益率曲线失败: {e}")
            return []
