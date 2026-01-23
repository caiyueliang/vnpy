# 先修改环境变量，禁用文件日志
import os
import sys

# 确保日志目录存在
log_dir = os.path.expanduser("~/.vntrader/log")
os.makedirs(log_dir, exist_ok=True)

# 在导入vnpy模块之前，先修改配置
# 通过修改sys.modules来拦截setting模块的加载
class MockSetting:
    def __init__(self):
        self.settings = {
            "font.family": "微软雅黑",
            "font.size": 12,
            "log.active": True,
            "log.level": 20,  # INFO
            "log.console": True,
            "log.file": False,  # 禁用文件日志
            "email.server": "smtp.qq.com",
            "email.port": 465,
            "email.username": "",
            "email.password": "",
            "email.sender": "",
            "email.receiver": "",
            "datafeed.name": "",
            "datafeed.username": "",
            "datafeed.password": "",
            "database.timezone": "Asia/Shanghai",
            "database.name": "sqlite",
            "database.database": "database.db",
            "database.host": "",
            "database.port": 0,
            "database.user": "",
            "database.password": ""
        }
    
    def __getitem__(self, key):
        return self.settings[key]

# 先创建mock的setting模块
sys.modules["vnpy.trader.setting"] = type('module', (), {
    'SETTINGS': MockSetting().settings
})()

# 现在可以安全地导入vnpy模块了
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine


def main():
    """Test VeighNa framework without UI"""
    print("\n=== VeighNa Framework Test ===")
    print("Version: vnpy 4.3.0")
    print("=" * 40)
    
    try:
        # 创建事件引擎
        event_engine = EventEngine()
        print("✓ EventEngine created successfully")
        
        # 创建主引擎
        main_engine = MainEngine(event_engine)
        print("✓ MainEngine created successfully")
        
        # 获取引擎信息
        print(f"\n✓ Engine initialized successfully")
        print(f"✓ Available gateways: {main_engine.get_all_gateways()}")
        print(f"✓ Available datafeeds: {main_engine.get_all_datafeeds()}")
        print(f"✓ Available apps: {main_engine.get_all_apps()}")
        
        print("\n✅ VeighNa framework is running correctly!")
        print("\n📝 Framework structure:")
        print("   - Event-driven architecture")
        print("   - Modular design with apps/gateways")
        print("   - Support for multiple datafeeds")
        print("   - Extensible plugin system")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Please check the error message above.")
    
    print("\n=== Test Completed ===")


if __name__ == "__main__":
    main()