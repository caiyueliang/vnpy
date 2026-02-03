"""
策略监控模块

监控策略运行状态和表现
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque


@dataclass
class StrategyMetrics:
    """策略指标数据"""
    timestamp: datetime
    strategy_name: str
    signal_count: int
    trade_count: int
    pnl: float
    drawdown: float
    win_rate: float
    sharpe_ratio: float


class StrategyMonitor:
    """
    策略监控器

    监控策略运行状态，包括：
    - 信号生成情况
    - 交易执行情况
    - 盈亏统计
    - 风险指标
    """

    def __init__(self, history_size: int = 1000) -> None:
        """
        Constructor

        Args:
            history_size: 每个策略历史数据保留数量
        """
        self.history_size = history_size

        # 策略数据
        self.strategy_signals: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))
        self.strategy_trades: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))
        self.strategy_pnl: Dict[str, float] = defaultdict(float)
        self.strategy_peak: Dict[str, float] = defaultdict(float)
        self.strategy_drawdown: Dict[str, float] = defaultdict(float)

        # 统计数据
        self.stats: Dict[str, Dict] = defaultdict(lambda: {
            "signal_count": 0,
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
        })

    def record_signal(
        self,
        strategy_name: str,
        vt_symbol: str,
        signal_type: str,
        strength: float = 0.0
    ) -> None:
        """
        记录策略信号

        Args:
            strategy_name: 策略名称
            vt_symbol: 合约代码
            signal_type: 信号类型（buy/sell/short/cover）
            strength: 信号强度
        """
        signal_record = {
            "vt_symbol": vt_symbol,
            "signal_type": signal_type,
            "strength": strength,
            "timestamp": datetime.now(),
        }

        self.strategy_signals[strategy_name].append(signal_record)
        self.stats[strategy_name]["signal_count"] += 1

    def record_trade(
        self,
        strategy_name: str,
        vt_symbol: str,
        direction: str,
        volume: float,
        price: float,
        pnl: float = 0.0
    ) -> None:
        """
        记录策略交易

        Args:
            strategy_name: 策略名称
            vt_symbol: 合约代码
            direction: 交易方向
            volume: 交易数量
            price: 交易价格
            pnl: 盈亏
        """
        trade_record = {
            "vt_symbol": vt_symbol,
            "direction": direction,
            "volume": volume,
            "price": price,
            "pnl": pnl,
            "timestamp": datetime.now(),
        }

        self.strategy_trades[strategy_name].append(trade_record)
        self.stats[strategy_name]["trade_count"] += 1

        # 更新盈亏
        self.strategy_pnl[strategy_name] += pnl
        self.stats[strategy_name]["total_pnl"] += pnl

        # 更新胜负统计
        if pnl > 0:
            self.stats[strategy_name]["win_count"] += 1
        elif pnl < 0:
            self.stats[strategy_name]["loss_count"] += 1

        # 更新回撤
        current_pnl = self.strategy_pnl[strategy_name]
        if current_pnl > self.strategy_peak[strategy_name]:
            self.strategy_peak[strategy_name] = current_pnl

        drawdown = self.strategy_peak[strategy_name] - current_pnl
        self.strategy_drawdown[strategy_name] = drawdown

        if drawdown > self.stats[strategy_name]["max_drawdown"]:
            self.stats[strategy_name]["max_drawdown"] = drawdown

    def get_win_rate(self, strategy_name: str) -> float:
        """
        获取策略胜率

        Args:
            strategy_name: 策略名称

        Returns:
            胜率（0-1）
        """
        stats = self.stats[strategy_name]
        total = stats["win_count"] + stats["loss_count"]

        if total == 0:
            return 0.0

        return stats["win_count"] / total

    def get_profit_factor(self, strategy_name: str) -> float:
        """
        获取盈亏比

        Args:
            strategy_name: 策略名称

        Returns:
            盈亏比
        """
        trades = list(self.strategy_trades[strategy_name])

        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))

        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def get_strategy_summary(self, strategy_name: str) -> Dict:
        """
        获取策略摘要

        Args:
            strategy_name: 策略名称

        Returns:
            策略统计摘要
        """
        stats = self.stats[strategy_name]

        return {
            "strategy_name": strategy_name,
            "signals": {
                "total": stats["signal_count"],
            },
            "trades": {
                "total": stats["trade_count"],
                "wins": stats["win_count"],
                "losses": stats["loss_count"],
                "win_rate": round(self.get_win_rate(strategy_name) * 100, 2),
            },
            "performance": {
                "total_pnl": round(stats["total_pnl"], 2),
                "current_drawdown": round(self.strategy_drawdown[strategy_name], 2),
                "max_drawdown": round(stats["max_drawdown"], 2),
                "profit_factor": round(self.get_profit_factor(strategy_name), 2),
            }
        }

    def get_all_summaries(self) -> Dict[str, Dict]:
        """
        获取所有策略摘要

        Returns:
            所有策略的统计摘要
        """
        return {
            name: self.get_strategy_summary(name)
            for name in self.stats.keys()
        }

    def get_active_strategies(self) -> List[str]:
        """
        获取活跃策略列表

        Returns:
            策略名称列表
        """
        return list(self.stats.keys())

    def reset_strategy(self, strategy_name: str) -> None:
        """
        重置策略统计

        Args:
            strategy_name: 策略名称
        """
        if strategy_name in self.strategy_signals:
            self.strategy_signals[strategy_name].clear()
        if strategy_name in self.strategy_trades:
            self.strategy_trades[strategy_name].clear()

        self.strategy_pnl[strategy_name] = 0.0
        self.strategy_peak[strategy_name] = 0.0
        self.strategy_drawdown[strategy_name] = 0.0

        self.stats[strategy_name] = {
            "signal_count": 0,
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
        }
