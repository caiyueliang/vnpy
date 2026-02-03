"""
因子基础模块

定义因子的抽象基类和注册表。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np


@dataclass
class FactorResult:
    """因子计算结果"""
    name: str
    values: pd.Series
    timestamp: datetime
    metadata: Dict[str, Any]


class Factor(ABC):
    """
    因子抽象基类

    所有因子必须继承此类并实现calculate方法。
    """

    def __init__(self, name: str, description: str = ""):
        """
        初始化因子

        Args:
            name: 因子名称
            description: 因子描述
        """
        self.name = name
        self.description = description
        self.params: Dict[str, Any] = {}
        self._cache: Dict[str, pd.Series] = {}

    @abstractmethod
    def calculate(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        计算因子值

        Args:
            data: 输入数据，包含OHLCV等
            **kwargs: 额外参数

        Returns:
            因子值序列
        """
        pass

    def set_params(self, **params) -> 'Factor':
        """
        设置因子参数

        Args:
            **params: 参数键值对

        Returns:
            self，支持链式调用
        """
        self.params.update(params)
        return self

    def get_params(self) -> Dict[str, Any]:
        """
        获取当前参数

        Returns:
            参数字典
        """
        return self.params.copy()

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def _get_from_cache(self, key: str) -> Optional[pd.Series]:
        """从缓存获取"""
        return self._cache.get(key)

    def _set_to_cache(self, key: str, value: pd.Series) -> None:
        """设置缓存"""
        self._cache[key] = value

    def __call__(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        """
        调用因子计算

        Args:
            data: 输入数据
            **kwargs: 额外参数

        Returns:
            因子计算结果
        """
        values = self.calculate(data, **kwargs)

        return FactorResult(
            name=self.name,
            values=values,
            timestamp=datetime.now(),
            metadata={
                'params': self.params.copy(),
                'description': self.description
            }
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class FactorRegistry:
    """
    因子注册表

    管理所有可用的因子，支持按类别查找。
    """

    def __init__(self):
        self._factors: Dict[str, Factor] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, factor: Factor, category: str = "default") -> None:
        """
        注册因子

        Args:
            factor: 因子实例
            category: 因子类别
        """
        self._factors[factor.name] = factor

        if category not in self._categories:
            self._categories[category] = []

        if factor.name not in self._categories[category]:
            self._categories[category].append(factor.name)

    def unregister(self, name: str) -> None:
        """
        注销因子

        Args:
            name: 因子名称
        """
        if name in self._factors:
            del self._factors[name]

            # 从类别中移除
            for category in self._categories:
                if name in self._categories[category]:
                    self._categories[category].remove(name)

    def get(self, name: str) -> Optional[Factor]:
        """
        获取因子

        Args:
            name: 因子名称

        Returns:
            因子实例或None
        """
        return self._factors.get(name)

    def list_factors(self, category: Optional[str] = None) -> List[str]:
        """
        列出因子

        Args:
            category: 类别筛选，None表示所有

        Returns:
            因子名称列表
        """
        if category is None:
            return list(self._factors.keys())

        return self._categories.get(category, [])

    def list_categories(self) -> List[str]:
        """
        列出所有类别

        Returns:
            类别列表
        """
        return list(self._categories.keys())

    def get_factors_by_category(self, category: str) -> Dict[str, Factor]:
        """
        按类别获取因子

        Args:
            category: 因子类别

        Returns:
            因子字典
        """
        names = self._categories.get(category, [])
        return {name: self._factors[name] for name in names if name in self._factors}

    def clear(self) -> None:
        """清空所有因子"""
        self._factors.clear()
        self._categories.clear()


# 全局因子注册表
_global_registry = FactorRegistry()


def register_factor(factor: Factor, category: str = "default") -> None:
    """
    注册因子到全局注册表

    Args:
        factor: 因子实例
        category: 因子类别
    """
    _global_registry.register(factor, category)


def get_factor(name: str) -> Optional[Factor]:
    """
    从全局注册表获取因子

    Args:
        name: 因子名称

    Returns:
        因子实例或None
    """
    return _global_registry.get(name)


def list_all_factors() -> List[str]:
    """
    列出所有已注册因子

    Returns:
        因子名称列表
    """
    return _global_registry.list_factors()
