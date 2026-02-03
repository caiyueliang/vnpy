"""
基本面因子模块

实现基于财务数据的基本面因子。
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict

from .base import Factor, register_factor


class ValuationFactor(Factor):
    """
    估值因子

    基于PE、PB等估值指标。
    """

    def __init__(self, method: str = "pe"):
        """
        初始化估值因子

        Args:
            method: 估值方法，可选"pe", "pb", "ps", "pcf"
        """
        super().__init__(
            name=f"valuation_{method}",
            description=f"{method.upper()}估值因子"
        )
        self.set_params(method=method)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算估值因子

        Args:
            data: 包含估值指标的DataFrame

        Returns:
            估值因子值（越低估值越便宜，因子值越高）
        """
        method = self.params.get('method', 'pe')

        # 获取对应的估值列
        col_map = {
            'pe': 'pe_ratio',
            'pb': 'pb_ratio',
            'ps': 'ps_ratio',
            'pcf': 'pcf_ratio'
        }

        col = col_map.get(method, 'pe_ratio')

        if col not in data.columns:
            # 如果没有估值数据，返回中性值
            return pd.Series(0, index=data.index)

        # 获取估值数据
        valuation = data[col].replace([np.inf, -np.inf], np.nan)

        # 过滤异常值
        valuation = valuation[valuation > 0]

        # 计算分位数排名（越低排名越高）
        factor = 1 - valuation.rank(pct=True)

        return factor


class GrowthFactor(Factor):
    """
    成长因子

    基于营收、利润增长率。
    """

    def __init__(self, metric: str = "revenue", period: str = "yoy"):
        """
        初始化成长因子

        Args:
            metric: 指标类型，可选"revenue", "profit", "net_profit"
            period: 计算周期，可选"yoy", "qoq"
        """
        super().__init__(
            name=f"growth_{metric}_{period}",
            description=f"{metric}_{period}成长因子"
        )
        self.set_params(metric=metric, period=period)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算成长因子

        Args:
            data: 包含财务数据的DataFrame

        Returns:
            成长因子值
        """
        metric = self.params.get('metric', 'revenue')
        period = self.params.get('period', 'yoy')

        # 构建列名
        col = f"{metric}_growth_{period}"

        if col not in data.columns:
            # 如果没有成长数据，返回中性值
            return pd.Series(0, index=data.index)

        # 获取成长数据
        growth = data[col].replace([np.inf, -np.inf], np.nan)

        # 过滤极端值
        growth = growth[growth.abs() < 10]  # 过滤超过1000%的增长率

        # 标准化
        factor = (growth - growth.mean()) / growth.std()

        return factor


class ProfitabilityFactor(Factor):
    """
    盈利能力因子

    基于ROE、ROA等盈利指标。
    """

    def __init__(self, metric: str = "roe"):
        """
        初始化盈利能力因子

        Args:
            metric: 指标类型，可选"roe", "roa", "gross_margin", "net_margin"
        """
        super().__init__(
            name=f"profitability_{metric}",
            description=f"{metric.upper()}盈利因子"
        )
        self.set_params(metric=metric)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算盈利因子

        Args:
            data: 包含财务数据的DataFrame

        Returns:
            盈利因子值
        """
        metric = self.params.get('metric', 'roe')

        # 列名映射
        col_map = {
            'roe': 'roe',
            'roa': 'roa',
            'gross_margin': 'gross_profit_margin',
            'net_margin': 'net_profit_margin'
        }

        col = col_map.get(metric, 'roe')

        if col not in data.columns:
            return pd.Series(0, index=data.index)

        # 获取盈利数据
        profitability = data[col].replace([np.inf, -np.inf], np.nan)

        # 过滤异常值
        profitability = profitability[profitability.abs() < 2]  # 过滤超过200%的指标

        # 标准化
        factor = (profitability - profitability.mean()) / profitability.std()

        return factor


