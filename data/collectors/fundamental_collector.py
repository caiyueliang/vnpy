"""
基本面数据采集器

采集A股基本面数据，包括：
- 财务报表（利润表、资产负债表、现金流量表）
- 业绩预告
- 股东持仓
- 龙虎榜数据
"""

from datetime import datetime
from typing import Any

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class FundamentalCollector(DataCollector):
    """
    基本面数据采集器

    使用AKShare获取A股基本面数据，包括财务报表、业绩预告、
    股东持仓、龙虎榜等数据。
    """

    def __init__(self, config: CollectorConfig | None = None) -> None:
        """Constructor"""
        if config is None:
            config = CollectorConfig(source=DataSource.AKSHARE)
        super().__init__(config)

        self._ak = None

    def connect(self) -> bool:
        """
        连接数据源

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
            print(f"连接失败: {e}")
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
        """获取K线数据（基本面采集器不支持）"""
        return []

    def get_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """获取Tick数据（基本面采集器不支持）"""
        return []

    # ========== 财务报表 ==========

    def get_income_statement(
        self,
        symbol: str,
        period: str = "annual"
    ) -> list[dict]:
        """
        获取利润表

        Args:
            symbol: 股票代码
            period: 报表类型 (annual-年报, quarterly-季报)

        Returns:
            利润表数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if period == "annual":
                df = self._ak.stock_financial_report_sina(
                    stock=symbol,
                    symbol="利润表"
                )
            else:
                # 获取季报数据
                df = self._ak.stock_financial_report_sina(
                    stock=symbol,
                    symbol="利润表"
                )

            if df is None or df.empty:
                return []

            statements = []
            for _, row in df.iterrows():
                statement = {
                    "symbol": symbol,
                    "report_date": row.get("报告日", ""),
                    "total_revenue": self._parse_amount(row.get("营业总收入", 0)),
                    "revenue": self._parse_amount(row.get("营业收入", 0)),
                    "total_cost": self._parse_amount(row.get("营业总成本", 0)),
                    "operating_cost": self._parse_amount(row.get("营业成本", 0)),
                    "gross_profit": self._parse_amount(row.get("营业利润", 0)),
                    "total_profit": self._parse_amount(row.get("利润总额", 0)),
                    "net_profit": self._parse_amount(row.get("净利润", 0)),
                    "net_profit_parent": self._parse_amount(row.get("归属于母公司股东的净利润", 0)),
                    "eps": self._parse_amount(row.get("基本每股收益", 0)),
                    "diluted_eps": self._parse_amount(row.get("稀释每股收益", 0)),
                }
                statements.append(statement)

            self._success_count += 1
            return statements

        except Exception as e:
            self._error_count += 1
            print(f"获取利润表失败: {e}")
            return []

    def get_balance_sheet(
        self,
        symbol: str,
        period: str = "annual"
    ) -> list[dict]:
        """
        获取资产负债表

        Args:
            symbol: 股票代码
            period: 报表类型

        Returns:
            资产负债表数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_financial_report_sina(
                stock=symbol,
                symbol="资产负债表"
            )

            if df is None or df.empty:
                return []

            statements = []
            for _, row in df.iterrows():
                statement = {
                    "symbol": symbol,
                    "report_date": row.get("报告日", ""),
                    "total_assets": self._parse_amount(row.get("资产总计", 0)),
                    "current_assets": self._parse_amount(row.get("流动资产合计", 0)),
                    "non_current_assets": self._parse_amount(row.get("非流动资产合计", 0)),
                    "total_liabilities": self._parse_amount(row.get("负债合计", 0)),
                    "current_liabilities": self._parse_amount(row.get("流动负债合计", 0)),
                    "non_current_liabilities": self._parse_amount(row.get("非流动负债合计", 0)),
                    "equity": self._parse_amount(row.get("所有者权益合计", 0)),
                    "equity_parent": self._parse_amount(row.get("归属于母公司股东权益合计", 0)),
                    "share_capital": self._parse_amount(row.get("实收资本", 0)),
                    "capital_reserve": self._parse_amount(row.get("资本公积", 0)),
                    "retained_earnings": self._parse_amount(row.get("未分配利润", 0)),
                }
                statements.append(statement)

            self._success_count += 1
            return statements

        except Exception as e:
            self._error_count += 1
            print(f"获取资产负债表失败: {e}")
            return []

    def get_cash_flow(
        self,
        symbol: str,
        period: str = "annual"
    ) -> list[dict]:
        """
        获取现金流量表

        Args:
            symbol: 股票代码
            period: 报表类型

        Returns:
            现金流量表数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_financial_report_sina(
                stock=symbol,
                symbol="现金流量表"
            )

            if df is None or df.empty:
                return []

            statements = []
            for _, row in df.iterrows():
                statement = {
                    "symbol": symbol,
                    "report_date": row.get("报告日", ""),
                    "net_cash_flow": self._parse_amount(row.get("现金及现金等价物净增加额", 0)),
                    "operating_cash_flow": self._parse_amount(row.get("经营活动产生的现金流量净额", 0)),
                    "investing_cash_flow": self._parse_amount(row.get("投资活动产生的现金流量净额", 0)),
                    "financing_cash_flow": self._parse_amount(row.get("筹资活动产生的现金流量净额", 0)),
                    "cash_from_sales": self._parse_amount(row.get("销售商品、提供劳务收到的现金", 0)),
                    "cash_to_suppliers": self._parse_amount(row.get("购买商品、接受劳务支付的现金", 0)),
                    "cash_to_employees": self._parse_amount(row.get("支付给职工以及为职工支付的现金", 0)),
                    "cash_paid_for_taxes": self._parse_amount(row.get("支付的各项税费", 0)),
                }
                statements.append(statement)

            self._success_count += 1
            return statements

        except Exception as e:
            self._error_count += 1
            print(f"获取现金流量表失败: {e}")
            return []

    def get_financial_indicators(
        self,
        symbol: str
    ) -> list[dict]:
        """
        获取财务指标

        Args:
            symbol: 股票代码

        Returns:
            财务指标数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_financial_analysis_indicator(
                symbol=symbol
            )

            if df is None or df.empty:
                return []

            indicators = []
            for _, row in df.iterrows():
                indicator = {
                    "symbol": symbol,
                    "report_date": row.get("报告日", ""),
                    "eps": self._parse_amount(row.get("每股收益", 0)),
                    "eps_diluted": self._parse_amount(row.get("每股收益(扣除)", 0)),
                    "bps": self._parse_amount(row.get("每股净资产", 0)),
                    "roe": self._parse_amount(row.get("净资产收益率", 0)),
                    "roa": self._parse_amount(row.get("总资产收益率", 0)),
                    "gross_margin": self._parse_amount(row.get("毛利率", 0)),
                    "net_margin": self._parse_amount(row.get("净利率", 0)),
                    "debt_ratio": self._parse_amount(row.get("资产负债率", 0)),
                    "current_ratio": self._parse_amount(row.get("流动比率", 0)),
                    "quick_ratio": self._parse_amount(row.get("速动比率", 0)),
                    "inventory_turnover": self._parse_amount(row.get("存货周转率", 0)),
                    "receivable_turnover": self._parse_amount(row.get("应收账款周转率", 0)),
                    "total_asset_turnover": self._parse_amount(row.get("总资产周转率", 0)),
                }
                indicators.append(indicator)

            self._success_count += 1
            return indicators

        except Exception as e:
            self._error_count += 1
            print(f"获取财务指标失败: {e}")
            return []

    # ========== 业绩预告 ==========

    def get_performance_forecast(
        self,
        symbol: str | None = None
    ) -> list[dict]:
        """
        获取业绩预告

        Args:
            symbol: 股票代码，None则获取全部

        Returns:
            业绩预告数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if symbol:
                # 获取单个股票的业绩预告
                df = self._ak.stock_yjyg(symbol=symbol)
            else:
                # 获取全部业绩预告
                df = self._ak.stock_yjyg_em()

            if df is None or df.empty:
                return []

            forecasts = []
            for _, row in df.iterrows():
                forecast = {
                    "symbol": row.get("股票代码", ""),
                    "name": row.get("股票简称", ""),
                    "forecast_date": row.get("首次公告日", ""),
                    "report_period": row.get("报告期", ""),
                    "forecast_type": row.get("预告类型", ""),  # 预增、预减等
                    "profit_change_min": self._parse_amount(row.get("净利润变动幅度下限", 0)),
                    "profit_change_max": self._parse_amount(row.get("净利润变动幅度上限", 0)),
                    "profit_min": self._parse_amount(row.get("预计净利润下限", 0)),
                    "profit_max": self._parse_amount(row.get("预计净利润上限", 0)),
                    "reason": row.get("业绩变动原因", ""),
                }
                forecasts.append(forecast)

            self._success_count += 1
            return forecasts

        except Exception as e:
            self._error_count += 1
            print(f"获取业绩预告失败: {e}")
            return []

    def get_performance_express(
        self,
        symbol: str | None = None
    ) -> list[dict]:
        """
        获取业绩快报

        Args:
            symbol: 股票代码，None则获取全部

        Returns:
            业绩快报数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_yjkb_em()

            if df is None or df.empty:
                return []

            expresses = []
            for _, row in df.iterrows():
                express = {
                    "symbol": row.get("股票代码", ""),
                    "name": row.get("股票简称", ""),
                    "report_date": row.get("公告日期", ""),
                    "report_period": row.get("报告期", ""),
                    "total_revenue": self._parse_amount(row.get("营业收入", 0)),
                    "revenue_growth": self._parse_amount(row.get("营业收入同比增长", 0)),
                    "operating_profit": self._parse_amount(row.get("营业利润", 0)),
                    "total_profit": self._parse_amount(row.get("利润总额", 0)),
                    "net_profit": self._parse_amount(row.get("净利润", 0)),
                    "net_profit_growth": self._parse_amount(row.get("净利润同比增长", 0)),
                    "eps": self._parse_amount(row.get("基本每股收益", 0)),
                    "bps": self._parse_amount(row.get("每股净资产", 0)),
                    "roe": self._parse_amount(row.get("净资产收益率", 0)),
                }
                expresses.append(express)

            self._success_count += 1
            return expresses

        except Exception as e:
            self._error_count += 1
            print(f"获取业绩快报失败: {e}")
            return []

    # ========== 股东持仓 ==========

    def get_top10_holders(
        self,
        symbol: str,
        period: str | None = None
    ) -> list[dict]:
        """
        获取前十大股东

        Args:
            symbol: 股票代码
            period: 报告期，None则获取最新

        Returns:
            股东持仓数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_top10_stock_holder(
                stock=symbol,
                year=datetime.now().year if period is None else int(period[:4]),
                quarter=4 if period is None else int(period[5:6])
            )

            if df is None or df.empty:
                return []

            holders = []
            for _, row in df.iterrows():
                holder = {
                    "symbol": symbol,
                    "report_period": row.get("报告期", ""),
                    "rank": int(row.get("排名", 0)),
                    "holder_name": row.get("股东名称", ""),
                    "share_type": row.get("股份类型", ""),
                    "holdings": self._parse_amount(row.get("持股数量", 0)),
                    "holdings_pct": self._parse_amount(row.get("持股比例", 0)),
                    "change": self._parse_amount(row.get("变动数量", 0)),
                    "change_pct": self._parse_amount(row.get("变动比例", 0)),
                }
                holders.append(holder)

            self._success_count += 1
            return holders

        except Exception as e:
            self._error_count += 1
            print(f"获取前十大股东失败: {e}")
            return []

    def get_fund_holdings(
        self,
        symbol: str | None = None
    ) -> list[dict]:
        """
        获取基金持仓

        Args:
            symbol: 股票代码，None则获取全部基金重仓股

        Returns:
            基金持仓数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if symbol:
                # 获取单个股票的基金持仓
                df = self._ak.stock_gdfx_free_top_10_em(symbol=symbol)
            else:
                # 获取基金重仓股
                df = self._ak.stock_zcfz_em()

            if df is None or df.empty:
                return []

            holdings = []
            for _, row in df.iterrows():
                holding = {
                    "symbol": row.get("股票代码", ""),
                    "name": row.get("股票简称", ""),
                    "fund_name": row.get("基金名称", ""),
                    "fund_code": row.get("基金代码", ""),
                    "holdings": self._parse_amount(row.get("持股数量", 0)),
                    "holdings_value": self._parse_amount(row.get("持股市值", 0)),
                    "holdings_pct": self._parse_amount(row.get("持股比例", 0)),
                    "net_value_pct": self._parse_amount(row.get("占净值比例", 0)),
                    "quarter": row.get("季度", ""),
                }
                holdings.append(holding)

            self._success_count += 1
            return holdings

        except Exception as e:
            self._error_count += 1
            print(f"获取基金持仓失败: {e}")
            return []

    # ========== 龙虎榜 ==========

    def get_dragon_tiger_list(
        self,
        trade_date: str | None = None
    ) -> list[dict]:
        """
        获取龙虎榜列表

        Args:
            trade_date: 交易日期 (YYYYMMDD)，None则获取最新

        Returns:
            龙虎榜数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if trade_date is None:
                trade_date = datetime.now().strftime("%Y%m%d")

            df = self._ak.stock_lhb_detail_daily_sina(start_date=trade_date, end_date=trade_date)

            if df is None or df.empty:
                return []

            dragons = []
            for _, row in df.iterrows():
                dragon = {
                    "symbol": row.get("代码", ""),
                    "name": row.get("名称", ""),
                    "trade_date": trade_date,
                    "close_price": self._parse_amount(row.get("收盘价", 0)),
                    "change_pct": self._parse_amount(row.get("涨跌幅", 0)),
                    "turnover": self._parse_amount(row.get("成交额", 0)),
                    "buy_amount": self._parse_amount(row.get("买入额", 0)),
                    "sell_amount": self._parse_amount(row.get("卖出额", 0)),
                    "net_amount": self._parse_amount(row.get("净额", 0)),
                    "reason": row.get("上榜原因", ""),
                }
                dragons.append(dragon)

            self._success_count += 1
            return dragons

        except Exception as e:
            self._error_count += 1
            print(f"获取龙虎榜失败: {e}")
            return []

    def get_dragon_tiger_detail(
        self,
        symbol: str,
        trade_date: str
    ) -> dict:
        """
        获取龙虎榜详情

        Args:
            symbol: 股票代码
            trade_date: 交易日期 (YYYYMMDD)

        Returns:
            龙虎榜详情数据
        """
        if not self._connected or not self._ak:
            return {}

        try:
            self._requests_count += 1

            # 获取买入营业部
            buy_df = self._ak.stock_lhb_stock_detail_sina(
                symbol=symbol,
                date=trade_date,
                type="buy"
            )

            # 获取卖出营业部
            sell_df = self._ak.stock_lhb_stock_detail_sina(
                symbol=symbol,
                date=trade_date,
                type="sell"
            )

            buy_depts = []
            if buy_df is not None and not buy_df.empty:
                for _, row in buy_df.iterrows():
                    buy_depts.append({
                        "dept_name": row.get("营业部名称", ""),
                        "amount": self._parse_amount(row.get("买入金额", 0)),
                        "pct": self._parse_amount(row.get("买入占比", 0)),
                    })

            sell_depts = []
            if sell_df is not None and not sell_df.empty:
                for _, row in sell_df.iterrows():
                    sell_depts.append({
                        "dept_name": row.get("营业部名称", ""),
                        "amount": self._parse_amount(row.get("卖出金额", 0)),
                        "pct": self._parse_amount(row.get("卖出占比", 0)),
                    })

            self._success_count += 1

            return {
                "symbol": symbol,
                "trade_date": trade_date,
                "buy_departments": buy_depts,
                "sell_departments": sell_depts,
            }

        except Exception as e:
            self._error_count += 1
            print(f"获取龙虎榜详情失败: {e}")
            return {}

    # ========== 工具方法 ==========

    def _parse_amount(self, value: Any) -> float:
        """
        解析金额

        Args:
            value: 原始值

        Returns:
            解析后的数值
        """
        if pd.isna(value):
            return 0.0

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            # 处理带单位的字符串
            value = value.strip()
            value = value.replace(",", "")
            value = value.replace("亿", "e8")
            value = value.replace("万", "e4")

            try:
                return float(value)
            except ValueError:
                return 0.0

        return 0.0
