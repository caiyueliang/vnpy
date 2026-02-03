"""
另类数据采集器

采集A股另类数据，包括：
- 舆情数据（新闻、公告、社交媒体）
- 行业景气度数据
- 宏观指标数据
"""

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from .base import DataCollector, CollectorConfig, DataSource


class AlternativeCollector(DataCollector):
    """
    另类数据采集器

    使用AKShare获取A股另类数据，包括舆情、行业景气度、宏观指标等。
    这些数据可用于构建情绪因子、行业轮动策略、宏观择时策略等。
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
        """获取K线数据（另类数据采集器不支持）"""
        return []

    def get_tick_data(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime
    ) -> list[dict]:
        """获取Tick数据（另类数据采集器不支持）"""
        return []

    # ========== 舆情数据 ==========

    def get_stock_news(
        self,
        symbol: str,
        days: int = 7
    ) -> list[dict]:
        """
        获取个股新闻

        Args:
            symbol: 股票代码
            days: 获取最近几天的数据

        Returns:
            新闻数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_news_em(symbol=symbol)

            if df is None or df.empty:
                return []

            # 过滤日期
            cutoff_date = datetime.now() - timedelta(days=days)

            news_list = []
            for _, row in df.iterrows():
                news_time = pd.to_datetime(row.get("发布时间", ""))
                if news_time < cutoff_date:
                    continue

                news = {
                    "symbol": symbol,
                    "title": row.get("标题", ""),
                    "content": row.get("内容", ""),
                    "publish_time": news_time,
                    "source": row.get("来源", ""),
                    "url": row.get("链接", ""),
                }
                news_list.append(news)

            self._success_count += 1
            return news_list

        except Exception as e:
            self._error_count += 1
            print(f"获取个股新闻失败: {e}")
            return []

    def get_stock_announcements(
        self,
        symbol: str,
        category: str | None = None
    ) -> list[dict]:
        """
        获取个股公告

        Args:
            symbol: 股票代码
            category: 公告类别，None则获取全部

        Returns:
            公告数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_notice_report(
                symbol=symbol,
                date=datetime.now().strftime("%Y%m%d")
            )

            if df is None or df.empty:
                return []

            announcements = []
            for _, row in df.iterrows():
                announcement = {
                    "symbol": symbol,
                    "title": row.get("公告标题", ""),
                    "category": row.get("公告类型", ""),
                    "publish_date": row.get("公告日期", ""),
                    "url": row.get("公告链接", ""),
                }

                if category and announcement["category"] != category:
                    continue

                announcements.append(announcement)

            self._success_count += 1
            return announcements

        except Exception as e:
            self._error_count += 1
            print(f"获取个股公告失败: {e}")
            return []

    def get_investor_sentiment(self) -> dict:
        """
        获取投资者情绪指标

        Returns:
            情绪指标数据
        """
        if not self._connected or not self._ak:
            return {}

        try:
            self._requests_count += 1

            # 获取新增投资者数量（市场情绪指标）
            df = self._ak.stock_new_investor()

            if df is None or df.empty:
                return {}

            latest = df.iloc[0]

            sentiment = {
                "date": latest.get("日期", ""),
                "new_investors": self._parse_amount(latest.get("新增投资者数量", 0)),
                "total_investors": self._parse_amount(latest.get("期末投资者数量", 0)),
                "growth_rate": self._parse_amount(latest.get("环比", 0)),
            }

            self._success_count += 1
            return sentiment

        except Exception as e:
            self._error_count += 1
            print(f"获取投资者情绪失败: {e}")
            return {}

    def get_stock_hot_rank(self) -> list[dict]:
        """
        获取个股热度排名（东方财富）

        Returns:
            热度排名列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_hot_rank_em()

            if df is None or df.empty:
                return []

            ranks = []
            for _, row in df.iterrows():
                rank = {
                    "rank": int(row.get("排名", 0)),
                    "symbol": row.get("代码", ""),
                    "name": row.get("名称", ""),
                    "hot_value": self._parse_amount(row.get("热度", 0)),
                    "change": row.get("涨跌幅", ""),
                }
                ranks.append(rank)

            self._success_count += 1
            return ranks

        except Exception as e:
            self._error_count += 1
            print(f"获取热度排名失败: {e}")
            return []

    # ========== 行业景气度数据 ==========

    def get_industry_list(self) -> list[dict]:
        """
        获取行业列表

        Returns:
            行业列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_board_industry_name_em()

            if df is None or df.empty:
                return []

            industries = []
            for _, row in df.iterrows():
                industry = {
                    "code": row.get("板块代码", ""),
                    "name": row.get("板块名称", ""),
                    "change_pct": self._parse_amount(row.get("涨跌幅", 0)),
                    "turnover": self._parse_amount(row.get("换手率", 0)),
                    "amount": self._parse_amount(row.get("成交额", 0)),
                    "up_count": int(row.get("上涨家数", 0)),
                    "down_count": int(row.get("下跌家数", 0)),
                }
                industries.append(industry)

            self._success_count += 1
            return industries

        except Exception as e:
            self._error_count += 1
            print(f"获取行业列表失败: {e}")
            return []

    def get_industry_stocks(self, industry_code: str) -> list[dict]:
        """
        获取行业成分股

        Args:
            industry_code: 行业代码

        Returns:
            成分股列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_board_industry_cons_em(symbol=industry_code)

            if df is None or df.empty:
                return []

            stocks = []
            for _, row in df.iterrows():
                stock = {
                    "symbol": row.get("代码", ""),
                    "name": row.get("名称", ""),
                    "price": self._parse_amount(row.get("最新价", 0)),
                    "change_pct": self._parse_amount(row.get("涨跌幅", 0)),
                    "turnover": self._parse_amount(row.get("换手率", 0)),
                    "amount": self._parse_amount(row.get("成交额", 0)),
                    "market_cap": self._parse_amount(row.get("总市值", 0)),
                }
                stocks.append(stock)

            self._success_count += 1
            return stocks

        except Exception as e:
            self._error_count += 1
            print(f"获取行业成分股失败: {e}")
            return []

    def get_industry_boom_index(self, industry: str) -> list[dict]:
        """
        获取行业景气度指数

        Args:
            industry: 行业名称

        Returns:
            景气度指数列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            # 获取行业指数历史数据作为景气度参考
            df = self._ak.index_zh_a_hist(
                symbol=self._get_industry_index_code(industry),
                period="daily",
                start_date=(datetime.now() - timedelta(days=365)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d")
            )

            if df is None or df.empty:
                return []

            # 计算景气度指标
            indices = []
            for i in range(20, len(df)):
                window = df.iloc[i-20:i]

                # 计算趋势强度
                returns = (window["收盘"].iloc[-1] - window["收盘"].iloc[0]) / window["收盘"].iloc[0]
                volatility = window["收盘"].std() / window["收盘"].mean()

                # 计算成交量趋势
                volume_trend = window["成交量"].iloc[-5:].mean() / window["成交量"].iloc[:5].mean()

                # 综合景气度指数（简化版）
                boom_index = (returns * 0.5 + (1 - volatility) * 0.3 + volume_trend * 0.2) * 100

                indices.append({
                    "date": df.iloc[i]["日期"],
                    "industry": industry,
                    "boom_index": boom_index,
                    "returns_20d": returns,
                    "volatility": volatility,
                    "volume_trend": volume_trend,
                })

            self._success_count += 1
            return indices

        except Exception as e:
            self._error_count += 1
            print(f"获取行业景气度失败: {e}")
            return []

    def get_concept_list(self) -> list[dict]:
        """
        获取概念板块列表

        Returns:
            概念板块列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.stock_board_concept_name_em()

            if df is None or df.empty:
                return []

            concepts = []
            for _, row in df.iterrows():
                concept = {
                    "code": row.get("板块代码", ""),
                    "name": row.get("板块名称", ""),
                    "change_pct": self._parse_amount(row.get("涨跌幅", 0)),
                    "turnover": self._parse_amount(row.get("换手率", 0)),
                    "amount": self._parse_amount(row.get("成交额", 0)),
                    "up_count": int(row.get("上涨家数", 0)),
                    "down_count": int(row.get("下跌家数", 0)),
                }
                concepts.append(concept)

            self._success_count += 1
            return concepts

        except Exception as e:
            self._error_count += 1
            print(f"获取概念板块失败: {e}")
            return []

    # ========== 宏观指标数据 ==========

    def get_macro_economic_indicators(self) -> dict:
        """
        获取宏观经济指标

        Returns:
            宏观经济指标数据
        """
        if not self._connected or not self._ak:
            return {}

        try:
            self._requests_count += 1

            indicators = {}

            # GDP数据
            try:
                gdp_df = self._ak.macro_china_gdp()
                if gdp_df is not None and not gdp_df.empty:
                    latest = gdp_df.iloc[0]
                    indicators["gdp"] = {
                        "quarter": latest.get("季度", ""),
                        "gdp_value": self._parse_amount(latest.get("国内生产总值-绝对值", 0)),
                        "gdp_yoy": self._parse_amount(latest.get("国内生产总值-同比增长", 0)),
                    }
            except Exception:
                pass

            # CPI数据
            try:
                cpi_df = self._ak.macro_china_cpi()
                if cpi_df is not None and not cpi_df.empty:
                    latest = cpi_df.iloc[0]
                    indicators["cpi"] = {
                        "month": latest.get("月份", ""),
                        "cpi_yoy": self._parse_amount(latest.get("全国-当月", 0)),
                        "cpi_mom": self._parse_amount(latest.get("全国-环比", 0)),
                    }
            except Exception:
                pass

            # PMI数据
            try:
                pmi_df = self._ak.macro_china_pmi()
                if pmi_df is not None and not pmi_df.empty:
                    latest = pmi_df.iloc[0]
                    indicators["pmi"] = {
                        "month": latest.get("月份", ""),
                        "manufacturing_pmi": self._parse_amount(latest.get("制造业-指数", 0)),
                        "non_manufacturing_pmi": self._parse_amount(latest.get("非制造业-指数", 0)),
                    }
            except Exception:
                pass

            # 货币供应量
            try:
                money_df = self._ak.macro_china_money_supply()
                if money_df is not None and not money_df.empty:
                    latest = money_df.iloc[0]
                    indicators["money_supply"] = {
                        "month": latest.get("月份", ""),
                        "m2_yoy": self._parse_amount(latest.get("M2-同比增长", 0)),
                        "m1_yoy": self._parse_amount(latest.get("M1-同比增长", 0)),
                        "m0_yoy": self._parse_amount(latest.get("M0-同比增长", 0)),
                    }
            except Exception:
                pass

            self._success_count += 1
            return indicators

        except Exception as e:
            self._error_count += 1
            print(f"获取宏观指标失败: {e}")
            return {}

    def get_interest_rates(self) -> list[dict]:
        """
        获取利率数据

        Returns:
            利率数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.macro_china_lpr()

            if df is None or df.empty:
                return []

            rates = []
            for _, row in df.iterrows():
                rate = {
                    "date": row.get("日期", ""),
                    "lpr_1y": self._parse_amount(row.get("LPR1Y", 0)),
                    "lpr_5y": self._parse_amount(row.get("LPR5Y", 0)),
                }
                rates.append(rate)

            self._success_count += 1
            return rates

        except Exception as e:
            self._error_count += 1
            print(f"获取利率数据失败: {e}")
            return []

    def get_exchange_rate(self, currency_pair: str = "USD/CNY") -> list[dict]:
        """
        获取汇率数据

        Args:
            currency_pair: 货币对

        Returns:
            汇率数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            if currency_pair == "USD/CNY":
                df = self._ak.currency_boc_safe()
            else:
                return []

            if df is None or df.empty:
                return []

            rates = []
            for _, row in df.head(30).iterrows():
                rate = {
                    "date": row.get("日期", ""),
                    "currency_pair": currency_pair,
                    "spot_rate": self._parse_amount(row.get("现汇买入价", 0)),
                    "cash_rate": self._parse_amount(row.get("现钞买入价", 0)),
                    "selling_rate": self._parse_amount(row.get("现汇卖出价", 0)),
                }
                rates.append(rate)

            self._success_count += 1
            return rates

        except Exception as e:
            self._error_count += 1
            print(f"获取汇率数据失败: {e}")
            return []

    def get_treasury_yield(self) -> list[dict]:
        """
        获取国债收益率

        Returns:
            国债收益率数据列表
        """
        if not self._connected or not self._ak:
            return []

        try:
            self._requests_count += 1

            df = self._ak.bond_zh_us_rate()

            if df is None or df.empty:
                return []

            yields = []
            for _, row in df.head(30).iterrows():
                yield_data = {
                    "date": row.get("日期", ""),
                    "china_2y": self._parse_amount(row.get("中国国债收益率2年", 0)),
                    "china_5y": self._parse_amount(row.get("中国国债收益率5年", 0)),
                    "china_10y": self._parse_amount(row.get("中国国债收益率10年", 0)),
                    "china_30y": self._parse_amount(row.get("中国国债收益率30年", 0)),
                    "us_2y": self._parse_amount(row.get("美国国债收益率2年", 0)),
                    "us_5y": self._parse_amount(row.get("美国国债收益率5年", 0)),
                    "us_10y": self._parse_amount(row.get("美国国债收益率10年", 0)),
                    "us_30y": self._parse_amount(row.get("美国国债收益率30年", 0)),
                }
                yields.append(yield_data)

            self._success_count += 1
            return yields

        except Exception as e:
            self._error_count += 1
            print(f"获取国债收益率失败: {e}")
            return []

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
            value = value.strip()
            value = value.replace(",", "")
            value = value.replace("%", "")
            value = value.replace("亿", "e8")
            value = value.replace("万", "e4")

            try:
                return float(value)
            except ValueError:
                return 0.0

        return 0.0

    def _get_industry_index_code(self, industry_name: str) -> str:
        """
        获取行业指数代码（简化映射）

        Args:
            industry_name: 行业名称

        Returns:
            指数代码
        """
        # 常见行业指数映射
        mapping = {
            "银行": "BK0475",
            "证券": "BK0473",
            "保险": "BK0474",
            "房地产": "BK0451",
            "医药": "BK0465",
            "半导体": "BK0891",
            "新能源": "BK0493",
            "汽车": "BK0481",
            "白酒": "BK0896",
            "军工": "BK0490",
            "电子": "BK0459",
            "计算机": "BK0474",
            "传媒": "BK0486",
            "通信": "BK0479",
            "电力": "BK0428",
            "钢铁": "BK0479",
            "煤炭": "BK0437",
            "石油": "BK0464",
            "化工": "BK0467",
            "有色": "BK0478",
            "建材": "BK0476",
            "建筑": "BK0425",
            "机械": "BK0447",
            "家电": "BK0456",
            "食品饮料": "BK0438",
            "纺织服装": "BK0436",
            "轻工": "BK0444",
            "农林牧渔": "BK0433",
            "交通运输": "BK0422",
            "商贸零售": "BK0482",
        }
        return mapping.get(industry_name, "")
