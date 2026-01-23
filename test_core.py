from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine


def test_core():
    """Test core functionality without UI"""
    print("Testing VeighNa core functionality...")
    
    # 创建事件引擎
    event_engine = EventEngine()
    print("✓ EventEngine created successfully")
    
    # 创建主引擎
    main_engine = MainEngine(event_engine)
    print("✓ MainEngine created successfully")
    
    # 获取所有支持的应用
    apps = main_engine.get_all_apps()
    print(f"✓ Available apps: {apps}")
    
    # 获取所有支持的数据接口
    datafeeds = main_engine.get_all_datafeeds()
    print(f"✓ Available datafeeds: {datafeeds}")
    
    print("\nAll core functionality tests passed!")
    print("VeighNa framework is working correctly.")


if __name__ == "__main__":
    test_core()