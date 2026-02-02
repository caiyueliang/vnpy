"""
数据清洗模块

提供数据质量检查和清洗功能
"""

from datetime import datetime
from typing import Any
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import numpy as np


class DataQualityIssue(Enum):
    """数据质量问题类型"""
    MISSING_VALUE = "missing_value"         # 缺失值
    OUTLIER = "outlier"                     # 异常值
    DUPLICATE = "duplicate"                 # 重复数据
    GAP = "gap"                             # 数据缺失
    NEGATIVE_PRICE = "negative_price"       # 负价格
    ZERO_VOLUME = "zero_volume"             # 零成交量
    PRICE_JUMP = "price_jump"               # 价格跳变
    TIMESTAMP_ERROR = "timestamp_error"     # 时间戳错误


@dataclass
class QualityReport:
    """数据质量报告"""
    total_records: int = 0
    issues_found: int = 0
    issues_fixed: int = 0
    missing_rate: float = 0.0
    outlier_rate: float = 0.0
    duplicate_rate: float = 0.0
    issues: list[dict] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []


class DataCleaner:
    """
    数据清洗器

    提供数据质量检查和清洗功能：
    1. 缺失值检测与填充
    2. 异常值检测与处理
    3. 重复数据检测与删除
    4. 数据连续性检查
    """

    def __init__(self) -> None:
        """Constructor"""
        self.issues: list[dict] = []

    def clean_bar_data(self, bars: list[dict]) -> list[dict]:
        """
        清洗K线数据

        Args:
            bars: 原始K线数据列表

        Returns:
            清洗后的K线数据列表
        """
        if not bars:
            return []

        # 转换为DataFrame便于处理
        df = pd.DataFrame(bars)

        # 按时间排序
        df = df.sort_values("datetime")

        # 检测并处理缺失值
        df = self._handle_missing_values(df)

        # 检测并处理异常值
        df = self._handle_outliers(df)

        # 检测并删除重复数据
        df = self._handle_duplicates(df)

        # 检测价格合理性
        df = self._validate_prices(df)

        # 转换回列表
        cleaned_bars = df.to_dict("records")

        return cleaned_bars

    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理缺失值"""
        # 记录缺失值
        missing_count = df.isnull().sum().sum()
        if missing_count > 0:
            self.issues.append({
                "type": DataQualityIssue.MISSING_VALUE.value,
                "count": int(missing_count),
                "message": f"发现{missing_count}个缺失值",
            })

        # 前向填充价格数据
        price_cols = ["open_price", "high_price", "low_price", "close_price"]
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].fillna(method="ffill")

        # 填充成交量为0
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0)

        if "turnover" in df.columns:
            df["turnover"] = df["turnover"].fillna(0)

        return df

    def _handle_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理异常值"""
        if "close_price" not in df.columns or len(df) < 20:
            return df

        # 使用Z-score检测异常值
        prices = df["close_price"]
        z_scores = np.abs((prices - prices.mean()) / prices.std())

        # 标记异常值 (|z| > 3)
        outliers = z_scores > 3
        outlier_count = outliers.sum()

        if outlier_count > 0:
            self.issues.append({
                "type": DataQualityIssue.OUTLIER.value,
                "count": int(outlier_count),
                "message": f"发现{outlier_count}个价格异常值",
            })

            # 使用中位数替换异常值
            median_price = prices.median()
            df.loc[outliers, "close_price"] = median_price

        return df

    def _handle_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理重复数据"""
        if "datetime" not in df.columns:
            return df

        # 检测重复时间戳
        duplicates = df.duplicated(subset=["datetime"], keep="first")
        dup_count = duplicates.sum()

        if dup_count > 0:
            self.issues.append({
                "type": DataQualityIssue.DUPLICATE.value,
                "count": int(dup_count),
                "message": f"发现{dup_count}条重复数据",
            })

            # 删除重复项
            df = df[~duplicates]

        return df

    def _validate_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """验证价格合理性"""
        price_cols = ["open_price", "high_price", "low_price", "close_price"]

        # 检查负价格
        for col in price_cols:
            if col in df.columns:
                negative = df[col] < 0
                if negative.any():
                    self.issues.append({
                        "type": DataQualityIssue.NEGATIVE_PRICE.value,
                        "count": int(negative.sum()),
                        "message": f"{col}中发现{negative.sum()}个负价格",
                    })
                    # 将负价格设为NaN，后续会填充
                    df.loc[negative, col] = np.nan

        # 检查OHLC关系
        if all(col in df.columns for col in ["high_price", "low_price", "open_price", "close_price"]):
            # high >= max(open, close, low)
            invalid_high = df["high_price"] < df[["open_price", "close_price", "low_price"]].max(axis=1)
            # low <= min(open, close, high)
            invalid_low = df["low_price"] > df[["open_price", "close_price", "high_price"]].min(axis=1)

            if invalid_high.any() or invalid_low.any():
                self.issues.append({
                    "type": DataQualityIssue.PRICE_JUMP.value,
                    "count": int(invalid_high.sum() + invalid_low.sum()),
                    "message": "发现OHLC关系异常",
                })

        return df

    def check_data_quality(self, bars: list[dict]) -> QualityReport:
        """
        检查数据质量

        Args:
            bars: K线数据列表

        Returns:
            质量报告
        """
        if not bars:
            return QualityReport()

        df = pd.DataFrame(bars)
        total_records = len(df)

        # 重置问题列表
        self.issues = []

        # 检查缺失值
        missing_count = df.isnull().sum().sum()

        # 检查重复
        if "datetime" in df.columns:
            dup_count = df.duplicated(subset=["datetime"]).sum()
        else:
            dup_count = 0

        # 检查异常值
        outlier_count = 0
        if "close_price" in df.columns and len(df) >= 20:
            prices = df["close_price"]
            z_scores = np.abs((prices - prices.mean()) / prices.std())
            outlier_count = (z_scores > 3).sum()

        # 检查数据连续性
        gap_count = 0
        if "datetime" in df.columns and len(df) > 1:
            df_sorted = df.sort_values("datetime")
            time_diff = df_sorted["datetime"].diff()
            # 假设日K线，正常间隔应为1天
            expected_diff = pd.Timedelta(days=1)
            gaps = time_diff > expected_diff * 2  # 超过2天的间隔视为缺失
            gap_count = gaps.sum()

        report = QualityReport(
            total_records=total_records,
            issues_found=int(missing_count + dup_count + outlier_count + gap_count),
            missing_rate=missing_count / max(total_records * len(df.columns), 1),
            outlier_rate=outlier_count / max(total_records, 1),
            duplicate_rate=dup_count / max(total_records, 1),
            issues=self.issues,
        )

        return report

    def fill_missing_bars(
        self,
        bars: list[dict],
        interval: str = "d",
        start: datetime | None = None,
        end: datetime | None = None
    ) -> list[dict]:
        """
        填充缺失的K线

        Args:
            bars: 原始K线数据
            interval: 时间周期
            start: 开始时间
            end: 结束时间

        Returns:
            填充后的K线数据
        """
        if not bars:
            return bars

        df = pd.DataFrame(bars)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
        df = df.sort_index()

        # 确定时间范围
        if start is None:
            start = df.index.min()
        if end is None:
            end = df.index.max()

        # 创建完整的时间序列
        if interval == "d":
            full_index = pd.date_range(start=start, end=end, freq="B")  # 工作日
        elif interval == "1m":
            full_index = pd.date_range(start=start, end=end, freq="T")
        else:
            full_index = pd.date_range(start=start, end=end, freq="B")

        # 重新索引
        df = df.reindex(full_index)

        # 填充缺失值
        price_cols = ["open_price", "high_price", "low_price", "close_price"]
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].fillna(method="ffill")

        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0)
        if "turnover" in df.columns:
            df["turnover"] = df["turnover"].fillna(0)

        # 重置索引
        df = df.reset_index()
        df = df.rename(columns={"index": "datetime"})

        return df.to_dict("records")
