"""
交易日志记录系统

记录交易相关的所有日志，支持多种日志级别和分类
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import threading


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(Enum):
    """日志分类"""
    TRADE = "trade"           # 交易相关
    STRATEGY = "strategy"     # 策略相关
    RISK = "risk"             # 风控相关
    SYSTEM = "system"         # 系统相关
    DATA = "data"             # 数据相关
    PERFORMANCE = "performance"  # 性能相关


@dataclass
class TradeLogEntry:
    """交易日志条目"""
    # 基本信息
    log_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    level: LogLevel = LogLevel.INFO
    category: LogCategory = LogCategory.TRADE
    
    # 内容
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    # 上下文
    strategy_name: Optional[str] = None
    vt_symbol: Optional[str] = None
    trade_id: Optional[str] = None
    order_id: Optional[str] = None
    
    # 标签
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "category": self.category.value,
            "message": self.message,
            "details": self.details,
            "strategy_name": self.strategy_name,
            "vt_symbol": self.vt_symbol,
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "tags": self.tags,
        }


class TradeLogger:
    """
    交易日志记录器
    
    功能：
    1. 多级别日志记录
    2. 日志分类和标签
    3. 日志查询和过滤
    4. 日志导出和分析
    """
    
    def __init__(
        self,
        storage_path: str = "./logs/trade",
        max_entries: int = 100000,
        auto_save: bool = True,
        save_interval: int = 100,
    ) -> None:
        """
        Constructor
        
        Args:
            storage_path: 存储路径
            max_entries: 最大条目数
            auto_save: 是否自动保存
            save_interval: 自动保存间隔（条目数）
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.max_entries = max_entries
        self.auto_save = auto_save
        self.save_interval = save_interval
        
        # 日志存储
        self.entries: List[TradeLogEntry] = []
        self._entries_since_save = 0
        
        # 回调
        self._callbacks: Dict[LogLevel, List[Callable]] = {
            level: [] for level in LogLevel
        }
        
        # 锁
        self._lock = threading.Lock()
        
        # 加载历史日志
        self._load_history()
    
    def _load_history(self) -> None:
        """加载历史日志"""
        log_file = self.storage_path / "trade_logs.json"
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for entry_data in data[-self.max_entries:]:
                        entry = TradeLogEntry(
                            log_id=entry_data["log_id"],
                            timestamp=datetime.fromisoformat(entry_data["timestamp"]),
                            level=LogLevel(entry_data["level"]),
                            category=LogCategory(entry_data["category"]),
                            message=entry_data["message"],
                            details=entry_data.get("details", {}),
                            strategy_name=entry_data.get("strategy_name"),
                            vt_symbol=entry_data.get("vt_symbol"),
                            trade_id=entry_data.get("trade_id"),
                            order_id=entry_data.get("order_id"),
                            tags=entry_data.get("tags", []),
                        )
                        self.entries.append(entry)
            except Exception as e:
                print(f"加载历史日志失败: {e}")
    
    def _save_logs(self) -> None:
        """保存日志"""
        log_file = self.storage_path / "trade_logs.json"
        try:
            data = [entry.to_dict() for entry in self.entries[-self.max_entries:]]
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            self._entries_since_save = 0
        except Exception as e:
            print(f"保存日志失败: {e}")
    
    def log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        category: LogCategory = LogCategory.TRADE,
        details: Optional[Dict[str, Any]] = None,
        strategy_name: Optional[str] = None,
        vt_symbol: Optional[str] = None,
        trade_id: Optional[str] = None,
        order_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> TradeLogEntry:
        """
        记录日志
        
        Args:
            message: 日志消息
            level: 日志级别
            category: 日志分类
            details: 详细信息
            strategy_name: 策略名称
            vt_symbol: 合约代码
            trade_id: 成交ID
            order_id: 订单ID
            tags: 标签
            
        Returns:
            日志条目
        """
        entry = TradeLogEntry(
            message=message,
            level=level,
            category=category,
            details=details or {},
            strategy_name=strategy_name,
            vt_symbol=vt_symbol,
            trade_id=trade_id,
            order_id=order_id,
            tags=tags or [],
        )
        
        with self._lock:
            self.entries.append(entry)
            
            # 限制条目数
            if len(self.entries) > self.max_entries:
                self.entries = self.entries[-self.max_entries:]
            
            self._entries_since_save += 1
            
            # 自动保存
            if self.auto_save and self._entries_since_save >= self.save_interval:
                self._save_logs()
        
        # 触发回调
        self._trigger_callbacks(entry)
        
        return entry
    
    def debug(
        self,
        message: str,
        category: LogCategory = LogCategory.TRADE,
        **kwargs
    ) -> TradeLogEntry:
        """记录DEBUG级别日志"""
        return self.log(message, LogLevel.DEBUG, category, **kwargs)
    
    def info(
        self,
        message: str,
        category: LogCategory = LogCategory.TRADE,
        **kwargs
    ) -> TradeLogEntry:
        """记录INFO级别日志"""
        return self.log(message, LogLevel.INFO, category, **kwargs)
    
    def warning(
        self,
        message: str,
        category: LogCategory = LogCategory.TRADE,
        **kwargs
    ) -> TradeLogEntry:
        """记录WARNING级别日志"""
        return self.log(message, LogLevel.WARNING, category, **kwargs)
    
    def error(
        self,
        message: str,
        category: LogCategory = LogCategory.TRADE,
        **kwargs
    ) -> TradeLogEntry:
        """记录ERROR级别日志"""
        return self.log(message, LogLevel.ERROR, category, **kwargs)
    
    def critical(
        self,
        message: str,
        category: LogCategory = LogCategory.TRADE,
        **kwargs
    ) -> TradeLogEntry:
        """记录CRITICAL级别日志"""
        return self.log(message, LogLevel.CRITICAL, category, **kwargs)
    
    def log_trade(
        self,
        vt_symbol: str,
        direction: str,
        volume: float,
        price: float,
        pnl: Optional[float] = None,
        strategy_name: Optional[str] = None,
        **kwargs
    ) -> TradeLogEntry:
        """
        记录交易日志
        
        Args:
            vt_symbol: 合约代码
            direction: 方向
            volume: 数量
            price: 价格
            pnl: 盈亏
            strategy_name: 策略名称
            
        Returns:
            日志条目
        """
        message = f"交易: {vt_symbol} {direction} {volume}@{price}"
        if pnl is not None:
            message += f" PnL={pnl:,.2f}"
        
        details = {
            "direction": direction,
            "volume": volume,
            "price": price,
        }
        if pnl is not None:
            details["pnl"] = pnl
        
        return self.log(
            message=message,
            level=LogLevel.INFO,
            category=LogCategory.TRADE,
            details=details,
            vt_symbol=vt_symbol,
            strategy_name=strategy_name,
            **kwargs
        )
    
    def log_signal(
        self,
        strategy_name: str,
        vt_symbol: str,
        signal_type: str,
        signal_value: float,
        confidence: Optional[float] = None,
        **kwargs
    ) -> TradeLogEntry:
        """
        记录信号日志
        
        Args:
            strategy_name: 策略名称
            vt_symbol: 合约代码
            signal_type: 信号类型
            signal_value: 信号值
            confidence: 置信度
            
        Returns:
            日志条目
        """
        message = f"信号: {strategy_name} {vt_symbol} {signal_type}={signal_value:.4f}"
        if confidence is not None:
            message += f" 置信度={confidence:.2%}"
        
        details = {
            "signal_type": signal_type,
            "signal_value": signal_value,
        }
        if confidence is not None:
            details["confidence"] = confidence
        
        return self.log(
            message=message,
            level=LogLevel.INFO,
            category=LogCategory.STRATEGY,
            details=details,
            strategy_name=strategy_name,
            vt_symbol=vt_symbol,
            **kwargs
        )
    
    def log_risk_event(
        self,
        event_type: str,
        message: str,
        severity: str = "warning",
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> TradeLogEntry:
        """
        记录风控事件
        
        Args:
            event_type: 事件类型
            message: 消息
            severity: 严重程度
            details: 详细信息
            
        Returns:
            日志条目
        """
        level_map = {
            "info": LogLevel.INFO,
            "warning": LogLevel.WARNING,
            "error": LogLevel.ERROR,
            "critical": LogLevel.CRITICAL,
        }
        level = level_map.get(severity, LogLevel.WARNING)
        
        full_message = f"风控事件 [{event_type}]: {message}"
        
        return self.log(
            message=full_message,
            level=level,
            category=LogCategory.RISK,
            details={"event_type": event_type, **(details or {})},
            **kwargs
        )
    
    def _trigger_callbacks(self, entry: TradeLogEntry) -> None:
        """触发回调"""
        callbacks = self._callbacks.get(entry.level, [])
        for callback in callbacks:
            try:
                callback(entry)
            except Exception as e:
                print(f"回调执行失败: {e}")
    
    def on_level(self, level: LogLevel, callback: Callable[[TradeLogEntry], None]) -> None:
        """
        注册级别回调
        
        Args:
            level: 日志级别
            callback: 回调函数
        """
        self._callbacks[level].append(callback)
    
    def query(
        self,
        level: Optional[LogLevel] = None,
        category: Optional[LogCategory] = None,
        strategy_name: Optional[str] = None,
        vt_symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[TradeLogEntry]:
        """
        查询日志
        
        Args:
            level: 日志级别
            category: 日志分类
            strategy_name: 策略名称
            vt_symbol: 合约代码
            start_time: 开始时间
            end_time: 结束时间
            tags: 标签
            limit: 限制数量
            
        Returns:
            日志条目列表
        """
        results = self.entries
        
        if level:
            results = [e for e in results if e.level == level]
        
        if category:
            results = [e for e in results if e.category == category]
        
        if strategy_name:
            results = [e for e in results if e.strategy_name == strategy_name]
        
        if vt_symbol:
            results = [e for e in results if e.vt_symbol == vt_symbol]
        
        if start_time:
            results = [e for e in results if e.timestamp >= start_time]
        
        if end_time:
            results = [e for e in results if e.timestamp <= end_time]
        
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        
        return results[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self.entries)
        
        level_counts = {level.value: 0 for level in LogLevel}
        category_counts = {cat.value: 0 for cat in LogCategory}
        
        for entry in self.entries:
            level_counts[entry.level.value] += 1
            category_counts[entry.category.value] += 1
        
        return {
            "total_entries": total,
            "by_level": level_counts,
            "by_category": category_counts,
            "storage_path": str(self.storage_path),
        }
    
    def export_to_file(
        self,
        filepath: str,
        level: Optional[LogLevel] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """
        导出日志到文件
        
        Args:
            filepath: 文件路径
            level: 日志级别过滤
            start_time: 开始时间
            end_time: 结束时间
        """
        entries = self.query(level=level, start_time=start_time, end_time=end_time)
        data = [entry.to_dict() for entry in entries]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def clear(self, before: Optional[datetime] = None) -> int:
        """
        清除日志
        
        Args:
            before: 清除该时间之前的日志
            
        Returns:
            清除的条目数
        """
        with self._lock:
            if before:
                original_count = len(self.entries)
                self.entries = [e for e in self.entries if e.timestamp >= before]
                cleared = original_count - len(self.entries)
            else:
                cleared = len(self.entries)
                self.entries = []
            
            self._save_logs()
            return cleared
    
    def close(self) -> None:
        """关闭日志记录器"""
        self._save_logs()
