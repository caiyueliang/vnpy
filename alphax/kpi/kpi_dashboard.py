"""
KPI监控面板

实现核心KPI监控和目标管理
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class KPITarget:
    """KPI目标"""
    name: str
    target_value: float
    current_value: float = 0.0
    unit: str = "%"
    period: str = "monthly"  # daily, weekly, monthly, quarterly, yearly
    
    def get_achievement_rate(self) -> float:
        """获取达成率"""
        if self.target_value == 0:
            return 0.0
        return self.current_value / self.target_value
    
    def is_achieved(self) -> bool:
        """是否达成目标"""
        return self.current_value >= self.target_value


class KPIDashboard:
    """
    KPI监控面板
    
    监控核心KPI指标：
    - 月度目标收益率 >= 21%
    - 季度目标收益率 >= 100%
    - 年度目标收益率 >= 1000%
    - 最大回撤 <= 20%
    - 夏普比率 >= 3.0
    """
    
    def __init__(self) -> None:
        """Constructor"""
        self.kpis: Dict[str, KPITarget] = {}
        self._init_default_kpis()
    
    def _init_default_kpis(self) -> None:
        """初始化默认KPI"""
        # 收益率目标
        self.kpis["monthly_return"] = KPITarget(
            name="月度收益率",
            target_value=0.21,
            unit="%",
            period="monthly"
        )
        
        self.kpis["quarterly_return"] = KPITarget(
            name="季度收益率",
            target_value=1.0,
            unit="%",
            period="quarterly"
        )
        
        self.kpis["yearly_return"] = KPITarget(
            name="年度收益率",
            target_value=10.0,
            unit="%",
            period="yearly"
        )
        
        # 风险控制目标
        self.kpis["max_drawdown"] = KPITarget(
            name="最大回撤",
            target_value=0.20,
            unit="%",
            period="monthly"
        )
        
        # 风险调整收益
        self.kpis["sharpe_ratio"] = KPITarget(
            name="夏普比率",
            target_value=3.0,
            unit="",
            period="monthly"
        )
    
    def update_kpi(self, name: str, value: float) -> None:
        """更新KPI值"""
        if name in self.kpis:
            self.kpis[name].current_value = value
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取KPI面板数据"""
        return {
            "timestamp": datetime.now().isoformat(),
            "kpis": {
                name: {
                    "name": kpi.name,
                    "target": f"{kpi.target_value:.2%}" if kpi.unit == "%" else f"{kpi.target_value:.2f}",
                    "current": f"{kpi.current_value:.2%}" if kpi.unit == "%" else f"{kpi.current_value:.2f}",
                    "achievement": f"{kpi.get_achievement_rate():.1%}",
                    "status": "✓ 达成" if kpi.is_achieved() else "✗ 未达成"
                }
                for name, kpi in self.kpis.items()
            }
        }
    
    def generate_report(self) -> str:
        """生成KPI报告"""
        dashboard = self.get_dashboard()
        
        lines = [
            "=" * 60,
            "AlphaX KPI监控面板",
            "=" * 60,
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        for name, data in dashboard["kpis"].items():
            lines.append(f"{data['name']}")
            lines.append(f"  目标: {data['target']} | 当前: {data['current']} | 达成率: {data['achievement']}")
            lines.append(f"  状态: {data['status']}")
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)
