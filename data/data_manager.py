"""
数据管理器 - 数据层核心模块

实现数据获取、缓存、持久化功能，与策略层完全分离
"""

import os
import pickle
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

import pandas as pd

from data.collectors.akshare_collector import AKShareCollector
from data.collectors.tushare_collector import TushareCollector
from data.collectors.base import DataSource, CollectorConfig
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval


class DataManager:
    """
    数据管理器
    
    功能：
    1. 数据获取（支持多数据源）
    2. 数据缓存（避免重复下载）
    3. 数据持久化（本地存储）
    4. 重试机制（处理网络问题）
    """
    
    def __init__(self, cache_dir: str = "data/cache"):
        """Constructor"""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据源优先级
        self.data_sources = [
            DataSource.AKSHARE,
            DataSource.TUSHARE,
        ]
        
        # 数据源实例
        self.collectors = {}
        
        # 缓存过期时间（天）
        self.cache_expiry = 7
        
    def _get_collector(self, source: DataSource):
        """获取数据采集器实例"""
        if source not in self.collectors:
            config = CollectorConfig(source=source)
            if source == DataSource.AKSHARE:
                self.collectors[source] = AKShareCollector(config)
            elif source == DataSource.TUSHARE:
                self.collectors[source] = TushareCollector(config)
        
        return self.collectors[source]
    
    def _get_cache_path(self, symbol: str, start_date: datetime, end_date: datetime) -> Path:
        """获取缓存文件路径"""
        cache_key = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.pkl"
        return self.cache_dir / cache_key
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """检查缓存是否有效"""
        if not cache_path.exists():
            return False
        
        # 检查缓存文件年龄
        file_age = time.time() - cache_path.stat().st_mtime
        return file_age < self.cache_expiry * 86400  # 转换为秒
    
    def _load_from_cache(self, cache_path: Path) -> Optional[List[BarData]]:
        """从缓存加载数据"""
        try:
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"加载缓存失败: {e}")
            return None
    
    def _save_to_cache(self, cache_path: Path, bars: List[BarData]):
        """保存数据到缓存"""
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(bars, f)
        except Exception as e:
            print(f"保存缓存失败: {e}")
    
    def get_stock_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "d",
        use_cache: bool = True,
        max_retries: int = 3
    ) -> List[BarData]:
        """
        获取股票数据
        
        Args:
            symbol: 股票代码（如 "600519.SH"）
            start_date: 开始日期
            end_date: 结束日期
            interval: 数据周期
            use_cache: 是否使用缓存
            max_retries: 最大重试次数
        
        Returns:
            K线数据列表
        """
        # 1. 尝试从缓存加载
        if use_cache:
            cache_path = self._get_cache_path(symbol, start_date, end_date)
            if self._is_cache_valid(cache_path):
                cached_data = self._load_from_cache(cache_path)
                if cached_data:
                    print(f"[缓存] {symbol} 从缓存加载")
                    return cached_data
        
        # 2. 从数据源获取
        for source in self.data_sources:
            collector = self._get_collector(source)
            
            if not collector.connect():
                print(f"[{source.value}] 连接失败，尝试下一个数据源")
                continue
            
            print(f"[{source.value}] 开始获取 {symbol} 数据...")
            
            # 重试机制
            for retry in range(max_retries):
                try:
                    bars_dict = collector.get_bar_data(symbol, interval, start_date, end_date)
                    
                    if bars_dict and len(bars_dict) > 50:
                        # 转换为BarData对象
                        bars = self._convert_to_bars(bars_dict, symbol)
                        
                        # 保存到缓存
                        if use_cache:
                            cache_path = self._get_cache_path(symbol, start_date, end_date)
                            self._save_to_cache(cache_path, bars)
                        
                        print(f"[{source.value}] {symbol} 获取成功: {len(bars)}条")
                        return bars
                    else:
                        print(f"[{source.value}] {symbol} 数据不足: {len(bars_dict) if bars_dict else 0}条")
                        break
                        
                except Exception as e:
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 2
                        print(f"[{source.value}] 获取失败，{wait_time}秒后重试 ({retry+1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        print(f"[{source.value}] {symbol} 获取失败: {e}")
            
            collector.disconnect()
        
        print(f"[失败] {symbol} 所有数据源均获取失败")
        return []
    
    def _convert_to_bars(self, bars_dict: List[dict], symbol: str) -> List[BarData]:
        """转换为BarData对象"""
        bars = []
        
        # 解析交易所
        if ".SH" in symbol:
            exchange = Exchange.SSE
        elif ".SZ" in symbol:
            exchange = Exchange.SZSE
        else:
            exchange = Exchange.SZSE
        
        # 生成正确的vt_symbol
        if ".SH" in symbol:
            vt_symbol = symbol.replace(".SH", ".SSE")
        elif ".SZ" in symbol:
            vt_symbol = symbol.replace(".SZ", ".SZSE")
        else:
            vt_symbol = symbol + ".SZSE"
        
        for bar_dict in bars_dict:
            bar = BarData(
                symbol=symbol.split(".")[0],
                exchange=exchange,
                datetime=bar_dict["datetime"],
                interval=Interval.DAILY,
                open_price=bar_dict["open_price"],
                high_price=bar_dict["high_price"],
                low_price=bar_dict["low_price"],
                close_price=bar_dict["close_price"],
                volume=bar_dict["volume"],
                open_interest=0,
                gateway_name="BACKTEST"
            )
            bars.append(bar)
        
        return bars
    
    def get_multiple_stocks(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        interval: str = "d",
        use_cache: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, List[BarData]]:
        """
        批量获取多只股票数据
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            interval: 数据周期
            use_cache: 是否使用缓存
            progress_callback: 进度回调函数
        
        Returns:
            股票数据字典
        """
        all_data = {}
        success_count = 0
        failed_symbols = []
        
        print(f"\n开始批量获取 {len(symbols)} 只股票数据...")
        print(f"时间范围: {start_date.date()} 至 {end_date.date()}")
        print(f"缓存: {'启用' if use_cache else '禁用'}\n")
        
        for i, symbol in enumerate(symbols, 1):
            bars = self.get_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                use_cache=use_cache
            )
            
            if bars and len(bars) > 50:
                all_data[symbol] = bars
                success_count += 1
                print(f"[{i}/{len(symbols)}] ✓ {symbol} ({len(bars)}条)")
            else:
                failed_symbols.append(symbol)
                print(f"[{i}/{len(symbols)}] ✗ {symbol} (数据不足)")
            
            # 进度回调
            if progress_callback:
                progress_callback(i, len(symbols), symbol, len(bars) if bars else 0)
        
        print(f"\n数据获取完成: {success_count}/{len(symbols)} 只股票")
        if failed_symbols:
            print(f"失败标的: {failed_symbols}")
        
        return all_data
    
    def clear_cache(self, older_than_days: Optional[int] = None):
        """
        清理缓存
        
        Args:
            older_than_days: 清理多少天前的缓存，None表示清理全部
        """
        current_time = time.time()
        cleared_count = 0
        
        for cache_file in self.cache_dir.glob("*.pkl"):
            if older_than_days is None:
                cache_file.unlink()
                cleared_count += 1
            else:
                file_age = current_time - cache_file.stat().st_mtime
                if file_age > older_than_days * 86400:
                    cache_file.unlink()
                    cleared_count += 1
        
        print(f"清理缓存: {cleared_count} 个文件")
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        cache_files = list(self.cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in cache_files)
        
        return {
            "cache_count": len(cache_files),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "cache_dir": str(self.cache_dir)
        }