class FinancialQualityFactor(Factor):
    """
    财务质量因子

    基于资产负债率、现金流等指标。
    """

    def __init__(self, method: str = "composite"):
        """
        初始化财务质量因子

        Args:
            method: 计算方法，可选"debt", "cashflow", "composite"
        """
        super().__init__(
            name=f"quality_{method}",
            description=f"{method}财务质量因子"
        )
        self.set_params(method=method)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算财务质量因子

        Args:
            data: 包含财务数据的DataFrame

        Returns:
            财务质量因子值
        """
        method = self.params.get('method', 'composite')

        if method == 'debt':
            return self._debt_quality(data)
        elif method == 'cashflow':
            return self._cashflow_quality(data)
        else:
            return self._composite_quality(data)

    def _debt_quality(self, data: pd.DataFrame) -> pd.Series:
        """基于负债率的质量因子"""
        if 'debt_ratio' not in data.columns:
            return pd.Series(0, index=data.index)

        debt_ratio = data['debt_ratio'].replace([np.inf, -np.inf], np.nan)
        debt_ratio = debt_ratio[debt_ratio > 0]

        # 负债率越低越好
        factor = 1 - debt_ratio.rank(pct=True)

        return factor

    def _cashflow_quality(self, data: pd.DataFrame) -> pd.Series:
        """基于现金流的质量因子"""
        if 'operating_cash_flow' not in data.columns:
            return pd.Series(0, index=data.index)

        ocf = data['operating_cash_flow'].replace([np.inf, -np.inf], np.nan)

        # 经营现金流为正且越大越好
        factor = pd.Series(0, index=data.index)
        factor[ocf > 0] = ocf[ocf > 0].rank(pct=True)
        factor[ocf <= 0] = -0.5  # 负现金流给予惩罚

        return factor

    def _composite_quality(self, data: pd.DataFrame) -> pd.Series:
        """综合质量因子"""
        factors = []

        # 负债率因子
        if 'debt_ratio' in data.columns:
            debt = data['debt_ratio'].replace([np.inf, -np.inf], np.nan)
            debt = debt[debt > 0]
            factors.append(1 - debt.rank(pct=True))

        # 现金流因子
        if 'operating_cash_flow' in data.columns:
            ocf = data['operating_cash_flow'].replace([np.inf, -np.inf], np.nan)
            ocf_factor = pd.Series(0, index=data.index)
            ocf_factor[ocf > 0] = ocf[ocf > 0].rank(pct=True)
            factors.append(ocf_factor)

        # 流动比率
        if 'current_ratio' in data.columns:
            current = data['current_ratio'].replace([np.inf, -np.inf], np.nan)
            factors.append(current.rank(pct=True))

        if not factors:
            return pd.Series(0, index=data.index)

        # 等权合成
        composite = pd.concat(factors, axis=1).mean(axis=1)

        return composite


class EPFactor(Factor):
    """
    盈利收益率因子 (Earnings-to-Price)

    EP = 盈利 / 市值，是PE的倒数。
    """

    def __init__(self, method: str = "ttm"):
        """
        初始化EP因子

        Args:
            method: 计算方法，可选"ttm", "forecast"
        """
        super().__init__(
            name=f"ep_{method}",
            description=f"{method}盈利收益率因子"
        )
        self.set_params(method=method)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算EP因子

        Args:
            data: 包含盈利和市值数据的DataFrame

        Returns:
            EP因子值
        """
        if 'ep_ratio' in data.columns:
            ep = data['ep_ratio'].replace([np.inf, -np.inf], np.nan)
        elif 'pe_ratio' in data.columns:
            # 从PE计算EP
            pe = data['pe_ratio'].replace([np.inf, -np.inf], np.nan)
            pe = pe[pe > 0]
            ep = 1 / pe
        else:
            return pd.Series(0, index=data.index)

        # 过滤异常值
        ep = ep[ep.abs() < 1]  # 过滤超过100%的收益率

        # 标准化
        factor = (ep - ep.mean()) / ep.std()

        return factor


