"""
仓位管理模块

实现动态仓位计算和风险管理
"""

from dataclasses import dataclass

from collections import defaultdict

import numpy as np

from vnpy.trader.object import BarData


@dataclass
class PositionConfig:
    """仓位配置"""
    base_position: float = 0.1              # 基础仓位 10%
    max_position: float = 0.3               # 最大仓位 30%
    min_position: float = 0.0               # 最小仓位 0%
    atr_multiplier: float = 2.0             # ATR乘数
    risk_per_trade: float = 0.02            # 单笔交易风险 2%
    confidence_threshold: float = 0.6       # 信号置信度阈值


class PositionManager:
    """
    仓位管理器

    根据项目规则文档中的动态仓位计算公式：
    position_size = min(
        base_position * (current_confidence / 0.6),
        max_position_per_symbol,
        portfolio_value * max_risk_per_trade / (atr * multiplier)
    )
    """

    def __init__(self, config: PositionConfig | None = None) -> None:
        """Constructor"""
        self.config: PositionConfig = config or PositionConfig()

        # 持仓状态
        self.positions: dict[str, float] = defaultdict(float)       # 当前持仓数量
        self.position_cost: dict[str, float] = defaultdict(float)   # 持仓成本
        self.position_value: dict[str, float] = defaultdict(float)  # 持仓市值

        # ATR缓存
        self.atr_cache: dict[str, float] = {}

        # 组合状态
        self.portfolio_value: float = 0.0
        self.cash_available: float = 0.0

    def set_portfolio_value(self, value: float, cash: float) -> None:
        """设置组合价值"""
        self.portfolio_value = value
        self.cash_available = cash

    def calculate_atr(self, bars: list[BarData], period: int = 14) -> float:
        """计算ATR (Average True Range)"""
        if len(bars) < period:
            return 0.0

        tr_values: list[float] = []
        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1]

            tr1 = bar.high_price - bar.low_price
            tr2 = abs(bar.high_price - prev_bar.close_price)
            tr3 = abs(bar.low_price - prev_bar.close_price)

            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)

        if len(tr_values) < period:
            return 0.0

        atr = float(np.mean(tr_values[-period:]))
        return atr

    def calculate_position_size(
        self,
        vt_symbol: str,
        confidence: float,
        current_price: float,
        atr: float | None = None,
        bars: list[BarData] | None = None
    ) -> float:
        """
        计算目标仓位大小

        Args:
            vt_symbol: 合约代码
            confidence: 信号置信度 (0-1)
            current_price: 当前价格
            atr: ATR值，如未提供则自动计算
            bars: K线数据，用于计算ATR

        Returns:
            目标持仓数量
        """
        if confidence < self.config.confidence_threshold:
            return 0.0

        # 计算ATR
        if atr is None and bars is not None:
            atr = self.calculate_atr(bars)

        if atr is None or atr == 0:
            atr = current_price * 0.02  # 默认2%波动

        # 基于信号强度的仓位
        confidence_position = self.config.base_position * (confidence / self.config.confidence_threshold)

        # 基于风险平价的仓位
        risk_position = (self.portfolio_value * self.config.risk_per_trade) / (atr * self.config.atr_multiplier)

        # 取最小值
        target_value = min(
            confidence_position * self.portfolio_value,
            self.config.max_position * self.portfolio_value,
            risk_position
        )

        # 转换为数量
        target_size = target_value / current_price if current_price > 0 else 0

        return target_size

    def calculate_position_pct(
        self,
        vt_symbol: str,
        confidence: float,
        atr: float | None = None
    ) -> float:
        """
        计算目标仓位比例

        Returns:
            目标仓位比例 (0-1)
        """
        if confidence < self.config.confidence_threshold:
            return 0.0

        # 基于信号强度的仓位比例
        confidence_pct = self.config.base_position * (confidence / self.config.confidence_threshold)

        # 限制在最大仓位内
        target_pct = min(confidence_pct, self.config.max_position)

        return target_pct

    def update_position(
        self,
        vt_symbol: str,
        size: float,
        price: float,
        is_open: bool = True
    ) -> None:
        """更新持仓"""
        if is_open:
            # 开仓或加仓
            old_size = self.positions[vt_symbol]
            old_cost = self.position_cost[vt_symbol]

            new_size = old_size + size
            if new_size > 0:
                new_cost = (old_cost * old_size + price * size) / new_size
                self.position_cost[vt_symbol] = new_cost

            self.positions[vt_symbol] = new_size
        else:
            # 平仓或减仓
            self.positions[vt_symbol] -= size

            if self.positions[vt_symbol] <= 0:
                self.positions[vt_symbol] = 0
                self.position_cost[vt_symbol] = 0

        # 更新持仓市值
        self.position_value[vt_symbol] = self.positions[vt_symbol] * price

    def get_position(self, vt_symbol: str) -> float:
        """获取当前持仓数量"""
        return self.positions[vt_symbol]

    def get_position_value(self, vt_symbol: str) -> float:
        """获取持仓市值"""
        return self.position_value[vt_symbol]

    def get_position_pct(self, vt_symbol: str) -> float:
        """获取持仓比例"""
        if self.portfolio_value <= 0:
            return 0.0
        return self.position_value[vt_symbol] / self.portfolio_value

    def get_total_position_value(self) -> float:
        """获取总持仓市值"""
        return sum(self.position_value.values())

    def get_total_position_pct(self) -> float:
        """获取总仓位比例"""
        if self.portfolio_value <= 0:
            return 0.0
        return self.get_total_position_value() / self.portfolio_value

    def get_unrealized_pnl(self, vt_symbol: str, current_price: float) -> float:
        """获取未实现盈亏"""
        pos = self.positions[vt_symbol]
        cost = self.position_cost[vt_symbol]

        if pos == 0 or cost == 0:
            return 0.0

        return (current_price - cost) * pos

    def get_unrealized_pnl_pct(self, vt_symbol: str, current_price: float) -> float:
        """获取未实现盈亏比例"""
        cost = self.position_cost[vt_symbol]

        if cost == 0:
            return 0.0

        return (current_price - cost) / cost

    def should_reduce_position(self, vt_symbol: str, current_price: float, stop_loss_pct: float = 0.05) -> bool:
        """检查是否需要减仓（止损）"""
        pnl_pct = self.get_unrealized_pnl_pct(vt_symbol, current_price)

        if pnl_pct < -stop_loss_pct:
            return True

        return False

    def get_rebalance_targets(
        self,
        signals: dict[str, float],
        prices: dict[str, float],
        bars_dict: dict[str, list[BarData]] | None = None
    ) -> dict[str, float]:
        """
        获取再平衡目标仓位

        Args:
            signals: 信号字典 {vt_symbol: confidence}
            prices: 价格字典 {vt_symbol: price}
            bars_dict: K线数据字典 {vt_symbol: bars}

        Returns:
            目标持仓数量字典 {vt_symbol: target_size}
        """
        targets: dict[str, float] = {}

        # 计算总信号强度
        total_confidence = sum(signals.values())
        if total_confidence == 0:
            return targets

        # 归一化信号
        normalized_signals = {
            symbol: conf / total_confidence
            for symbol, conf in signals.items()
        }

        # 计算目标仓位
        for vt_symbol, confidence in normalized_signals.items():
            if vt_symbol not in prices:
                continue

            price = prices[vt_symbol]
            bars = bars_dict.get(vt_symbol) if bars_dict else None

            target_size = self.calculate_position_size(
                vt_symbol=vt_symbol,
                confidence=confidence,
                current_price=price,
                bars=bars
            )

            targets[vt_symbol] = target_size

        return targets

    def get_position_report(self) -> dict:
        """获取仓位报告"""
        return {
            "portfolio": {
                "total_value": self.portfolio_value,
                "cash_available": self.cash_available,
                "position_value": self.get_total_position_value(),
                "position_pct": self.get_total_position_pct(),
            },
            "positions": {
                symbol: {
                    "size": size,
                    "cost": self.position_cost[symbol],
                    "value": self.position_value[symbol],
                    "pct": self.get_position_pct(symbol),
                }
                for symbol, size in self.positions.items()
                if size != 0
            },
            "config": {
                "base_position": self.config.base_position,
                "max_position": self.config.max_position,
                "risk_per_trade": self.config.risk_per_trade,
            },
        }
