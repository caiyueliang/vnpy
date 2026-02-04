"""
资金管理模块

提供账户资金监控、可用资金计算和资金使用风险控制功能
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import threading

from vnpy.trader.object import AccountData


@dataclass
class AccountRecord:
    """账户记录"""
    # 基本信息
    vt_accountid: str
    accountid: str
    gateway_name: str
    
    # 资金信息
    balance: float = 0.0               # 总权益
    available: float = 0.0             # 可用资金
    frozen: float = 0.0                # 冻结资金
    
    # 计算字段
    margin: float = 0.0                # 保证金
    commission: float = 0.0            # 手续费
    
    # 时间戳
    last_update: datetime = field(default_factory=datetime.now)
    
    # 历史记录
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def position_value(self) -> float:
        """持仓市值（估算）"""
        return self.balance - self.available - self.frozen
    
    @property
    def cash_ratio(self) -> float:
        """现金比例"""
        if self.balance <= 0:
            return 0.0
        return self.available / self.balance
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "vt_accountid": self.vt_accountid,
            "accountid": self.accountid,
            "gateway_name": self.gateway_name,
            "balance": self.balance,
            "available": self.available,
            "frozen": self.frozen,
            "margin": self.margin,
            "commission": self.commission,
            "position_value": self.position_value,
            "cash_ratio": self.cash_ratio,
            "last_update": self.last_update.isoformat(),
        }


@dataclass
class AccountConfig:
    """账户管理配置"""
    # 风控配置
    min_cash_ratio: float = 0.1        # 最小现金比例 10%
    max_margin_ratio: float = 0.8      # 最大保证金比例 80%
    
    # 预警配置
    low_balance_threshold: float = 0.0   # 低资金预警阈值
    
    # 历史记录配置
    max_history_length: int = 1000     # 最大历史记录长度


@dataclass
class FundAllocation:
    """资金分配"""
    strategy_name: str
    allocated: float = 0.0             # 已分配资金
    used: float = 0.0                  # 已使用资金
    available: float = 0.0             # 可用资金
    
    @property
    def usage_ratio(self) -> float:
        """使用率"""
        if self.allocated <= 0:
            return 0.0
        return self.used / self.allocated
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "strategy_name": self.strategy_name,
            "allocated": self.allocated,
            "used": self.used,
            "available": self.available,
            "usage_ratio": self.usage_ratio,
        }


class AccountTracker:
    """
    账户跟踪器
    
    跟踪单个账户的资金变化
    """
    
    def __init__(self, account_record: AccountRecord) -> None:
        """
        构造函数
        
        Args:
            account_record: 账户记录
        """
        self.record = account_record
        self._lock = threading.RLock()
    
    def update_from_account(self, account: AccountData) -> None:
        """
        从AccountData更新
        
        Args:
            account: 账户数据
        """
        with self._lock:
            # 记录历史
            self._add_history({
                "balance": account.balance,
                "available": account.available,
                "frozen": account.frozen,
            })
            
            # 更新数据
            self.record.balance = account.balance
            self.record.available = account.available
            self.record.frozen = account.frozen
            self.record.last_update = datetime.now()
    
    def update_margin(self, margin: float) -> None:
        """
        更新保证金
        
        Args:
            margin: 保证金金额
        """
        with self._lock:
            self.record.margin = margin
    
    def update_commission(self, commission: float) -> None:
        """
        更新手续费
        
        Args:
            commission: 手续费金额
        """
        with self._lock:
            self.record.commission += commission
    
    def _add_history(self, data: Dict[str, Any]) -> None:
        """添加历史记录"""
        self.record.history.append({
            "timestamp": datetime.now().isoformat(),
            **data
        })
        
        # 限制历史记录长度
        if len(self.record.history) > 1000:
            self.record.history = self.record.history[-1000:]
    
    def get_margin_ratio(self) -> float:
        """
        获取保证金比例
        
        Returns:
            保证金比例
        """
        with self._lock:
            if self.record.balance <= 0:
                return 0.0
            return self.record.margin / self.record.balance
    
    def can_withdraw(self, amount: float) -> bool:
        """
        检查是否可以提取资金
        
        Args:
            amount: 提取金额
            
        Returns:
            是否可以提取
        """
        with self._lock:
            return self.record.available >= amount


class AccountManager:
    """
    账户管理器
    
    管理所有账户的资金，提供资金分配和风险控制功能
    """
    
    def __init__(self, config: Optional[AccountConfig] = None) -> None:
        """
        构造函数
        
        Args:
            config: 账户管理配置
        """
        self.config = config or AccountConfig()
        
        # 账户存储
        self._accounts: Dict[str, AccountRecord] = {}
        self._trackers: Dict[str, AccountTracker] = {}
        
        # 资金分配
        self._allocations: Dict[str, FundAllocation] = {}
        
        # 回调函数
        self._callbacks: Dict[str, List[Callable]] = {
            "on_account_update": [],
            "on_low_balance": [],
            "on_margin_warning": [],
        }
        
        # 锁
        self._lock = threading.RLock()
    
    def register_callback(self, event: str, callback: Callable) -> None:
        """
        注册回调函数
        
        Args:
            event: 事件类型
            callback: 回调函数
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, *args, **kwargs) -> None:
        """触发回调"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"账户回调执行失败: {e}")
    
    def on_account_update(self, account: AccountData) -> None:
        """
        处理账户更新
        
        Args:
            account: 账户数据
        """
        with self._lock:
            tracker = self._trackers.get(account.vt_accountid)
            
            if tracker:
                # 更新现有账户
                tracker.update_from_account(account)
            else:
                # 创建新账户
                self._create_account(account)
            
            # 检查预警
            self._check_warnings(account.vt_accountid)
            
            # 触发回调
            self._emit("on_account_update", self._accounts.get(account.vt_accountid))
    
    def _create_account(self, account: AccountData) -> AccountTracker:
        """
        创建新账户
        
        Args:
            account: 账户数据
            
        Returns:
            账户跟踪器
        """
        # 创建记录
        record = AccountRecord(
            vt_accountid=account.vt_accountid,
            accountid=account.accountid,
            gateway_name=account.gateway_name,
            balance=account.balance,
            available=account.available,
            frozen=account.frozen,
        )
        
        # 创建跟踪器
        tracker = AccountTracker(record)
        
        # 存储
        self._accounts[account.vt_accountid] = record
        self._trackers[account.vt_accountid] = tracker
        
        return tracker
    
    def _check_warnings(self, vt_accountid: str) -> None:
        """
        检查预警
        
        Args:
            vt_accountid: 账户ID
        """
        tracker = self._trackers.get(vt_accountid)
        if not tracker:
            return
        
        record = tracker.record
        
        # 检查低资金预警
        if self.config.low_balance_threshold > 0:
            if record.available < self.config.low_balance_threshold:
                self._emit("on_low_balance", record)
        
        # 检查保证金预警
        margin_ratio = tracker.get_margin_ratio()
        if margin_ratio > self.config.max_margin_ratio:
            self._emit("on_margin_warning", record, margin_ratio)
    
    def get_account(self, vt_accountid: str) -> Optional[AccountRecord]:
        """
        获取账户
        
        Args:
            vt_accountid: 账户ID
            
        Returns:
            账户记录
        """
        with self._lock:
            return self._accounts.get(vt_accountid)
    
    def get_tracker(self, vt_accountid: str) -> Optional[AccountTracker]:
        """
        获取账户跟踪器
        
        Args:
            vt_accountid: 账户ID
            
        Returns:
            账户跟踪器
        """
        with self._lock:
            return self._trackers.get(vt_accountid)
    
    def get_all_accounts(self) -> List[AccountRecord]:
        """
        获取所有账户
        
        Returns:
            账户列表
        """
        with self._lock:
            return list(self._accounts.values())
    
    def get_total_balance(self) -> float:
        """
        获取总权益
        
        Returns:
            总权益
        """
        with self._lock:
            return sum(acc.balance for acc in self._accounts.values())
    
    def get_total_available(self) -> float:
        """
        获取总可用资金
        
        Returns:
            总可用资金
        """
        with self._lock:
            return sum(acc.available for acc in self._accounts.values())
    
    def get_total_frozen(self) -> float:
        """
        获取总冻结资金
        
        Returns:
            总冻结资金
        """
        with self._lock:
            return sum(acc.frozen for acc in self._accounts.values())
    
    def allocate_funds(
        self,
        strategy_name: str,
        amount: float
    ) -> bool:
        """
        分配资金给策略
        
        Args:
            strategy_name: 策略名称
            amount: 分配金额
            
        Returns:
            是否分配成功
        """
        with self._lock:
            total_available = self.get_total_available()
            
            if amount > total_available:
                print(f"可用资金不足: {total_available} < {amount}")
                return False
            
            # 获取或创建分配记录
            allocation = self._allocations.get(strategy_name)
            if not allocation:
                allocation = FundAllocation(strategy_name=strategy_name)
                self._allocations[strategy_name] = allocation
            
            # 更新分配
            allocation.allocated += amount
            allocation.available += amount
            
            return True
    
    def release_funds(
        self,
        strategy_name: str,
        amount: float
    ) -> bool:
        """
        释放策略资金
        
        Args:
            strategy_name: 策略名称
            amount: 释放金额
            
        Returns:
            是否释放成功
        """
        with self._lock:
            allocation = self._allocations.get(strategy_name)
            if not allocation:
                return False
            
            if amount > allocation.available:
                print(f"策略可用资金不足: {allocation.available} < {amount}")
                return False
            
            # 更新分配
            allocation.allocated -= amount
            allocation.available -= amount
            
            return True
    
    def use_funds(
        self,
        strategy_name: str,
        amount: float
    ) -> bool:
        """
        使用策略资金
        
        Args:
            strategy_name: 策略名称
            amount: 使用金额
            
        Returns:
            是否使用成功
        """
        with self._lock:
            allocation = self._allocations.get(strategy_name)
            if not allocation:
                return False
            
            if amount > allocation.available:
                print(f"策略可用资金不足: {allocation.available} < {amount}")
                return False
            
            # 更新使用
            allocation.used += amount
            allocation.available -= amount
            
            return True
    
    def free_funds(
        self,
        strategy_name: str,
        amount: float
    ) -> bool:
        """
        释放策略已用资金
        
        Args:
            strategy_name: 策略名称
            amount: 释放金额
            
        Returns:
            是否释放成功
        """
        with self._lock:
            allocation = self._allocations.get(strategy_name)
            if not allocation:
                return False
            
            if amount > allocation.used:
                amount = allocation.used
            
            # 更新使用
            allocation.used -= amount
            allocation.available += amount
            
            return True
    
    def get_allocation(self, strategy_name: str) -> Optional[FundAllocation]:
        """
        获取资金分配
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            资金分配
        """
        with self._lock:
            return self._allocations.get(strategy_name)
    
    def get_all_allocations(self) -> List[FundAllocation]:
        """
        获取所有资金分配
        
        Returns:
            资金分配列表
        """
        with self._lock:
            return list(self._allocations.values())
    
    def check_fund_limit(self, amount: float) -> bool:
        """
        检查资金限制
        
        Args:
            amount: 使用金额
            
        Returns:
            是否通过检查
        """
        with self._lock:
            total_available = self.get_total_available()
            
            if amount > total_available:
                print(f"可用资金不足: {total_available} < {amount}")
                return False
            
            # 检查现金比例
            total_balance = self.get_total_balance()
            if total_balance > 0:
                new_cash_ratio = (total_available - amount) / total_balance
                if new_cash_ratio < self.config.min_cash_ratio:
                    print(f"现金比例将低于限制: {new_cash_ratio:.2%} < {self.config.min_cash_ratio:.2%}")
                    return False
            
            return True
    
    def check_strategy_fund_limit(
        self,
        strategy_name: str,
        amount: float
    ) -> bool:
        """
        检查策略资金限制
        
        Args:
            strategy_name: 策略名称
            amount: 使用金额
            
        Returns:
            是否通过检查
        """
        with self._lock:
            allocation = self._allocations.get(strategy_name)
            if not allocation:
                return False
            
            if amount > allocation.available:
                print(f"策略可用资金不足: {allocation.available} < {amount}")
                return False
            
            return True
    
    def get_cash_ratio(self) -> float:
        """
        获取现金比例
        
        Returns:
            现金比例
        """
        with self._lock:
            total_balance = self.get_total_balance()
            if total_balance <= 0:
                return 0.0
            
            total_available = self.get_total_available()
            return total_available / total_balance
    
    def get_margin_ratio(self) -> float:
        """
        获取保证金比例
        
        Returns:
            保证金比例
        """
        with self._lock:
            total_margin = sum(
                tracker.record.margin
                for tracker in self._trackers.values()
            )
            total_balance = self.get_total_balance()
            
            if total_balance <= 0:
                return 0.0
            
            return total_margin / total_balance
    
    def get_account_report(self) -> Dict[str, Any]:
        """
        获取账户报告
        
        Returns:
            账户报告
        """
        with self._lock:
            return {
                "accounts": [
                    acc.to_dict() for acc in self._accounts.values()
                ],
                "summary": {
                    "total_balance": self.get_total_balance(),
                    "total_available": self.get_total_available(),
                    "total_frozen": self.get_total_frozen(),
                    "cash_ratio": self.get_cash_ratio(),
                    "margin_ratio": self.get_margin_ratio(),
                },
                "allocations": [
                    alloc.to_dict() for alloc in self._allocations.values()
                ],
            }
