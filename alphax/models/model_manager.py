"""
机器学习模型管理器

实现模型版本控制、性能监控、自动重训练等功能
"""

import hashlib
import json
import pickle
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

import numpy as np
import pandas as pd


class ModelStatus(Enum):
    """模型状态"""
    TRAINING = "training"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class ModelType(Enum):
    """模型类型"""
    REGRESSION = "regression"
    CLASSIFICATION = "classification"
    CLUSTERING = "clustering"
    REINFORCEMENT = "reinforcement"


@dataclass
class ModelPerformance:
    """模型性能指标"""
    # 基础指标
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    
    # 回归指标
    mse: float = 0.0
    rmse: float = 0.0
    mae: float = 0.0
    r2_score: float = 0.0
    
    # 时间戳
    evaluated_at: datetime = field(default_factory=datetime.now)
    
    # 样本信息
    train_samples: int = 0
    test_samples: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "mse": self.mse,
            "rmse": self.rmse,
            "mae": self.mae,
            "r2_score": self.r2_score,
            "evaluated_at": self.evaluated_at.isoformat(),
            "train_samples": self.train_samples,
            "test_samples": self.test_samples,
        }


@dataclass
class ModelVersion:
    """模型版本信息"""
    # 基本信息
    version_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    model_name: str = ""
    model_type: ModelType = ModelType.REGRESSION
    
    # 版本信息
    version_number: int = 1
    parent_version: Optional[str] = None
    
    # 状态
    status: ModelStatus = ModelStatus.TRAINING
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    activated_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    
    # 性能
    performance: ModelPerformance = field(default_factory=ModelPerformance)
    
    # 元数据
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    feature_names: List[str] = field(default_factory=list)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    
    # 文件路径
    model_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "version_id": self.version_id,
            "model_name": self.model_name,
            "model_type": self.model_type.value,
            "version_number": self.version_number,
            "parent_version": self.parent_version,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "deprecated_at": self.deprecated_at.isoformat() if self.deprecated_at else None,
            "performance": self.performance.to_dict(),
            "hyperparameters": self.hyperparameters,
            "feature_names": self.feature_names,
            "description": self.description,
            "tags": self.tags,
            "model_path": self.model_path,
        }


@dataclass
class RetrainConfig:
    """自动重训练配置"""
    enabled: bool = True
    accuracy_drop_threshold: float = 0.10  # 准确率下降10%触发重训练
    min_samples_for_retrain: int = 1000    # 最少样本数
    retrain_interval_days: int = 7         # 定期重训练间隔
    max_retrain_attempts: int = 3          # 最大重训练次数


