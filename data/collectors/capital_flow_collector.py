"""
资金流向数据采集器

采集A股市场资金流向数据：
1. 个股资金流向（主力、散户、大单、小单）
2. 板块资金流向
3. 北向资金流向
4. 龙虎榜数据
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class CapitalFlowType(Enum):
    """资金流向类型"""
    MAIN_FORCE = "main_force"       # 主力资金
    RETAIL = "retail"               # 散户资金
    LARGE_ORDER = "large_order"     # 大单
    MEDIUM_ORDER = "medium_order"   # 中单
    SMALL_ORDER = "small_order"     # 小单
    NORTH_BOUND = "north_bound"     # 北向资金
    SOUTH_BOUND = "south_bound"     # 南向资金


@dataclass
class CapitalFlowData:
    """资金流向数据"""
    symbol: str                     # 股票代码
    datetime: datetime              # 时间
    flow_type: CapitalFlowType      # 流向类型
    inflow: float                   # 流入金额（万元）
    outflow: float                  # 流出金额（万元）
    net_flow: float                 # 净流入（万元）
    inflow_volume: int              # 流入股数
    outflow_volume: int             # 流出股数
    net_volume: int                 # 净流入股数


@dataclass
class DragonTigerData:
    """龙虎榜数据"""
    symbol: str                     # 股票代码
    name: str                       # 股票名称
    date: datetime                  # 日期
    close_price: float              # 收盘价
    change_pct: float               # 涨跌幅
    turnover: float                 # 成交额（万元）
    buy_amount: float               # 买入金额（万元）
    sell_amount: float              # 卖出金额（万元）
    net_amount: float               # 净额（万元）
    buy_seats: List[Dict]           # 买入席位
    sell_seats: List[Dict]          # 卖出席位


class CapitalFlowCollector(DataCollector):
    """
    资金流向数据采集器

    使用AKShare获取A股市场资金流向数据
    """

    def __init__(self, config: Optional[CollectorConfig] = None) -> None:
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

    def get_capital_flow(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[CapitalFlowData]:
        """
        获取个股资金流向数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            资金流向数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            # 获取资金流向数据
            df = self._ak.stock_individual_fund_flow(
                stock=symbol,
                market="sh" if symbol.startswith("6") else "sz"
            )

            if df is None or df.empty:
                return []

            # 转换日期格式
            df['日期'] = pd.to_datetime(df['日期'])

            # 过滤日期范围
            df = df[(df['日期'] >= start_date) & (df['日期'] <= end_date)]

            # 转换为标准格式
            flows = []
            for _, row in df.iterrows():
                flow = CapitalFlowData(
                    symbol=symbol,
                    datetime=row['日期'],
                    flow_type=CapitalFlowType.MAIN_FORCE,
                    inflow=float(row.get('主力净流入', 0)),
                    outflow=0.0,  # AKShare返回的是净流入
                    net_flow=float(row.get('主力净流入', 0)),
                    inflow_volume=int(row.get('主力净流入', 0) * 10000),  # 估算
                    outflow_volume=0,
                    net_volume=int(row.get('主力净流入', 0) * 10000)
                )
                flows.append(flow)

            self._success_count += 1
            return flows

        except Exception as e:
            self._error_count += 1
            print(f"获取资金流向数据失败: {e}")
            return []

    def get_sector_capital_flow(
        self,
        sector_type: str = "industry",
        date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        获取板块资金流向

        Args:
            sector_type: 板块类型 (industry/concept/region)
            date: 日期，默认为今天

        Returns:
            板块资金流向列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if date is None:
                date = datetime.now()

            date_str = date.strftime("%Y%m%d")

            # 根据板块类型选择接口
            if sector_type == "industry":
                df = self._ak.stock_sector_fund_flow_rank(
                    symbol="行业资金流",
                    indicator="今日"
                )
            elif sector_type == "concept":
                df = self._ak.stock_sector_fund_flow_rank(
                    symbol="概念资金流",
                    indicator="今日"
                )
            else:
                df = self._ak.stock_sector_fund_flow_rank(
                    symbol="地域资金流",
                    indicator="今日"
                )

            if df is None or df.empty:
                return []

            # 转换为标准格式
            sectors = []
            for _, row in df.iterrows():
                sector = {
                    "name": row.get('名称', ''),
                    "change_pct": float(row.get('涨跌幅', 0)),
                    "main_force_inflow": float(row.get('主力净流入', 0)),
                    "main_force_net": float(row.get('主力净占比', 0)),
                    "large_order_inflow": float(row.get('超大单净流入', 0)),
                    "large_order_net": float(row.get('超大单净占比', 0)),
                    "big_order_inflow": float(row.get('大单净流入', 0)),
                    "big_order_net": float(row.get('大单净占比', 0)),
                    "medium_order_inflow": float(row.get('中单净流入', 0)),
                    "medium_order_net": float(row.get('中单净占比', 0)),
                    "small_order_inflow": float(row.get('小单净流入', 0)),
                    "small_order_net": float(row.get('小单净占比', 0)),
                }
                sectors.append(sector)

            self._success_count += 1
            return sectors

        except Exception as e:
            self._error_count += 1
            print(f"获取板块资金流向失败: {e}")
            return []

    def get_north_bound_flow(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """
        获取北向资金流向

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            北向资金流向列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            # 获取北向资金历史数据
            df = self._ak.stock_hsgt_hist_em(
                symbol="沪股通",
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d")
            )

            if df is None or df.empty:
                return []

            # 转换为标准格式
            flows = []
            for _, row in df.iterrows():
                flow = {
                    "date": pd.to_datetime(row['日期']),
                    "sh_net": float(row.get('沪股通', 0)),
                    "sz_net": float(row.get('深股通', 0)),
                    "total_net": float(row.get('港股通', 0)),
                    "sh_cum": float(row.get('沪股通', 0)),  # 累计
                    "sz_cum": float(row.get('深股通', 0)),
                    "total_cum": float(row.get('港股通', 0)),
                }
                flows.append(flow)

            self._success_count += 1
            return flows

        except Exception as e:
            self._error_count += 1
            print(f"获取北向资金流向失败: {e}")
            return []

    def get_realtime_capital_flow(self, symbol: str) -> Optional[Dict]:
        """
        获取实时资金流向

        Args:
            symbol: 股票代码

        Returns:
            实时资金流向数据
        """
        if not self._connected or not self._ak:
            return None

        try:
            self._requests_count += 1

            # 获取实时资金流向
            df = self._ak.stock_individual_fund_flow_rank(
                indicator="今日"
            )

            if df is None or df.empty:
                return None

            # 查找指定股票
            stock_data = df[df['代码'] == symbol]

            if stock_data.empty:
                return None

            row = stock_data.iloc[0]

            flow_data = {
                "symbol": symbol,
                "name": row.get('名称', ''),
                "latest_price": float(row.get('最新价', 0)),
                "change_pct": float(row.get('涨跌幅', 0)),
                "main_force_net": float(row.get('主力净流入', 0)),
                "main_force_net_pct": float(row.get('主力净占比', 0)),
                "large_order_net": float(row.get('超大单净流入', 0)),
                "large_order_net_pct": float(row.get('超大单净占比', 0)),
                "big_order_net": float(row.get('大单净流入', 0)),
                "big_order_net_pct": float(row.get('大单净占比', 0)),
                "medium_order_net": float(row.get('中单净流入', 0)),
                "medium_order_net_pct": float(row.get('中单净占比', 0)),
                "small_order_net": float(row.get('小单净流入', 0)),
                "small_order_net_pct": float(row.get('小单净占比', 0)),
            }

            self._success_count += 1
            return flow_data

        except Exception as e:
            self._error_count += 1
            print(f"获取实时资金流向失败: {e}")
            return None

    def get_dragon_tiger_list(
        self,
        date: Optional[datetime] = None
    ) -> List[DragonTigerData]:
        """
        获取龙虎榜数据

        Args:
            date: 日期，默认为今天

        Returns:
            龙虎榜数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if date is None:
                date = datetime.now()

            date_str = date.strftime("%Y%m%d")

            # 获取龙虎榜数据
            df = self._ak.stock_lhb_detail_daily_sina(
                start_date=date_str,
                end_date=date_str
            )

            if df is None or df.empty:
                return []

            # 转换为标准格式
            dragon_tiger_list = []
            for _, row in df.iterrows():
                dt_data = DragonTigerData(
                    symbol=row.get('代码', ''),
                    name=row.get('名称', ''),
                    date=date,
                    close_price=float(row.get('收盘价', 0)),
                    change_pct=float(row.get('涨跌幅', 0)),
                    turnover=float(row.get('成交额', 0)),
                    buy_amount=float(row.get('买方机构数', 0)),
                    sell_amount=float(row.get('卖方机构数', 0)),
                    net_amount=float(row.get('买方机构数', 0)) - float(row.get('卖方机构数', 0)),
                    buy_seats=[],
                    sell_seats=[]
                )
                dragon_tiger_list.append(dt_data)

            self._success_count += 1
            return dragon_tiger_list

        except Exception as e:
            self._error_count += 1
            print(f"获取龙虎榜数据失败: {e}")
            return []

    def get_dragon_tiger_detail(
        self,
        symbol: str,
        date: datetime
    ) -> Optional[DragonTigerData]:
        """
        获取个股龙虎榜详细数据

        Args:
            symbol: 股票代码
            date: 日期

        Returns:
            龙虎榜详细数据
        """
        if not self._connected or not self._ak:
            return None

        try:
            self._requests_count += 1

            date_str = date.strftime("%Y%m%d")

            # 获取龙虎榜详细数据
            df = self._ak.stock_lhb_detail_em(
                symbol=symbol,
                date=date_str
            )

            if df is None or df.empty:
                return None

            # 解析买卖席位
            buy_seats = []
            sell_seats = []

            for _, row in df.iterrows():
                seat_type = row.get('类型', '')
                seat_data = {
                    "name": row.get('营业部名称', ''),
                    "buy_amount": float(row.get('买入金额', 0)),
                    "sell_amount": float(row.get('卖出金额', 0)),
                    "net_amount": float(row.get('净额', 0)),
                }

                if "买入" in seat_type:
                    buy_seats.append(seat_data)
                elif "卖出" in seat_type:
                    sell_seats.append(seat_data)

            # 获取基本信息
            df_stock = self._ak.stock_lhb_detail_daily_sina(
                start_date=date_str,
                end_date=date_str
            )

            stock_info = df_stock[df_stock['代码'] == symbol]

            if stock_info.empty:
                return None

            row = stock_info.iloc[0]

            dt_data = DragonTigerData(
                symbol=symbol,
                name=row.get('名称', ''),
                date=date,
                close_price=float(row.get('收盘价', 0)),
                change_pct=float(row.get('涨跌幅', 0)),
                turnover=float(row.get('成交额', 0)),
                buy_amount=sum(s['buy_amount'] for s in buy_seats),
                sell_amount=sum(s['sell_amount'] for s in sell_seats),
                net_amount=sum(s['net_amount'] for s in buy_seats + sell_seats),
                buy_seats=buy_seats,
                sell_seats=sell_seats
            )

            self._success_count += 1
            return dt_data

        except Exception as e:
            self._error_count += 1
            print(f"获取龙虎榜详细数据失败: {e}")
            return None

    def get_bar_data(
        self,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """
        获取K线数据（资金流向采集器不支持）

        Note: 资金流向采集器专门用于采集资金流向数据
        """
        print("资金流向采集器不支持K线数据获取，请使用AKShareCollector")
        return []

    def get_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """
        获取Tick数据（资金流向采集器不支持）

        Note: 资金流向采集器专门用于采集资金流向数据
        """
        print("资金流向采集器不支持Tick数据获取")
        return []

    def get_capital_flow_summary(
        self,
        symbols: List[str],
        lookback_days: int = 5
    ) -> Dict:
        """
        获取多只股票资金流向汇总

        Args:
            symbols: 股票代码列表
            lookback_days: 回看天数

        Returns:
            资金流向汇总报告
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        summary = {
            "period": f"{start_date.date()} to {end_date.date()}",
            "stocks": {},
            "rankings": {
                "main_force_inflow": [],
                "main_force_outflow": [],
                "retail_inflow": [],
            }
        }

        for symbol in symbols:
            flows = self.get_capital_flow(symbol, start_date, end_date)

            if flows:
                total_main_force = sum(f.net_flow for f in flows)

                summary["stocks"][symbol] = {
                    "main_force_net": total_main_force,
                    "avg_daily_flow": total_main_force / len(flows),
                    "days_tracked": len(flows)
                }

                # 添加到排名
                if total_main_force > 0:
                    summary["rankings"]["main_force_inflow"].append(
                        (symbol, total_main_force)
                    )
                else:
                    summary["rankings"]["main_force_outflow"].append(
                        (symbol, abs(total_main_force))
                    )

        # 排序
        summary["rankings"]["main_force_inflow"].sort(
            key=lambda x: x[1], reverse=True
        )
        summary["rankings"]["main_force_outflow"].sort(
            key=lambda x: x[1], reverse=True
        )

        return summary
