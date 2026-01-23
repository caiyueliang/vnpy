#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTA应用安装测试脚本
用于测试vnpy_ctastrategy和vnpy_ctabacktester的安装是否成功
"""

import os
import sys
import tempfile

# 创建临时目录用于测试
TEMP_DIR = tempfile.mkdtemp(prefix="vntrader_test_")
print(f"创建临时目录: {TEMP_DIR}")

# 设置环境变量，使用临时目录
os.environ["VNPY_HOME"] = TEMP_DIR

# 创建必要的子目录
os.makedirs(os.path.join(TEMP_DIR, "log"), exist_ok=True)
os.makedirs(os.path.join(TEMP_DIR, "database"), exist_ok=True)

# 修改sys.path，确保使用本地的vnpy
sys.path.insert(0, ".")

print("\n=== 测试CTA应用安装 ===")

try:
    # 测试导入CTA策略应用
    print("1. 测试导入vnpy_ctastrategy...")
    from vnpy_ctastrategy import CtaStrategyApp
    print("✓ vnpy_ctastrategy导入成功")
    
    # 测试导入CTA回测应用
    print("2. 测试导入vnpy_ctabacktester...")
    from vnpy_ctabacktester import CtaBacktesterApp
    print("✓ vnpy_ctabacktester导入成功")
    
    # 测试导入SQLite数据库
    print("3. 测试导入vnpy_sqlite...")
    from vnpy_sqlite import Database
    print("✓ vnpy_sqlite导入成功")
    
    print("\n✅ 所有CTA应用安装测试通过！")
    print("\n📦 已安装的包：")
    print("   - vnpy_ctastrategy")
    print("   - vnpy_ctabacktester")
    print("   - vnpy_sqlite")
    
    print("\n📝 注意事项：")
    print("   - 由于当前环境的权限限制，无法实际运行GUI界面")
    print("   - 但CTA应用的安装是成功的")
    print("   - 在实际环境中，您可以通过以下命令运行：")
    print("     PYTHONPATH=. python examples/veighna_trader/run.py")
    
except Exception as e:
    print(f"\n❌ 测试失败：{e}")
    import traceback
    traceback.print_exc()
    
finally:
    # 清理临时目录
    import shutil
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print(f"\n清理临时目录: {TEMP_DIR}")

print("\n=== 测试完成 ===")
