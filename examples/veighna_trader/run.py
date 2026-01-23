from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

# 导入已安装的应用
from vnpy_ctastrategy import CtaStrategyApp
from vnpy_ctabacktester import CtaBacktesterApp

# 其他应用可以根据需要取消注释
# from vnpy_spreadtrading import SpreadTradingApp
# from vnpy_algotrading import AlgoTradingApp
# from vnpy_optionmaster import OptionMasterApp
# from vnpy_portfoliostrategy import PortfolioStrategyApp
# from vnpy_scripttrader import ScriptTraderApp
# from vnpy_chartwizard import ChartWizardApp
# from vnpy_rpcservice import RpcServiceApp
# from vnpy_excelrtd import ExcelRtdApp
# from vnpy_datamanager import DataManagerApp
# from vnpy_datarecorder import DataRecorderApp
# from vnpy_riskmanager import RiskManagerApp
# from vnpy_webtrader import WebTraderApp
# from vnpy_portfoliomanager import PortfolioManagerApp


def main():
    """启动VeighNa Trader"""
    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    # 不添加任何网关，避免C++编译问题

    # 添加应用
    main_engine.add_app(CtaStrategyApp)  # CTA策略引擎
    main_engine.add_app(CtaBacktesterApp)  # CTA回测引擎

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    main()
