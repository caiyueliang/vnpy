"""
经验库系统

积累交易经验和最佳实践，支持知识复用
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import re


@dataclass
class ExperienceEntry:
    """经验条目"""
    # 基本信息
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 内容
    title: str = ""
    content: str = ""
    category: str = "general"  # general, strategy, risk, execution, data
    
    # 标签
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # 上下文
    strategy_name: Optional[str] = None
    vt_symbol: Optional[str] = None
    market_condition: Optional[str] = None  # 牛市、熊市、震荡
    
    # 效果评估
    effectiveness: Optional[float] = None  # 0-1
    usage_count: int = 0
    
    # 来源
    source: str = "manual"  # manual, auto_extract, best_practice
    author: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "entry_id": self.entry_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "tags": self.tags,
            "keywords": self.keywords,
            "strategy_name": self.strategy_name,
            "vt_symbol": self.vt_symbol,
            "market_condition": self.market_condition,
            "effectiveness": self.effectiveness,
            "usage_count": self.usage_count,
            "source": self.source,
            "author": self.author,
        }


class ExperienceBase:
    """
    经验库
    
    功能：
    1. 经验记录和管理
    2. 智能搜索和推荐
    3. 经验效果跟踪
    4. 知识共享和复用
    """
    
    def __init__(self, storage_path: str = "./knowledge/experience") -> None:
        """
        Constructor
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 经验条目
        self.entries: Dict[str, ExperienceEntry] = {}
        
        # 索引
        self._tag_index: Dict[str, List[str]] = {}
        self._keyword_index: Dict[str, List[str]] = {}
        self._category_index: Dict[str, List[str]] = {}
        
        # 加载经验
        self._load_entries()
    
    def _load_entries(self) -> None:
        """加载经验条目"""
        entries_file = self.storage_path / "experience.json"
        if entries_file.exists():
            try:
                with open(entries_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for entry_data in data:
                        entry = ExperienceEntry(
                            entry_id=entry_data["entry_id"],
                            created_at=datetime.fromisoformat(entry_data["created_at"]),
                            updated_at=datetime.fromisoformat(entry_data["updated_at"]),
                            title=entry_data["title"],
                            content=entry_data["content"],
                            category=entry_data["category"],
                            tags=entry_data.get("tags", []),
                            keywords=entry_data.get("keywords", []),
                            strategy_name=entry_data.get("strategy_name"),
                            vt_symbol=entry_data.get("vt_symbol"),
                            market_condition=entry_data.get("market_condition"),
                            effectiveness=entry_data.get("effectiveness"),
                            usage_count=entry_data.get("usage_count", 0),
                            source=entry_data.get("source", "manual"),
                            author=entry_data.get("author"),
                        )
                        self.entries[entry.entry_id] = entry
                        self._update_index(entry)
            except Exception as e:
                print(f"加载经验库失败: {e}")
    
    def _save_entries(self) -> None:
        """保存经验条目"""
        entries_file = self.storage_path / "experience.json"
        try:
            data = [entry.to_dict() for entry in self.entries.values()]
            with open(entries_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"保存经验库失败: {e}")
    
    def _update_index(self, entry: ExperienceEntry) -> None:
        """更新索引"""
        # 标签索引
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if entry.entry_id not in self._tag_index[tag]:
                self._tag_index[tag].append(entry.entry_id)
        
        # 关键词索引
        for keyword in entry.keywords:
            if keyword not in self._keyword_index:
                self._keyword_index[keyword] = []
            if entry.entry_id not in self._keyword_index[keyword]:
                self._keyword_index[keyword].append(entry.entry_id)
        
        # 分类索引
        if entry.category not in self._category_index:
            self._category_index[entry.category] = []
        if entry.entry_id not in self._category_index[entry.category]:
            self._category_index[entry.category].append(entry.entry_id)
    
    def add_experience(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        strategy_name: Optional[str] = None,
        vt_symbol: Optional[str] = None,
        market_condition: Optional[str] = None,
        source: str = "manual",
        author: Optional[str] = None,
    ) -> ExperienceEntry:
        """
        添加经验
        
        Args:
            title: 标题
            content: 内容
            category: 分类
            tags: 标签
            keywords: 关键词
            strategy_name: 策略名称
            vt_symbol: 合约代码
            market_condition: 市场状况
            source: 来源
            author: 作者
            
        Returns:
            经验条目
        """
        entry = ExperienceEntry(
            title=title,
            content=content,
            category=category,
            tags=tags or [],
            keywords=keywords or self._extract_keywords(content),
            strategy_name=strategy_name,
            vt_symbol=vt_symbol,
            market_condition=market_condition,
            source=source,
            author=author,
        )
        
        self.entries[entry.entry_id] = entry
        self._update_index(entry)
        self._save_entries()
        
        return entry
    
    def _extract_keywords(self, content: str, max_keywords: int = 5) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取：提取长度大于2的词
        words = re.findall(r'\b[a-zA-Z\u4e00-\u9fa5]{2,}\b', content)
        
        # 统计词频
        word_freq = {}
        for word in words:
            word_lower = word.lower()
            word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
        
        # 返回最常见的词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:max_keywords]]
    
    def update_experience(
        self,
        entry_id: str,
        **kwargs
    ) -> Optional[ExperienceEntry]:
        """
        更新经验
        
        Args:
            entry_id: 条目ID
            **kwargs: 更新字段
            
        Returns:
            更新后的条目
        """
        if entry_id not in self.entries:
            return None
        
        entry = self.entries[entry_id]
        
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        
        entry.updated_at = datetime.now()
        
        self._save_entries()
        
        return entry
    
    def record_usage(self, entry_id: str, effectiveness: Optional[float] = None) -> None:
        """
        记录经验使用
        
        Args:
            entry_id: 条目ID
            effectiveness: 效果评分
        """
        if entry_id not in self.entries:
            return
        
        entry = self.entries[entry_id]
        entry.usage_count += 1
        
        if effectiveness is not None:
            # 更新平均效果
            if entry.effectiveness is None:
                entry.effectiveness = effectiveness
            else:
                # 加权平均
                entry.effectiveness = (
                    entry.effectiveness * (entry.usage_count - 1) + effectiveness
                ) / entry.usage_count
        
        self._save_entries()
    
    def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        strategy_name: Optional[str] = None,
        vt_symbol: Optional[str] = None,
        market_condition: Optional[str] = None,
        limit: int = 10,
    ) -> List[ExperienceEntry]:
        """
        搜索经验
        
        Args:
            query: 搜索关键词
            category: 分类
            tags: 标签
            strategy_name: 策略名称
            vt_symbol: 合约代码
            market_condition: 市场状况
            limit: 限制数量
            
        Returns:
            经验条目列表
        """
        results = list(self.entries.values())
        
        # 分类过滤
        if category:
            results = [e for e in results if e.category == category]
        
        # 标签过滤
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        
        # 策略过滤
        if strategy_name:
            results = [e for e in results if e.strategy_name == strategy_name]
        
        # 合约过滤
        if vt_symbol:
            results = [e for e in results if e.vt_symbol == vt_symbol]
        
        # 市场状况过滤
        if market_condition:
            results = [e for e in results if e.market_condition == market_condition]
        
        # 关键词搜索
        if query:
            query_lower = query.lower()
            scored_results = []
            
            for entry in results:
                score = 0
                
                # 标题匹配
                if query_lower in entry.title.lower():
                    score += 10
                
                # 内容匹配
                if query_lower in entry.content.lower():
                    score += 5
                
                # 关键词匹配
                if any(query_lower in kw.lower() for kw in entry.keywords):
                    score += 3
                
                # 标签匹配
                if any(query_lower in tag.lower() for tag in entry.tags):
                    score += 2
                
                if score > 0:
                    scored_results.append((entry, score))
            
            # 按分数排序
            scored_results.sort(key=lambda x: x[1], reverse=True)
            results = [e for e, _ in scored_results]
        else:
            # 按使用次数和效果排序
            results.sort(
                key=lambda e: (e.usage_count, e.effectiveness or 0),
                reverse=True
            )
        
        return results[:limit]
    
    def get_recommendations(
        self,
        context: Dict[str, Any],
        limit: int = 5,
    ) -> List[ExperienceEntry]:
        """
        获取推荐经验
        
        Args:
            context: 上下文信息
            limit: 限制数量
            
        Returns:
            推荐的经验条目
        """
        results = list(self.entries.values())
        scored_results = []
        
        for entry in results:
            score = 0
            
            # 策略匹配
            if context.get("strategy_name") and entry.strategy_name == context["strategy_name"]:
                score += 10
            
            # 合约匹配
            if context.get("vt_symbol") and entry.vt_symbol == context["vt_symbol"]:
                score += 8
            
            # 市场状况匹配
            if context.get("market_condition") and entry.market_condition == context["market_condition"]:
                score += 6
            
            # 效果评分
            if entry.effectiveness:
                score += entry.effectiveness * 5
            
            # 使用次数
            score += min(entry.usage_count * 0.5, 5)
            
            scored_results.append((entry, score))
        
        # 排序
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        return [e for e, _ in scored_results[:limit]]
    
    def get_best_practices(self, category: Optional[str] = None) -> List[ExperienceEntry]:
        """
        获取最佳实践
        
        Args:
            category: 分类
            
        Returns:
            最佳实践列表
        """
        results = list(self.entries.values())
        
        if category:
            results = [e for e in results if e.category == category]
        
        # 筛选高效果的经验
        best = [e for e in results if e.effectiveness and e.effectiveness >= 0.8]
        
        # 按效果排序
        best.sort(key=lambda e: (e.effectiveness or 0, e.usage_count), reverse=True)
        
        return best
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self.entries)
        
        # 按分类统计
        category_counts = {}
        for entry in self.entries.values():
            category_counts[entry.category] = category_counts.get(entry.category, 0) + 1
        
        # 按来源统计
        source_counts = {}
        for entry in self.entries.values():
            source_counts[entry.source] = source_counts.get(entry.source, 0) + 1
        
        # 效果统计
        effectiveness_values = [
            e.effectiveness for e in self.entries.values()
            if e.effectiveness is not None
        ]
        
        return {
            "total_entries": total,
            "by_category": category_counts,
            "by_source": source_counts,
            "avg_effectiveness": sum(effectiveness_values) / len(effectiveness_values) if effectiveness_values else 0,
            "total_usage": sum(e.usage_count for e in self.entries.values()),
        }
    
    def export_to_file(self, filepath: str) -> None:
        """
        导出经验库
        
        Args:
            filepath: 文件路径
        """
        data = {
            "exported_at": datetime.now().isoformat(),
            "stats": self.get_stats(),
            "entries": [entry.to_dict() for entry in self.entries.values()],
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def import_from_file(self, filepath: str) -> int:
        """
        导入经验库
        
        Args:
            filepath: 文件路径
            
        Returns:
            导入数量
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        count = 0
        for entry_data in data.get("entries", []):
            entry = ExperienceEntry(
                entry_id=entry_data["entry_id"],
                created_at=datetime.fromisoformat(entry_data["created_at"]),
                updated_at=datetime.fromisoformat(entry_data["updated_at"]),
                title=entry_data["title"],
                content=entry_data["content"],
                category=entry_data["category"],
                tags=entry_data.get("tags", []),
                keywords=entry_data.get("keywords", []),
                strategy_name=entry_data.get("strategy_name"),
                vt_symbol=entry_data.get("vt_symbol"),
                market_condition=entry_data.get("market_condition"),
                effectiveness=entry_data.get("effectiveness"),
                usage_count=entry_data.get("usage_count", 0),
                source=entry_data.get("source", "manual"),
                author=entry_data.get("author"),
            )
            
            if entry.entry_id not in self.entries:
                self.entries[entry.entry_id] = entry
                self._update_index(entry)
                count += 1
        
        self._save_entries()
        return count
    
    def delete_entry(self, entry_id: str) -> bool:
        """
        删除经验条目
        
        Args:
            entry_id: 条目ID
            
        Returns:
            是否成功
        """
        if entry_id not in self.entries:
            return False
        
        del self.entries[entry_id]
        
        # 重建索引
        self._tag_index.clear()
        self._keyword_index.clear()
        self._category_index.clear()
        
        for entry in self.entries.values():
            self._update_index(entry)
        
        self._save_entries()
        return True
