"""
数据监控模块

监控数据质量和延迟
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque


@dataclass
class DataQualityMetrics:
    """数据质量指标"""
    timestamp: datetime
    symbol: str
    data_type: str
    record_count: int
    missing_count: int
    delay_seconds: float
    anomaly_count: int


class DataMonitor:
    """
    数据监控器

    监控数据质量和延迟，包括：
    - 数据完整性
    - 数据延迟
    - 数据异常
    - 数据源状态
    """

    def __init__(self, history_size: int = 1000) -> None:
        """
        Constructor

        Args:
            history_size: 历史数据保留数量
        """
        self.history_size = history_size

        # 数据质量历史
        self.quality_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))

        # 数据源状态
        self.data_source_status: Dict[str, Dict] = {}

        # 统计
        self.stats: Dict[str, Dict] = defaultdict(lambda: {
            "total_records": 0,
            "missing_records": 0,
            "anomaly_records": 0,
            "total_delay_ms": 0.0,
            "record_count": 0,
        })

        # 阈值
        self.thresholds = {
            "max_delay_seconds": 5.0,
            "max_missing_rate": 0.001,
            "max_anomaly_rate": 0.01,
        }

    def record_data_quality(
        self,
        symbol: str,
        data_type: str,
        record_count: int,
        missing_count: int = 0,
        delay_seconds: float = 0.0,
        anomaly_count: int = 0
    ) -> None:
        """
        记录数据质量指标

        Args:
            symbol: 合约代码
            data_type: 数据类型
            record_count: 记录总数
            missing_count: 缺失记录数
            delay_seconds: 延迟秒数
            anomaly_count: 异常记录数
        """
        key = f"{symbol}_{data_type}"

        metrics = DataQualityMetrics(
            timestamp=datetime.now(),
            symbol=symbol,
            data_type=data_type,
            record_count=record_count,
            missing_count=missing_count,
            delay_seconds=delay_seconds,
            anomaly_count=anomaly_count
        )

        self.quality_history[key].append(metrics)

        # 更新统计
        self.stats[key]["total_records"] += record_count
        self.stats[key]["missing_records"] += missing_count
        self.stats[key]["anomaly_records"] += anomaly_count
        self.stats[key]["total_delay_ms"] += delay_seconds * 1000
        self.stats[key]["record_count"] += 1

    def update_data_source_status(
        self,
        source_name: str,
        is_connected: bool,
        last_update: Optional[datetime] = None,
        error_message: str = ""
    ) -> None:
        """
        更新数据源状态

        Args:
            source_name: 数据源名称
            is_connected: 是否连接
            last_update: 最后更新时间
            error_message: 错误信息
        """
        self.data_source_status[source_name] = {
            "is_connected": is_connected,
            "last_update": last_update or datetime.now(),
            "error_message": error_message,
        }

    def get_missing_rate(self, symbol: str, data_type: str) -> float:
        """
        获取缺失率

        Args:
            symbol: 合约代码
            data_type: 数据类型

        Returns:
            缺失率（0-1）
        """
        key = f"{symbol}_{data_type}"
        stats = self.stats[key]

        if stats["total_records"] == 0:
            return 0.0

        return stats["missing_records"] / stats["total_records"]

    def get_avg_delay(self, symbol: str, data_type: str) -> float:
        """
        获取平均延迟

        Args:
            symbol: 合约代码
            data_type: 数据类型

        Returns:
            平均延迟（毫秒）
        """
        key = f"{symbol}_{data_type}"
        stats = self.stats[key]

        if stats["record_count"] == 0:
            return 0.0

        return stats["total_delay_ms"] / stats["record_count"]

    def get_anomaly_rate(self, symbol: str, data_type: str) -> float:
        """
        获取异常率

        Args:
            symbol: 合约代码
            data_type: 数据类型

        Returns:
            异常率（0-1）
        """
        key = f"{symbol}_{data_type}"
        stats = self.stats[key]

        if stats["total_records"] == 0:
            return 0.0

        return stats["anomaly_records"] / stats["total_records"]

    def check_data_quality(self, symbol: str, data_type: str) -> Dict[str, bool]:
        """
        检查数据质量

        Args:
            symbol: 合约代码
            data_type: 数据类型

        Returns:
            各质量指标是否正常的字典
        """
        return {
            "delay_ok": self.get_avg_delay(symbol, data_type) <= self.thresholds["max_delay_seconds"] * 1000,
            "missing_ok": self.get_missing_rate(symbol, data_type) <= self.thresholds["max_missing_rate"],
            "anomaly_ok": self.get_anomaly_rate(symbol, data_type) <= self.thresholds["max_anomaly_rate"],
        }

    def get_symbol_summary(self, symbol: str, data_type: str) -> Dict:
        """
        获取合约数据摘要

        Args:
            symbol: 合约代码
            data_type: 数据类型

        Returns:
            数据质量摘要
        """
        key = f"{symbol}_{data_type}"
        stats = self.stats[key]

        return {
            "symbol": symbol,
            "data_type": data_type,
            "total_records": stats["total_records"],
            "missing_rate": round(self.get_missing_rate(symbol, data_type) * 100, 4),
            "avg_delay_ms": round(self.get_avg_delay(symbol, data_type), 2),
            "anomaly_rate": round(self.get_anomaly_rate(symbol, data_type) * 100, 4),
            "quality_check": self.check_data_quality(symbol, data_type),
        }

    def get_data_source_summary(self) -> Dict[str, Dict]:
        """
        获取数据源摘要

        Returns:
            数据源状态摘要
        """
        summary = {}

        for source_name, status in self.data_source_status.items():
            # 计算最后更新时间距今的秒数
            time_since_update = (datetime.now() - status["last_update"]).total_seconds()

            summary[source_name] = {
                "is_connected": status["is_connected"],
                "time_since_update_seconds": round(time_since_update, 2),
                "error_message": status["error_message"],
                "healthy": status["is_connected"] and time_since_update < 60,
            }

        return summary

    def get_all_symbols_summary(self) -> List[Dict]:
        """
        获取所有合约数据摘要

        Returns:
            数据质量摘要列表
        """
        summaries = []

        for key in self.stats.keys():
            parts = key.rsplit("_", 1)
            if len(parts) == 2:
                symbol, data_type = parts
                summaries.append(self.get_symbol_summary(symbol, data_type))

        return summaries

    def set_threshold(self, metric: str, value: float) -> None:
        """
        设置阈值

        Args:
            metric: 指标名称
            value: 阈值
        """
        if metric in self.thresholds:
            self.thresholds[metric] = value

    def reset_stats(self, symbol: str = "", data_type: str = "") -> None:
        """
        重置统计

        Args:
            symbol: 合约代码，为空则重置所有
            data_type: 数据类型，为空则重置该合约所有类型
        """
        if symbol and data_type:
            key = f"{symbol}_{data_type}"
            if key in self.stats:
                del self.stats[key]
            if key in self.quality_history:
                del self.quality_history[key]
        elif symbol:
            keys_to_remove = [k for k in self.stats.keys() if k.startswith(f"{symbol}_")]
            for key in keys_to_remove:
                del self.stats[key]
                if key in self.quality_history:
                    del self.quality_history[key]
        else:
            self.stats.clear()
            self.quality_history.clear()
