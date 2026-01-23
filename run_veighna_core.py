#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VeighNa Trader核心功能测试脚本
用于测试VeighNa框架的核心功能，避免外部依赖和权限问题
"""

import os
import sys
import tempfile

# 在导入vnpy模块之前，先修改环境变量和配置
# 1. 创建临时目录用于日志
TEMP_DIR = tempfile.mkdtemp(prefix="vntrader_")
LOG_DIR = os.path.join(TEMP_DIR, "log")
os.makedirs(LOG_DIR, exist_ok=True)

# 2. 设置配置文件，禁用文件日志
SETTING_CONTENT = '''
{
    "log.active": true,
    "log.level": 20,
    "log.console": true,
    "log.file": false
}
'''

# 3. 创建临时配置文件
SETTING_FILE = os.path.join(TEMP_DIR, "vt_setting.json")
with open(SETTING_FILE, "w") as f:
    f.write(SETTING_CONTENT)

# 4. 将临时目录添加到Python路径，让vnpy找到配置文件
sys.path.insert(0, TEMP_DIR)

# 现在可以安全地导入vnpy模块了
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp


def main():
    """启动VeighNa Trader核心功能"""
    print("启动VeighNa Trader核心功能...")
    print(f"临时目录: {TEMP_DIR}")
    
    try:
        # 创建Qt应用
        qapp = create_qapp()
        print("✓ Qt应用创建成功")
        
        # 创建事件引擎
        event_engine = EventEngine()
        print("✓ 事件引擎创建成功")
        
        # 创建主引擎
        main_engine = MainEngine(event_engine)
        print("✓ 主引擎创建成功")
        
        # 显示主窗口
        main_window = MainWindow(main_engine, event_engine)
        main_window.showMaximized()
        print("✓ 主窗口显示成功")
        
        print("\n✅ VeighNa Trader核心功能启动成功！")
        print("\n📝 注意事项：")
        print("   - 当前仅启动了核心功能，未加载任何网关和应用")
        print("   - 如需使用完整功能，请安装相应的扩展模块")
        print("   - 示例：pip install vnpy_ctp vnpy_ctastrategy")
        
        # 运行Qt事件循环
        qapp.exec()
        
    except Exception as e:
        print(f"\n❌ 启动失败：{e}")
        print("请检查错误信息，或尝试使用脚本模式运行")
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        print(f"\n临时目录已清理: {TEMP_DIR}")


if __name__ == "__main__":
    main()