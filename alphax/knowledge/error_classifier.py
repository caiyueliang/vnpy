"""
错误分类系统

自动分类交易和系统中的错误，便于分析和改进
"""

import json
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Pattern
import uuid


class ErrorCategory(Enum):
    """错误分类"""
    # 系统错误
    SYSTEM_ERROR = "system_error"           # 系统错误
    NETWORK_ERROR = "network_error"         # 网络错误
    DATABASE_ERROR = "database_error"       # 数据库错误
    
    # 交易错误
    ORDER_ERROR = "order_error"             # 订单错误
    TRADE_ERROR = "trade_error"             # 成交错误
    POSITION_ERROR = "position_error"       # 持仓错误
    
    # 数据错误
    DATA_ERROR = "data_error"               # 数据错误
    DATA_MISSING = "data_missing"           # 数据缺失
    DATA_QUALITY = "data_quality"           # 数据质量问题
    
    # 策略错误
    STRATEGY_ERROR = "strategy_error"       # 策略错误
    SIGNAL_ERROR = "signal_error"           # 信号错误
    CALCULATION_ERROR = "calculation_error" # 计算错误
    
    # 风控错误
    RISK_ERROR = "risk_error"               # 风控错误
    LIMIT_ERROR = "limit_error"             # 限制错误
    
    # 未知错误
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"           # 低
    MEDIUM = "medium"     # 中
    HIGH = "high"         # 高
    CRITICAL = "critical" # 严重


@dataclass
class ErrorPattern:
    """错误模式"""
    category: ErrorCategory
    severity: ErrorSeverity
    patterns: List[Pattern] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ClassifiedError:
    """分类后的错误"""
    error_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 原始错误
    error_message: str = ""
    error_type: str = ""
    stack_trace: str = ""
    
    # 分类结果
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    confidence: float = 0.0
    
    # 上下文
    context: Dict[str, Any] = field(default_factory=dict)
    
    # 解决方案
    suggested_solution: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "error_type": self.error_type,
            "stack_trace": self.stack_trace,
            "category": self.category.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "context": self.context,
            "suggested_solution": self.suggested_solution,
        }


