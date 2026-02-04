"""
模型注册中心

统一管理所有机器学习模型，提供全局模型发现和访问能力
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

from .model_manager import ModelManager, ModelType


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    model_type: ModelType
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    active_version: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelRegistry:
    """
    模型注册中心
    
    统一管理所有模型，提供：
    1. 模型注册和发现
    2. 全局模型管理
    3. 模型依赖关系管理
    """
    
    _instance: Optional['ModelRegistry'] = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        storage_path: str = "./models/registry",
    ) -> None:
        """
        Constructor
        
        Args:
            storage_path: 注册中心存储路径
        """
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 模型管理器缓存
        self._managers: Dict[str, ModelManager] = {}
        self._model_infos: Dict[str, ModelInfo] = {}
        
        # 模型依赖关系
        self._dependencies: Dict[str, List[str]] = {}
        
        # 加载注册信息
        self._load_registry()
    
    def _load_registry(self) -> None:
        """加载注册信息"""
        registry_file = self.storage_path / "registry.json"
        if registry_file.exists():
            with open(registry_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for name, info_data in data.get("models", {}).items():
                    self._model_infos[name] = ModelInfo(
                        name=info_data["name"],
                        model_type=ModelType(info_data["model_type"]),
                        description=info_data.get("description", ""),
                        created_at=datetime.fromisoformat(info_data["created_at"]),
                        active_version=info_data.get("active_version"),
                        tags=info_data.get("tags", []),
                        metadata=info_data.get("metadata", {}),
                    )
                self._dependencies = data.get("dependencies", {})
    
    def _save_registry(self) -> None:
        """保存注册信息"""
        registry_file = self.storage_path / "registry.json"
        data = {
            "models": {
                name: {
                    "name": info.name,
                    "model_type": info.model_type.value,
                    "description": info.description,
                    "created_at": info.created_at.isoformat(),
                    "active_version": info.active_version,
                    "tags": info.tags,
                    "metadata": info.metadata,
                }
                for name, info in self._model_infos.items()
            },
            "dependencies": self._dependencies,
        }
        with open(registry_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def register_model(
        self,
        model_name: str,
        model_type: ModelType,
        description: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ModelManager:
        """
        注册新模型
        
        Args:
            model_name: 模型名称
            model_type: 模型类型
            description: 描述
            tags: 标签
            metadata: 元数据
            
        Returns:
            模型管理器
        """
        if model_name in self._managers:
            return self._managers[model_name]
        
        # 创建模型管理器
        manager = ModelManager(
            model_name=model_name,
            model_type=model_type,
            storage_path=str(self.storage_path.parent),
        )
        
        # 注册信息
        self._managers[model_name] = manager
        self._model_infos[model_name] = ModelInfo(
            name=model_name,
            model_type=model_type,
            description=description,
            tags=tags or [],
            metadata=metadata or {},
        )
        
        self._save_registry()
        
        return manager
    
    def get_manager(self, model_name: str) -> Optional[ModelManager]:
        """
        获取模型管理器
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型管理器
        """
        if model_name not in self._managers:
            if model_name in self._model_infos:
                # 延迟加载
                info = self._model_infos[model_name]
                self._managers[model_name] = ModelManager(
                    model_name=model_name,
                    model_type=info.model_type,
                    storage_path=str(self.storage_path.parent),
                )
        
        return self._managers.get(model_name)
    
    def list_models(
        self,
        model_type: Optional[ModelType] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ModelInfo]:
        """
        列出模型
        
        Args:
            model_type: 模型类型过滤
            tags: 标签过滤
            
        Returns:
            模型信息列表
        """
        results = list(self._model_infos.values())
        
        if model_type:
            results = [m for m in results if m.model_type == model_type]
        
        if tags:
            results = [m for m in results if any(t in m.tags for t in tags)]
        
        return results
    
    def add_dependency(self, model_name: str, depends_on: str) -> None:
        """
        添加模型依赖
        
        Args:
            model_name: 模型名称
            depends_on: 依赖的模型名称
        """
        if model_name not in self._dependencies:
            self._dependencies[model_name] = []
        
        if depends_on not in self._dependencies[model_name]:
            self._dependencies[model_name].append(depends_on)
            self._save_registry()
    
    def get_dependencies(self, model_name: str) -> List[str]:
        """
        获取模型依赖
        
        Args:
            model_name: 模型名称
            
        Returns:
            依赖列表
        """
        return self._dependencies.get(model_name, [])
    
    def get_dependents(self, model_name: str) -> List[str]:
        """
        获取依赖该模型的其他模型
        
        Args:
            model_name: 模型名称
            
        Returns:
            依赖该模型的模型列表
        """
        return [
            name for name, deps in self._dependencies.items()
            if model_name in deps
        ]
    
    def delete_model(self, model_name: str) -> None:
        """
        删除模型
        
        Args:
            model_name: 模型名称
        """
        if model_name not in self._model_infos:
            return
        
        # 检查是否有其他模型依赖
        dependents = self.get_dependents(model_name)
        if dependents:
            raise ValueError(f"模型 {model_name} 被以下模型依赖: {dependents}")
        
        # 删除管理器
        if model_name in self._managers:
            del self._managers[model_name]
        
        # 删除注册信息
        del self._model_infos[model_name]
        if model_name in self._dependencies:
            del self._dependencies[model_name]
        
        self._save_registry()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_models": len(self._model_infos),
            "model_types": {
                model_type.value: sum(
                    1 for info in self._model_infos.values()
                    if info.model_type == model_type
                )
                for model_type in ModelType
            },
            "models": [
                {
                    "name": info.name,
                    "type": info.model_type.value,
                    "versions": len(self.get_manager(info.name).versions) if self.get_manager(info.name) else 0,
                    "active_version": info.active_version,
                }
                for info in self._model_infos.values()
            ],
        }


# 全局注册中心实例
_registry: Optional[ModelRegistry] = None


def get_model_registry(storage_path: str = "./models/registry") -> ModelRegistry:
    """
    获取全局模型注册中心
    
    Args:
        storage_path: 存储路径
        
    Returns:
        模型注册中心
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry(storage_path)
    return _registry
