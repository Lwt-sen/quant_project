import logging
from config import START_DATE, END_DATE, MA_SHORT, MA_LONG
from db_manager import init_db
from data_loader import (
    get_all_stock_data, get_daily_data, get_stock_list_from_db,
    load_backtest_data, get_index_daily, calc_ma_factor, calc_forward_return, save_factor_to_db
)
from backtest_engine import run_multi_stock_backtest
from factor_analysis import FactorAnalyzer
from monitor import SyncMonitor
from visualization import plot_backtest_result, plot_factor_analysis


def setup_logging():
    """统一日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main(
    update_stock_list: bool = True,
    update_daily_data: bool = True,
    incremental_sync: bool = True,
    save_factor_to_db: bool = False,
    run_backtest: bool = True,
    run_factor_analysis: bool = True,
    generate_plot: bool = True
):
    """
    量化数据支持系统主流程
    :param update_stock_list: 是否更新股票基础信息
    :param update_daily_data: 是否更新日线行情
    :param incremental_sync: 是否增量同步
    :param save_factor_to_db: 是否将因子存入数据库
    :param run_backtest: 是否执行回测
    :param run_factor_analysis: 是否执行因子分析
    :param generate_plot: 是否生成可视化报告
    """
    setup_logging()
    logger = logging.getLogger("main")
    monitor = SyncMonitor()

    logger.info("=" * 60)
    logger.info("量化数据支持系统 - 全量分析启动")
    logger.info("=" * 60)

    try:
        # 1. 初始化数据库
        init_db()
        monitor.add_record("数据库初始化", "success")

        # 2. 同步股票基础信息
        if update_stock_list:
            get_all_stock_data()
            monitor.add_record("股票基础信息同步", "success")

        # 3. 获取股票池
        stock_list = get_stock_list_from_db()
        if not stock_list:
            logger.error("股票池为空，请先同步股票基础数据")
            monitor.add_record("获取股票池", "failed")
            return
        logger.info(f"当前股票池：{len(stock_list)} 只股票")

        # 4. 同步日线行情数据
        if update_daily_data:
            report = get_daily_data(
                start_date=START_DATE,
                end_date=END_DATE,
                stock_list=stock_list,
                incremental=incremental_sync
            )
            status = "success" if not report["failed_batches"] else "partial_failed"
            monitor.add_record("日线行情同步", status, detail=report)

        # 5. 加载行情数据
        data_dict = load_backtest_data(START_DATE, END_DATE, stock_list)

        # 6. 计算并保存因子
        factor_df = calc_ma_factor(data_dict, MA_SHORT, MA_LONG)
        if save_factor_to_db:
            save_factor_to_db(factor_df)
            monitor.add_record("因子数据入库", "success")

        # 7. 运行回测
        if run_backtest:
            result_metrics, net_value, drawdown, daily_returns = run_multi_stock_backtest(data_dict)
            monitor.add_record("策略回测", "success", detail=result_metrics)

            if generate_plot:
                plot_backtest_result(net_value, drawdown, result_metrics)
                monitor.add_record("回测可视化生成", "success")

        # 8. 因子与绩效分析
        if run_factor_analysis:
            return_df = calc_forward_return(data_dict, period=1)
            analyzer = FactorAnalyzer(factor_df, return_df)

            # IC/IR计算
            ic_result = analyzer.calc_ic_ir(method="pearson")
            ic_series = ic_result.pop("IC序列")

            # 分位数分析
            quantile_result = analyzer.calc_quantile_return(groups=5)

            # 阿尔法归因
            benchmark_df = get_index_daily("000300.SH", START_DATE, END_DATE)
            alpha_result = analyzer.calc_alpha_beta(daily_returns, benchmark_df["benchmark_return"])

            # 收益分布分析
            dist_result = analyzer.calc_return_distribution(daily_returns)

            # 汇总结果
            factor_summary = {**ic_result, **quantile_result, **alpha_result, **dist_result}
            monitor.add_record("因子绩效分析", "success", detail=factor_summary)

            if generate_plot:
                plot_factor_analysis(ic_series, quantile_result, daily_returns, alpha_result)
                monitor.add_record("因子分析可视化生成", "success")

        # 9. 生成运维报告
        monitor.generate_report(output_file="sync_report.json")
        logger.info("全流程执行完毕")

    except Exception as e:
        logger.error(f"程序执行异常: {e}", exc_info=True)
        monitor.add_record("主流程", "failed", detail={"error": str(e)})
        raise


if __name__ == "__main__":
    main(
        update_stock_list=True,
        update_daily_data=True,
        incremental_sync=True,
        save_factor_to_db=False,
        run_backtest=True,
        run_factor_analysis=True,
        generate_plot=True
    )