class ErrorClassifier:
    """
    错误分类器
    
    功能：
    1. 自动识别错误类型
    2. 评估错误严重程度
    3. 提供解决方案建议
    4. 错误统计和分析
    """
    
    def __init__(self, storage_path: str = "./logs/errors") -> None:
        """
        Constructor
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 错误历史
        self.errors: List[ClassifiedError] = []
        
        # 分类模式
        self.patterns: List[ErrorPattern] = []
        self._init_patterns()
        
        # 统计
        self.category_counts: Dict[ErrorCategory, int] = {cat: 0 for cat in ErrorCategory}
        self.severity_counts: Dict[ErrorSeverity, int] = {sev: 0 for sev in ErrorSeverity}
        
        # 加载历史错误
        self._load_errors()
    
    def _init_patterns(self) -> None:
        """初始化分类模式"""
        # 网络错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.NETWORK_ERROR,
            severity=ErrorSeverity.HIGH,
            patterns=[
                re.compile(r"connection.*refused", re.I),
                re.compile(r"timeout", re.I),
                re.compile(r"network.*unreachable", re.I),
                re.compile(r"socket.*error", re.I),
            ],
            keywords=["connection", "timeout", "network", "socket", "断开", "连接"],
            description="网络连接错误",
        ))
        
        # 数据库错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.DATABASE_ERROR,
            severity=ErrorSeverity.HIGH,
            patterns=[
                re.compile(r"database.*error", re.I),
                re.compile(r"sql.*error", re.I),
                re.compile(r"connection.*closed", re.I),
                re.compile(r"lock.*timeout", re.I),
            ],
            keywords=["database", "sql", "db", "数据库", "查询"],
            description="数据库错误",
        ))
        
        # 订单错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.ORDER_ERROR,
            severity=ErrorSeverity.MEDIUM,
            patterns=[
                re.compile(r"order.*reject", re.I),
                re.compile(r"insufficient.*fund", re.I),
                re.compile(r"invalid.*order", re.I),
            ],
            keywords=["order", "订单", "委托", "拒绝", "资金不足"],
            description="订单相关错误",
        ))
        
        # 数据错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.DATA_ERROR,
            severity=ErrorSeverity.MEDIUM,
            patterns=[
                re.compile(r"data.*error", re.I),
                re.compile(r"invalid.*data", re.I),
                re.compile(r"missing.*data", re.I),
            ],
            keywords=["data", "数据", "缺失", "无效"],
            description="数据错误",
        ))
        
        # 策略错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.STRATEGY_ERROR,
            severity=ErrorSeverity.MEDIUM,
            patterns=[
                re.compile(r"strategy.*error", re.I),
                re.compile(r"signal.*error", re.I),
                re.compile(r"calculation.*error", re.I),
            ],
            keywords=["strategy", "signal", "策略", "信号", "计算错误"],
            description="策略相关错误",
        ))
        
        # 风控错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.RISK_ERROR,
            severity=ErrorSeverity.HIGH,
            patterns=[
                re.compile(r"risk.*limit", re.I),
                re.compile(r"exceed.*limit", re.I),
                re.compile(r"circuit.*breaker", re.I),
            ],
            keywords=["risk", "limit", "风控", "限制", "熔断"],
            description="风控相关错误",
        ))
        
        # 系统错误
        self.patterns.append(ErrorPattern(
            category=ErrorCategory.SYSTEM_ERROR,
            severity=ErrorSeverity.CRITICAL,
            patterns=[
                re.compile(r"system.*error", re.I),
                re.compile(r"critical.*error", re.I),
                re.compile(r"fatal.*error", re.I),
            ],
            keywords=["system", "critical", "fatal", "系统错误", "严重"],
            description="系统级错误",
        ))
    
    def _load_errors(self) -> None:
        """加载历史错误"""
        error_file = self.storage_path / "classified_errors.json"
        if error_file.exists():
            try:
                with open(error_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for error_data in data:
                        error = ClassifiedError(
                            error_id=error_data["error_id"],
                            timestamp=datetime.fromisoformat(error_data["timestamp"]),
                            error_message=error_data["error_message"],
                            error_type=error_data.get("error_type", ""),
                            stack_trace=error_data.get("stack_trace", ""),
                            category=ErrorCategory(error_data["category"]),
                            severity=ErrorSeverity(error_data["severity"]),
                            confidence=error_data.get("confidence", 0.0),
                            context=error_data.get("context", {}),
                            suggested_solution=error_data.get("suggested_solution", ""),
                        )
                        self.errors.append(error)
                        self.category_counts[error.category] += 1
                        self.severity_counts[error.severity] += 1
            except Exception as e:
                print(f"加载历史错误失败: {e}")
    
    def _save_errors(self) -> None:
        """保存错误记录"""
        error_file = self.storage_path / "classified_errors.json"
        try:
            data = [error.to_dict() for error in self.errors[-10000:]]  # 保留最近10000条
            with open(error_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"保存错误记录失败: {e}")
    
    def classify(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassifiedError:
        """
        分类错误
        
        Args:
            error: 异常对象
            context: 上下文信息
            
        Returns:
            分类后的错误
        """
        error_message = str(error)
        error_type = type(error).__name__
        stack_trace = traceback.format_exc()
        
        # 匹配模式
        best_match = None
        best_confidence = 0.0
        
        for pattern in self.patterns:
            confidence = self._calculate_confidence(error_message, pattern)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = pattern
        
        # 创建分类结果
        if best_match and best_confidence > 0.3:
            classified = ClassifiedError(
                error_message=error_message,
                error_type=error_type,
                stack_trace=stack_trace,
                category=best_match.category,
                severity=best_match.severity,
                confidence=best_confidence,
                context=context or {},
            )
        else:
            classified = ClassifiedError(
                error_message=error_message,
                error_type=error_type,
                stack_trace=stack_trace,
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                confidence=0.0,
                context=context or {},
            )
        
        # 生成解决方案
        classified.suggested_solution = self._suggest_solution(classified)
        
        # 记录错误
        self.errors.append(classified)
        self.category_counts[classified.category] += 1
        self.severity_counts[classified.severity] += 1
        
        # 保存
        self._save_errors()
        
        return classified
    
    def _calculate_confidence(self, error_message: str, pattern: ErrorPattern) -> float:
        """计算匹配置信度"""
        confidence = 0.0
        
        # 正则匹配
        for regex in pattern.patterns:
            if regex.search(error_message):
                confidence += 0.5
        
        # 关键词匹配
        for keyword in pattern.keywords:
            if keyword.lower() in error_message.lower():
                confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _suggest_solution(self, error: ClassifiedError) -> str:
        """生成解决方案建议"""
        solutions = {
            ErrorCategory.NETWORK_ERROR: "检查网络连接，重试操作",
            ErrorCategory.DATABASE_ERROR: "检查数据库连接和状态",
            ErrorCategory.ORDER_ERROR: "检查订单参数和账户资金",
            ErrorCategory.DATA_ERROR: "检查数据源和数据质量",
            ErrorCategory.STRATEGY_ERROR: "检查策略逻辑和参数",
            ErrorCategory.RISK_ERROR: "检查风控设置和持仓状态",
            ErrorCategory.SYSTEM_ERROR: "检查系统资源，可能需要重启",
            ErrorCategory.UNKNOWN: "查看详细日志，手动分析原因",
        }
        
        return solutions.get(error.category, "未知错误类型，需要人工分析")
    
    def get_error_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        获取错误统计
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            统计信息
        """
        errors = self.errors
        
        if start_time:
            errors = [e for e in errors if e.timestamp >= start_time]
        
        if end_time:
            errors = [e for e in errors if e.timestamp <= end_time]
        
        # 按分类统计
        category_stats = {cat.value: 0 for cat in ErrorCategory}
        severity_stats = {sev.value: 0 for sev in ErrorSeverity}
        
        for error in errors:
            category_stats[error.category.value] += 1
            severity_stats[error.severity.value] += 1
        
        return {
            "total_errors": len(errors),
            "by_category": category_stats,
            "by_severity": severity_stats,
            "most_common": self._get_most_common_errors(errors, 5),
        }
    
    def _get_most_common_errors(
        self,
        errors: List[ClassifiedError],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """获取最常见的错误"""
        error_counts: Dict[str, int] = {}
        error_examples: Dict[str, ClassifiedError] = {}
        
        for error in errors:
            key = f"{error.category.value}:{error.error_type}"
            error_counts[key] = error_counts.get(key, 0) + 1
            if key not in error_examples:
                error_examples[key] = error
        
        # 排序
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {
                "category": error_examples[key].category.value,
                "error_type": error_examples[key].error_type,
                "count": count,
                "example_message": error_examples[key].error_message[:100],
            }
            for key, count in sorted_errors[:limit]
        ]
    
    def get_errors_by_category(
        self,
        category: ErrorCategory,
        limit: int = 100,
    ) -> List[ClassifiedError]:
        """
        获取指定分类的错误
        
        Args:
            category: 错误分类
            limit: 限制数量
            
        Returns:
            错误列表
        """
        return [
            e for e in self.errors
            if e.category == category
        ][-limit:]
    
    def export_report(self, filepath: str) -> None:
        """
        导出错误报告
        
        Args:
            filepath: 文件路径
        """
        stats = self.get_error_stats()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "recent_errors": [
                error.to_dict()
                for error in self.errors[-100:]
            ],
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