class BPFactor(Factor):
    """
    账面市值比因子 (Book-to-Price)

    BP = 账面价值 / 市值，是PB的倒数。
    """

    def __init__(self):
        super().__init__(
            name="bp",
            description="账面市值比因子"
        )

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算BP因子

        Args:
            data: 包含PB数据的DataFrame

        Returns:
            BP因子值
        """
        if 'bp_ratio' in data.columns:
            bp = data['bp_ratio'].replace([np.inf, -np.inf], np.nan)
        elif 'pb_ratio' in data.columns:
            # 从PB计算BP
            pb = data['pb_ratio'].replace([np.inf, -np.inf], np.nan)
            pb = pb[pb > 0]
            bp = 1 / pb
        else:
            return pd.Series(0, index=data.index)

        # 过滤异常值
        bp = bp[bp.abs() < 10]

        # 标准化
        factor = (bp - bp.mean()) / bp.std()

        return factor


class SPFactor(Factor):
    """
    营收市值比因子 (Sales-to-Price)

    SP = 营收 / 市值，是PS的倒数。
    """

    def __init__(self):
        super().__init__(
            name="sp",
            description="营收市值比因子"
        )

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算SP因子

        Args:
            data: 包含PS数据的DataFrame

        Returns:
            SP因子值
        """
        if 'sp_ratio' in data.columns:
            sp = data['sp_ratio'].replace([np.inf, -np.inf], np.nan)
        elif 'ps_ratio' in data.columns:
            # 从PS计算SP
            ps = data['ps_ratio'].replace([np.inf, -np.inf], np.nan)
            ps = ps[ps > 0]
            sp = 1 / ps
        else:
            return pd.Series(0, index=data.index)

        # 过滤异常值
        sp = sp[sp.abs() < 10]

        # 标准化
        factor = (sp - sp.mean()) / sp.std()

        return factor


class DividendFactor(Factor):
    """
    股息率因子

    基于分红收益率。
    """

    def __init__(self, method: str = "ttm"):
        """
        初始化股息率因子

        Args:
            method: 计算方法，可选"ttm", "avg_3y"
        """
        super().__init__(
            name=f"dividend_{method}",
            description=f"{method}股息率因子"
        )
        self.set_params(method=method)

    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算股息率因子

        Args:
            data: 包含股息率数据的DataFrame

        Returns:
            股息率因子值
        """
        method = self.params.get('method', 'ttm')

        col = f"dividend_yield_{method}"

        if col not in data.columns and 'dividend_yield' in data.columns:
            col = 'dividend_yield'

        if col not in data.columns:
            return pd.Series(0, index=data.index)

        # 获取股息率数据
        dividend = data[col].replace([np.inf, -np.inf], np.nan)

        # 过滤异常值
        dividend = dividend[dividend < 0.5]  # 过滤超过50%的股息率

        # 标准化
        factor = (dividend - dividend.mean()) / dividend.std()

        return factor


# 注册所有基本面因子
register_factor(ValuationFactor("pe"), "fundamental")
register_factor(ValuationFactor("pb"), "fundamental")
register_factor(ValuationFactor("ps"), "fundamental")

register_factor(GrowthFactor("revenue", "yoy"), "fundamental")
register_factor(GrowthFactor("net_profit", "yoy"), "fundamental")
register_factor(GrowthFactor("revenue", "qoq"), "fundamental")

register_factor(ProfitabilityFactor("roe"), "fundamental")
register_factor(ProfitabilityFactor("roa"), "fundamental")
register_factor(ProfitabilityFactor("gross_margin"), "fundamental")

register_factor(FinancialQualityFactor("composite"), "fundamental")
register_factor(FinancialQualityFactor("debt"), "fundamental")

register_factor(EPFactor(), "fundamental")
register_factor(BPFactor(), "fundamental")
register_factor(SPFactor(), "fundamental")

register_factor(DividendFactor("ttm"), "fundamental")
