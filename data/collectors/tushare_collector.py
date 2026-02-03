"""
Tushare数据采集器

使用Tushare Pro获取A股行情数据
需要申请Tushare Pro的API Token
"""

from datetime import datetime
from typing import Any

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class TushareCollector(DataCollector):
    """
    Tushare数据采集器

    使用Tushare Pro获取A股行情数据，包括：
    - 日K线数据
    - 分钟K线数据
    - Tick数据（需权限）
    - 基本面数据
    - 财务数据
    - 市场参考数据

    注意：需要申请Tushare Pro的API Token
    官网：https://tushare.pro
    """

    def __init__(self, config: CollectorConfig | None = None) -> None:
        """Constructor"""
        if config is None:
            config = CollectorConfig(source=DataSource.TUSHARE)
        super().__init__(config)

        self._pro = None
        self._ts = None

    def connect(self) -> bool:
        """
        连接Tushare

        Returns:
            是否连接成功
        """
        try:
            import tushare as ts

            if not self.config.api_key:
                print("Tushare需要API Token，请在配置中提供")
                return False

            # 设置Token
            ts.set_token(self.config.api_key)

            # 初始化Pro接口
            self._pro = ts.pro_api()
            self._ts = ts

            # 测试连接
            self._pro.query('stock_basic', limit=1)

            self._connected = True
            return True

        except ImportError:
            print("Tushare未安装，请运行: pip install tushare")
            return False
        except Exception as e:
            print(f"Tushare连接失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._pro = None
        self._ts = None

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
        if not self._connected or not self._pro:
            return []

        try:
            self._requests_count += 1

            # 解析合约代码
            ts_code = self._to_ts_code(vt_symbol)

            # 根据周期选择接口
            if interval == "d":
                df = self._get_daily_data(ts_code, start, end)
            elif interval == "w":
                df = self._get_weekly_data(ts_code, start, end)
            elif interval == "m":
                df = self._get_monthly_data(ts_code, start, end)
            elif interval in ["1m", "5m", "15m", "30m", "60m"]:
                df = self._get_minute_data(ts_code, interval, start, end)
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

        Note: 需要Tushare Pro的高级权限
        """
        if not self._connected or not self._pro:
            return []

        try:
            self._requests_count += 1

            ts_code = self._to_ts_code(vt_symbol)
            trade_date = start.strftime("%Y%m%d")

            # 获取Tick数据
            df = self._pro.query(
                'stk_tick',
                ts_code=ts_code,
                trade_date=trade_date
            )

            if df is None or df.empty:
                return []

            ticks = []
            for _, row in df.iterrows():
                tick = {
                    "vt_symbol": vt_symbol,
                    "datetime": pd.to_datetime(f"{row['trade_date']} {row['time']}"),
                    "price": float(row['price']),
                    "volume": int(row['vol']),
                    "amount": float(row['amount']),
                    "bid_price_1": float(row.get('bid', 0)),
                    "ask_price_1": float(row.get('ask', 0)),
                }
                ticks.append(tick)

            self._success_count += 1
            return ticks

        except Exception as e:
            self._error_count += 1
            print(f"获取Tick数据失败: {e}")
            return []

    def _to_ts_code(self, vt_symbol: str) -> str:
        """
        将vt_symbol转换为Tushare格式

        Args:
            vt_symbol: 合约代码 (如 "000001.SZ")

        Returns:
            Tushare格式代码 (如 "000001.SZ")
        """
        if "." in vt_symbol:
            symbol, exchange = vt_symbol.split(".")
            return f"{symbol}.{exchange}"
        return vt_symbol

    def _from_ts_code(self, ts_code: str) -> str:
        """
        将Tushare格式转换为vt_symbol

        Args:
            ts_code: Tushare代码 (如 "000001.SZ")

        Returns:
            vt_symbol (如 "000001.SZ")
        """
        return ts_code

    def _get_daily_data(
        self,
        ts_code: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """获取日K线数据"""
        try:
            df = self._pro.query(
                'daily',
                ts_code=ts_code,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d")
            )

            if df is not None and not df.empty:
                # 获取复权因子
                adj_df = self._pro.query(
                    'adj_factor',
                    ts_code=ts_code,
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d")
                )

                if adj_df is not None and not adj_df.empty:
                    # 合并数据进行前复权
                    df = df.merge(adj_df[['trade_date', 'adj_factor']], on='trade_date')
                    df['open'] = df['open'] * df['adj_factor'] / df['adj_factor'].iloc[-1]
                    df['high'] = df['high'] * df['adj_factor'] / df['adj_factor'].iloc[-1]
                    df['low'] = df['low'] * df['adj_factor'] / df['adj_factor'].iloc[-1]
                    df['close'] = df['close'] * df['adj_factor'] / df['adj_factor'].iloc[-1]

            return df

        except Exception as e:
            print(f"获取日线数据失败: {e}")
            return None

    def _get_weekly_data(
        self,
        ts_code: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """获取周K线数据"""
        try:
            df = self._pro.query(
                'weekly',
                ts_code=ts_code,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d")
            )
            return df
        except Exception as e:
            print(f"获取周线数据失败: {e}")
            return None

    def _get_monthly_data(
        self,
        ts_code: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """获取月K线数据"""
        try:
            df = self._pro.query(
                'monthly',
                ts_code=ts_code,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d")
            )
            return df
        except Exception as e:
            print(f"获取月线数据失败: {e}")
            return None

    def _get_minute_data(
        self,
        ts_code: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """获取分钟K线数据"""
        try:
            # 转换周期格式
            freq_map = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "60m": "60min",
            }
            freq = freq_map.get(interval, "1min")

            # Tushare分钟数据需要逐日获取
            df_list = []
            current_date = start

            while current_date <= end:
                trade_date = current_date.strftime("%Y%m%d")

                try:
                    df = self._pro.query(
                        'stk_mins',
                        ts_code=ts_code,
                        freq=freq,
                        trade_date=trade_date
                    )

                    if df is not None and not df.empty:
                        df_list.append(df)

                except Exception as e:
                    print(f"获取{trade_date}分钟数据失败: {e}")

                current_date += pd.Timedelta(days=1)

            if df_list:
                return pd.concat(df_list, ignore_index=True)
            return None

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

        # 确保列名统一
        column_mapping = {
            'trade_date': 'date',
            'trade_time': 'time',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'vol': 'volume',
            'volume': 'volume',
            'amount': 'turnover',
        }

        df = df.rename(columns=column_mapping)

        for _, row in df.iterrows():
            try:
                # 处理日期时间
                if 'date' in row:
                    if isinstance(row['date'], str):
                        if len(row['date']) == 8:  # YYYYMMDD
                            dt = datetime.strptime(row['date'], "%Y%m%d")
                        else:
                            dt = pd.to_datetime(row['date'])
                    else:
                        dt = pd.to_datetime(row['date'])
                else:
                    dt = datetime.now()

                bar = {
                    "vt_symbol": vt_symbol,
                    "datetime": dt,
                    "interval": interval,
                    "open_price": float(row.get("open", 0)),
                    "high_price": float(row.get("high", 0)),
                    "low_price": float(row.get("low", 0)),
                    "close_price": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                    "turnover": float(row.get("turnover", 0)),
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
        if not self._connected or not self._pro:
            return []

        try:
            df = self._pro.query('stock_basic', exchange='', list_status='L')

            stocks = []
            for _, row in df.iterrows():
                stock = {
                    "symbol": row["ts_code"].split(".")[0],
                    "name": row["name"],
                    "exchange": row["exchange"],
                    "industry": row.get("industry", ""),
                    "list_date": row.get("list_date", ""),
                }
                stocks.append(stock)

            return stocks

        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []

    def get_daily_basic(self, trade_date: str) -> list[dict]:
        """
        获取每日指标数据

        Args:
            trade_date: 交易日期 (YYYYMMDD)

        Returns:
            每日指标列表
        """
        if not self._connected or not self._pro:
            return []

        try:
            df = self._pro.query('daily_basic', trade_date=trade_date)

            indicators = []
            for _, row in df.iterrows():
                indicator = {
                    "ts_code": row["ts_code"],
                    "trade_date": row["trade_date"],
                    "close": float(row.get("close", 0)),
                    "turnover_rate": float(row.get("turnover_rate", 0)),
                    "turnover_rate_f": float(row.get("turnover_rate_f", 0)),
                    "volume_ratio": float(row.get("volume_ratio", 0)),
                    "pe": float(row.get("pe", 0)),
                    "pe_ttm": float(row.get("pe_ttm", 0)),
                    "pb": float(row.get("pb", 0)),
                    "ps": float(row.get("ps", 0)),
                    "ps_ttm": float(row.get("ps_ttm", 0)),
                    "dv_ratio": float(row.get("dv_ratio", 0)),
                    "dv_ttm": float(row.get("dv_ttm", 0)),
                    "total_share": float(row.get("total_share", 0)),
                    "float_share": float(row.get("float_share", 0)),
                    "free_share": float(row.get("free_share", 0)),
                    "total_mv": float(row.get("total_mv", 0)),
                    "circ_mv": float(row.get("circ_mv", 0)),
                }
                indicators.append(indicator)

            return indicators

        except Exception as e:
            print(f"获取每日指标失败: {e}")
            return []

    def get_money_flow(self, trade_date: str) -> list[dict]:
        """
        获取资金流向数据

        Args:
            trade_date: 交易日期 (YYYYMMDD)

        Returns:
            资金流向列表
        """
        if not self._connected or not self._pro:
            return []

        try:
            df = self._pro.query('moneyflow', trade_date=trade_date)

            flows = []
            for _, row in df.iterrows():
                flow = {
                    "ts_code": row["ts_code"],
                    "trade_date": row["trade_date"],
                    "buy_sm_vol": int(row.get("buy_sm_vol", 0)),
                    "buy_sm_amount": float(row.get("buy_sm_amount", 0)),
                    "sell_sm_vol": int(row.get("sell_sm_vol", 0)),
                    "sell_sm_amount": float(row.get("sell_sm_amount", 0)),
                    "buy_md_vol": int(row.get("buy_md_vol", 0)),
                    "buy_md_amount": float(row.get("buy_md_amount", 0)),
                    "sell_md_vol": int(row.get("sell_md_vol", 0)),
                    "sell_md_amount": float(row.get("sell_md_amount", 0)),
                    "buy_lg_vol": int(row.get("buy_lg_vol", 0)),
                    "buy_lg_amount": float(row.get("buy_lg_amount", 0)),
                    "sell_lg_vol": int(row.get("sell_lg_vol", 0)),
                    "sell_lg_amount": float(row.get("sell_lg_amount", 0)),
                    "buy_elg_vol": int(row.get("buy_elg_vol", 0)),
                    "buy_elg_amount": float(row.get("buy_elg_amount", 0)),
                    "sell_elg_vol": int(row.get("sell_elg_vol", 0)),
                    "sell_elg_amount": float(row.get("sell_elg_amount", 0)),
                    "net_mf_vol": int(row.get("net_mf_vol", 0)),
                    "net_mf_amount": float(row.get("net_mf_amount", 0)),
                }
                flows.append(flow)

            return flows

        except Exception as e:
            print(f"获取资金流向失败: {e}")
            return []

    def get_limit_list(self, trade_date: str) -> list[dict]:
        """
        获取涨跌停股票列表

        Args:
            trade_date: 交易日期 (YYYYMMDD)

        Returns:
            涨跌停股票列表
        """
        if not self._connected or not self._pro:
            return []

        try:
            df = self._pro.query('limit_list', trade_date=trade_date)

            limits = []
            for _, row in df.iterrows():
                limit = {
                    "ts_code": row["ts_code"],
                    "trade_date": row["trade_date"],
                    "name": row.get("name", ""),
                    "close": float(row.get("close", 0)),
                    "pct_chg": float(row.get("pct_chg", 0)),
                    "amp": float(row.get("amp", 0)),
                    "fc_ratio": float(row.get("fc_ratio", 0)),
                    "fl_ratio": float(row.get("fl_ratio", 0)),
                    "fd_amount": float(row.get("fd_amount", 0)),
                    "first_time": row.get("first_time", ""),
                    "last_time": row.get("last_time", ""),
                    "open_times": int(row.get("open_times", 0)),
                    "strth": float(row.get("strth", 0)),
                    "limit": row.get("limit", ""),  # U-涨停, D-跌停
                }
                limits.append(limit)

            return limits

        except Exception as e:
            print(f"获取涨跌停列表失败: {e}")
            return []
