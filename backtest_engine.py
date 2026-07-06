import logging
import pandas as pd
import backtrader as bt
from strategy import MACrossStrategy
from config import *

logger = logging.getLogger(__name__)


def run_multi_stock_backtest(data_dict: dict):
    """
    运行多股票回测
    :return: 指标字典, 净值序列, 回撤序列, 日收益率序列
    """
    if not data_dict:
        raise ValueError("行情数据为空，无法运行回测")

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(INITIAL_CAP)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.broker.set_slippage_perc(perc=SLIPPAGE)

    # 加载所有标的数据
    for code, df in data_dict.items():
        data = bt.feeds.PandasData(dataname=df, name=code, plot=False)
        cerebro.adddata(data)

    # 添加策略
    cerebro.addstrategy(
        MACrossStrategy,
        ma_short=MA_SHORT,
        ma_long=MA_LONG,
        stop_lost_pct=STOP_LOST_PCT,
        stop_won_pct=STOP_WON_PCT,
        mv_stop_pct=MV_STOP_PCT,
        mv_stop_trigger=MV_STOP_TRIGGER,
        max_holdings=MAX_HOLDINGS,
        rebalance_period=REBALANCE_PERIOD
    )

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=RISK_FREE)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return", timeframe=bt.TimeFrame.Days)

    logger.info(f"回测启动：初始资金 {INITIAL_CAP:,.0f} 元，标的 {len(data_dict)} 只")
    results = cerebro.run()
    if not results:
        logger.error("回测无结果")
        return {}, pd.Series(), pd.Series(), pd.Series()

    strat = results[0]
    trade = strat.analyzers.trade.get_analysis()
    returns = strat.analyzers.returns.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    daily_return_dict = strat.analyzers.time_return.get_analysis()

    # 计算净值与回撤
    daily_returns = pd.Series(daily_return_dict)
    daily_returns.index = pd.to_datetime(daily_returns.index)
    net_value = (1 + daily_returns).cumprod() * INITIAL_CAP
    net_value.name = "策略净值"

    running_max = net_value.cummax()
    drawdown = (net_value - running_max) / running_max * 100
    drawdown.name = "回撤(%)"

    # 计算交易指标
    total_trades = trade.get("total", {}).get("total", 0)
    win_trades = trade.get("won", {}).get("total", 0)
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    result_metrics = {
        "最终资金": round(cerebro.broker.getvalue(), 2),
        "总收益率": f"{returns.get('rtot',0)*100:.2f}%",
        "年化收益率": f"{returns.get('rnorm',0)*100:.2f}%",
        "最大回撤": f"{dd.get('max',{}).get('drawdown',0)*100:.2f}%",
        "夏普比率": round(sharpe.get("sharperatio", 0) or 0, 2),
        "总交易次数": total_trades,
        "胜率": f"{win_rate:.2f}%"
    }

    # 控制台输出
    logger.info("\n" + "="*50)
    logger.info("回测结果报告")
    for k, v in result_metrics.items():
        logger.info(f"{k}: {v}")
    logger.info("="*50 + "\n")

    return result_metrics, net_value, drawdown, daily_returns