class ModelManager:
    """
    模型管理器
    
    功能：
    1. 模型版本控制 - 支持多版本管理和切换
    2. 性能监控 - 实时监控模型预测准确率
    3. 自动重训练 - 准确率下降时自动触发重训练
    4. A/B测试 - 支持模型对比测试
    """
    
    def __init__(
        self,
        model_name: str,
        model_type: ModelType,
        storage_path: str = "./models",
        retrain_config: Optional[RetrainConfig] = None,
    ) -> None:
        """
        Constructor
        
        Args:
            model_name: 模型名称
            model_type: 模型类型
            storage_path: 模型存储路径
            retrain_config: 自动重训练配置
        """
        self.model_name = model_name
        self.model_type = model_type
        self.storage_path = Path(storage_path)
        self.retrain_config = retrain_config or RetrainConfig()
        
        # 创建存储目录
        self.model_dir = self.storage_path / model_name
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        # 版本管理
        self.versions: Dict[str, ModelVersion] = {}
        self.active_version: Optional[str] = None
        
        # 性能监控
        self.prediction_history: List[Dict[str, Any]] = []
        self.accuracy_history: List[Dict[str, Any]] = []
        
        # A/B测试
        self.ab_test_versions: List[str] = []
        self.ab_test_weights: Dict[str, float] = {}
        
        # 回调函数
        self._retrain_callback: Optional[Callable] = None
        self._performance_callback: Optional[Callable] = None
        
        # 加载已有版本
        self._load_versions()
    
    def _load_versions(self) -> None:
        """加载已有版本信息"""
        versions_file = self.model_dir / "versions.json"
        if versions_file.exists():
            with open(versions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for v_data in data.get("versions", []):
                    version = self._dict_to_version(v_data)
                    self.versions[version.version_id] = version
                self.active_version = data.get("active_version")
    
    def _save_versions(self) -> None:
        """保存版本信息"""
        versions_file = self.model_dir / "versions.json"
        data = {
            "versions": [v.to_dict() for v in self.versions.values()],
            "active_version": self.active_version,
        }
        with open(versions_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _dict_to_version(self, data: Dict[str, Any]) -> ModelVersion:
        """字典转换为版本对象"""
        performance = ModelPerformance(
            accuracy=data.get("performance", {}).get("accuracy", 0.0),
            precision=data.get("performance", {}).get("precision", 0.0),
            recall=data.get("performance", {}).get("recall", 0.0),
            f1_score=data.get("performance", {}).get("f1_score", 0.0),
            mse=data.get("performance", {}).get("mse", 0.0),
            rmse=data.get("performance", {}).get("rmse", 0.0),
            mae=data.get("performance", {}).get("mae", 0.0),
            r2_score=data.get("performance", {}).get("r2_score", 0.0),
            train_samples=data.get("performance", {}).get("train_samples", 0),
            test_samples=data.get("performance", {}).get("test_samples", 0),
        )
        
        return ModelVersion(
            version_id=data["version_id"],
            model_name=data["model_name"],
            model_type=ModelType(data["model_type"]),
            version_number=data["version_number"],
            parent_version=data.get("parent_version"),
            status=ModelStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            activated_at=datetime.fromisoformat(data["activated_at"]) if data.get("activated_at") else None,
            deprecated_at=datetime.fromisoformat(data["deprecated_at"]) if data.get("deprecated_at") else None,
            performance=performance,
            hyperparameters=data.get("hyperparameters", {}),
            feature_names=data.get("feature_names", []),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            model_path=data.get("model_path"),
        )
    
    def register_version(
        self,
        model: Any,
        hyperparameters: Dict[str, Any],
        feature_names: List[str],
        description: str = "",
        tags: Optional[List[str]] = None,
        parent_version: Optional[str] = None,
    ) -> ModelVersion:
        """
        注册新版本
        
        Args:
            model: 模型对象
            hyperparameters: 超参数
            feature_names: 特征名称列表
            description: 版本描述
            tags: 标签
            parent_version: 父版本ID
            
        Returns:
            新版本信息
        """
        # 计算版本号
        version_number = 1
        if parent_version and parent_version in self.versions:
            version_number = self.versions[parent_version].version_number + 1
        elif self.versions:
            version_number = max(v.version_number for v in self.versions.values()) + 1
        
        # 创建版本
        version = ModelVersion(
            model_name=self.model_name,
            model_type=self.model_type,
            version_number=version_number,
            parent_version=parent_version,
            hyperparameters=hyperparameters,
            feature_names=feature_names,
            description=description,
            tags=tags or [],
        )
        
        # 保存模型
        model_path = self.model_dir / f"model_{version.version_id}.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        version.model_path = str(model_path)
        
        # 注册版本
        self.versions[version.version_id] = version
        self._save_versions()
        
        return version
    
    def evaluate_version(
        self,
        version_id: str,
        X_test: np.ndarray,
        y_test: np.ndarray,
        metrics_fn: Optional[Callable] = None,
    ) -> ModelPerformance:
        """
        评估模型版本
        
        Args:
            version_id: 版本ID
            X_test: 测试特征
            y_test: 测试标签
            metrics_fn: 自定义评估函数
            
        Returns:
            性能指标
        """
        if version_id not in self.versions:
            raise ValueError(f"版本 {version_id} 不存在")
        
        version = self.versions[version_id]
        model = self.load_model(version_id)
        
        # 预测
        y_pred = model.predict(X_test)
        
        # 计算性能指标
        if metrics_fn:
            performance = metrics_fn(y_test, y_pred)
        else:
            performance = self._calculate_metrics(y_test, y_pred)
        
        performance.test_samples = len(y_test)
        
        # 更新版本
        version.performance = performance
        version.status = ModelStatus.ACTIVE
        version.activated_at = datetime.now()
        self._save_versions()
        
        return performance
    
    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> ModelPerformance:
        """计算性能指标"""
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score, f1_score,
            mean_squared_error, mean_absolute_error, r2_score
        )
        
        perf = ModelPerformance()
        
        # 判断任务类型
        if len(np.unique(y_true)) <= 10:  # 分类任务
            perf.accuracy = accuracy_score(y_true, y_pred)
            perf.precision = precision_score(y_true, y_pred, average='weighted', zero_division=0)
            perf.recall = recall_score(y_true, y_pred, average='weighted', zero_division=0)
            perf.f1_score = f1_score(y_true, y_pred, average='weighted', zero_division=0)
        else:  # 回归任务
            perf.mse = mean_squared_error(y_true, y_pred)
            perf.rmse = np.sqrt(perf.mse)
            perf.mae = mean_absolute_error(y_true, y_pred)
            perf.r2_score = r2_score(y_true, y_pred)
        
        return perf
    
    def activate_version(self, version_id: str) -> None:
        """
        激活版本
        
        Args:
            version_id: 版本ID
        """
        if version_id not in self.versions:
            raise ValueError(f"版本 {version_id} 不存在")
        
        # 废弃旧版本
        if self.active_version and self.active_version in self.versions:
            old_version = self.versions[self.active_version]
            old_version.status = ModelStatus.DEPRECATED
            old_version.deprecated_at = datetime.now()
        
        # 激活新版本
        version = self.versions[version_id]
        version.status = ModelStatus.ACTIVE
        version.activated_at = datetime.now()
        self.active_version = version_id
        
        self._save_versions()
    
    def load_model(self, version_id: Optional[str] = None) -> Any:
        """
        加载模型
        
        Args:
            version_id: 版本ID，None则加载活跃版本
            
        Returns:
            模型对象
        """
        if version_id is None:
            version_id = self.active_version
        
        if version_id is None or version_id not in self.versions:
            raise ValueError(f"版本 {version_id} 不存在")
        
        version = self.versions[version_id]
        if not version.model_path:
            raise ValueError(f"版本 {version_id} 没有模型文件")
        
        with open(version.model_path, 'rb') as f:
            return pickle.load(f)
    
    def predict(
        self,
        X: np.ndarray,
        version_id: Optional[str] = None,
        record: bool = True,
    ) -> np.ndarray:
        """
        预测
        
        Args:
            X: 输入特征
            version_id: 版本ID，None则使用活跃版本
            record: 是否记录预测历史
            
        Returns:
            预测结果
        """
        # A/B测试模式
        if self.ab_test_versions and not version_id:
            version_id = self._select_ab_version()
        
        model = self.load_model(version_id)
        predictions = model.predict(X)
        
        if record:
            self.prediction_history.append({
                "version_id": version_id or self.active_version,
                "timestamp": datetime.now().isoformat(),
                "input_shape": X.shape,
            })
        
        return predictions
    
    def _select_ab_version(self) -> str:
        """A/B测试版本选择"""
        if not self.ab_test_versions:
            return self.active_version
        
        # 根据权重随机选择
        versions = self.ab_test_versions
        weights = [self.ab_test_weights.get(v, 1.0) for v in versions]
        total = sum(weights)
        probs = [w / total for w in weights]
        
        return np.random.choice(versions, p=probs)
    
    def start_ab_test(
        self,
        version_ids: List[str],
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        启动A/B测试
        
        Args:
            version_ids: 版本ID列表
            weights: 版本权重
        """
        for vid in version_ids:
            if vid not in self.versions:
                raise ValueError(f"版本 {vid} 不存在")
        
        self.ab_test_versions = version_ids
        self.ab_test_weights = weights or {v: 1.0 for v in version_ids}
    
    def stop_ab_test(self, winning_version: Optional[str] = None) -> None:
        """
        停止A/B测试
        
        Args:
            winning_version: 获胜版本ID
        """
        if winning_version:
            self.activate_version(winning_version)
        
        self.ab_test_versions = []
        self.ab_test_weights = {}
    
    def record_accuracy(
        self,
        version_id: str,
        actual: np.ndarray,
        predicted: np.ndarray,
    ) -> float:
        """
        记录实际准确率
        
        Args:
            version_id: 版本ID
            actual: 实际值
            predicted: 预测值
            
        Returns:
            当前准确率
        """
        # 计算准确率
        if self.model_type == ModelType.CLASSIFICATION:
            accuracy = np.mean(actual == predicted)
        else:
            # 回归任务使用R²
            ss_res = np.sum((actual - predicted) ** 2)
            ss_tot = np.sum((actual - np.mean(actual)) ** 2)
            accuracy = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        # 记录
        self.accuracy_history.append({
            "version_id": version_id,
            "timestamp": datetime.now().isoformat(),
            "accuracy": accuracy,
        })
        
        # 检查是否需要重训练
        self._check_retrain_trigger(version_id, accuracy)
        
        return accuracy
    
    def _check_retrain_trigger(self, version_id: str, current_accuracy: float) -> None:
        """检查是否触发重训练"""
        if not self.retrain_config.enabled:
            return
        
        if version_id not in self.versions:
            return
        
        version = self.versions[version_id]
        baseline_accuracy = version.performance.accuracy
        
        if baseline_accuracy > 0:
            accuracy_drop = (baseline_accuracy - current_accuracy) / baseline_accuracy
            
            if accuracy_drop >= self.retrain_config.accuracy_drop_threshold:
                self._trigger_retrain(version_id, accuracy_drop)
    
    def _trigger_retrain(self, version_id: str, accuracy_drop: float) -> None:
        """触发重训练"""
        if self._retrain_callback:
            self._retrain_callback(
                model_name=self.model_name,
                version_id=version_id,
                accuracy_drop=accuracy_drop,
                triggered_at=datetime.now(),
            )
    
    def on_retrain(self, callback: Callable) -> None:
        """
        注册重训练回调
        
        Args:
            callback: 回调函数
        """
        self._retrain_callback = callback
    
    def on_performance_drop(self, callback: Callable) -> None:
        """
        注册性能下降回调
        
        Args:
            callback: 回调函数
        """
        self._performance_callback = callback
    
    def get_version_history(self) -> pd.DataFrame:
        """获取版本历史"""
        if not self.versions:
            return pd.DataFrame()
        
        data = [v.to_dict() for v in self.versions.values()]
        return pd.DataFrame(data)
    
    def get_performance_trend(self, days: int = 30) -> pd.DataFrame:
        """
        获取性能趋势
        
        Args:
            days: 天数
            
        Returns:
            性能趋势DataFrame
        """
        if not self.accuracy_history:
            return pd.DataFrame()
        
        cutoff = datetime.now() - timedelta(days=days)
        recent = [
            h for h in self.accuracy_history
            if datetime.fromisoformat(h["timestamp"]) >= cutoff
        ]
        
        return pd.DataFrame(recent)
    
    def get_best_version(self, metric: str = "accuracy") -> Optional[ModelVersion]:
        """
        获取最佳版本
        
        Args:
            metric: 评估指标
            
        Returns:
            最佳版本
        """
        active_versions = [
            v for v in self.versions.values()
            if v.status == ModelStatus.ACTIVE
        ]
        
        if not active_versions:
            return None
        
        return max(
            active_versions,
            key=lambda v: getattr(v.performance, metric, 0.0)
        )
    
    def compare_versions(
        self,
        version_ids: List[str],
        metrics: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        对比多个版本
        
        Args:
            version_ids: 版本ID列表
            metrics: 指标列表
            
        Returns:
            对比结果DataFrame
        """
        metrics = metrics or ["accuracy", "precision", "recall", "f1_score"]
        
        data = []
        for vid in version_ids:
            if vid in self.versions:
                v = self.versions[vid]
                row = {"version_id": vid, "version_number": v.version_number}
                for m in metrics:
                    row[m] = getattr(v.performance, m, 0.0)
                data.append(row)
        
        return pd.DataFrame(data)
    
    def delete_version(self, version_id: str) -> None:
        """
        删除版本
        
        Args:
            version_id: 版本ID
        """
        if version_id not in self.versions:
            raise ValueError(f"版本 {version_id} 不存在")
        
        if version_id == self.active_version:
            raise ValueError("不能删除活跃版本")
        
        version = self.versions[version_id]
        
        # 删除模型文件
        if version.model_path and Path(version.model_path).exists():
            Path(version.model_path).unlink()
        
        # 删除版本记录
        del self.versions[version_id]
        self._save_versions()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "model_name": self.model_name,
            "model_type": self.model_type.value,
            "total_versions": len(self.versions),
            "active_version": self.active_version,
            "ab_test_active": len(self.ab_test_versions) > 0,
            "ab_test_versions": self.ab_test_versions,
            "prediction_count": len(self.prediction_history),
            "accuracy_records": len(self.accuracy_history),
        }
