import time
import logging
import pandas as pd
import tushare as ts
import os
from dotenv import load_dotenv
from datetime import datetime

from config import BATCH_SIZE, MAX_RETRY, RETRY_BACKOFF, ENABLE_DATA_VALIDATE, STRICT_VALIDATE, MA_SHORT, MA_LONG
from db_manager import engine, bulk_upsert_daily, bulk_upsert_factor, get_db_session, AllStock
from sync_status import get_last_sync_date, update_sync_status
from data_quality import DataValidator

load_dotenv()
logger = logging.getLogger(__name__)

# Tushare 接口初始化
ts_token = os.getenv("TUSHARE_TOKEN")
pro = ts.pro_api(ts_token)


def get_all_stock_data():
    """获取全市场主板股票基础数据，全量覆盖写入"""
    logger.info("开始同步股票基础信息...")
    try:
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,name,list_date,industry"
        )
        if df.empty:
            logger.warning("未获取到股票基础数据")
            return pd.DataFrame()

        df["list_date"] = pd.to_datetime(df["list_date"])
        # 过滤ST/退市，仅保留主板
        df = df[~df["name"].str.contains(r"ST|退|\*", regex=True)]
        df = df[df["ts_code"].str.match(r"^(00|60)")]

        df.to_sql(
            "all_stock",
            con=engine,
            if_exists="replace",
            index=False,
            chunksize=1000
        )
        update_sync_status("all_stock", datetime.now().strftime("%Y%m%d"))
        logger.info(f"股票基础数据同步完成，共 {len(df)} 只")
        return df

    except Exception as e:
        logger.error(f"股票基础数据同步失败: {e}")
        raise


def get_daily_data(start_date: str, end_date: str, stock_list: list, incremental: bool = True):
    """日线行情数据同步（支持增量/全量）"""
    if not stock_list:
        logger.warning("股票列表为空，跳过日线同步")
        return {"total": 0, "success": 0, "failed": 0}

    # 增量模式：从上次同步日期后一天开始
    if incremental:
        last_date = get_last_sync_date("daily_qfq")
        start_dt = max(
            datetime.strptime(start_date, "%Y%m%d"),
            datetime.strptime(last_date, "%Y%m%d")
        )
        sync_start = start_dt.strftime("%Y%m%d")
        logger.info(f"增量同步模式：上次同步至 {last_date}，本次从 {sync_start} 开始")
    else:
        sync_start = start_date
        logger.info(f"全量同步模式：同步区间 {sync_start} ~ {end_date}")

    # 起始日大于结束日则跳过
    if datetime.strptime(sync_start, "%Y%m%d") > datetime.strptime(end_date, "%Y%m%d"):
        logger.info("无新数据需要同步")
        return {"total": 0, "success": 0, "failed": 0}

    validator = DataValidator(strict_mode=STRICT_VALIDATE) if ENABLE_DATA_VALIDATE else None

    total = len(stock_list)
    batch_num = total // BATCH_SIZE + 1
    total_inserted = 0
    failed_batches = []
    start_time = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch_codes = stock_list[i:i+BATCH_SIZE]
        codes_str = ",".join(batch_codes)
        batch_idx = i // BATCH_SIZE + 1
        retry = 0

        while retry < MAX_RETRY:
            try:
                df = pro.daily(
                    ts_code=codes_str,
                    start_date=sync_start,
                    end_date=end_date,
                    adj="qfq",
                    fields="ts_code,trade_date,open,close,low,high,vol,amount"
                )

                if df.empty:
                    logger.debug(f"批次 {batch_idx} 无数据返回")
                    break

                # 字段标准化
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df.rename(columns={"vol": "volume"}, inplace=True)

                # 数据质量校验
                if validator:
                    df, _ = validator.validate(df)

                # 批量Upsert写入
                inserted = bulk_upsert_daily(df)
                total_inserted += inserted

                logger.info(
                    f"批次 {batch_idx}/{batch_num} 完成 | "
                    f"写入 {inserted} 条 | 进度 {min(i+BATCH_SIZE, total)/total*100:.1f}%"
                )
                break

            except Exception as e:
                retry += 1
                logger.error(
                    f"批次 {batch_idx} 请求失败，第 {retry}/{MAX_RETRY} 次重试 | 原因: {e}"
                )
                time.sleep(RETRY_BACKOFF ** retry)
        else:
            failed_batches.append(batch_idx)
            logger.error(f"批次 {batch_idx} 多次重试失败，已跳过")

    # 更新同步状态
    if len(failed_batches) < batch_num:
        update_sync_status("daily_qfq", end_date)

    cost_time = time.time() - start_time
    report = {
        "total_stocks": total,
        "total_batches": batch_num,
        "failed_batches": failed_batches,
        "inserted_rows": total_inserted,
        "cost_seconds": round(cost_time, 2),
        "incremental": incremental
    }

    logger.info(f"日线同步完成 | 耗时 {cost_time:.2f}s | 写入 {total_inserted} 条")
    return report


def get_stock_list_from_db() -> list:
    """从数据库获取股票代码列表"""
    with get_db_session() as session:
        result = session.query(AllStock.ts_code).all()
        return [row[0] for row in result]


def load_backtest_data(start_date: str, end_date: str, stock_list: list = None) -> dict:
    """从数据库加载回测行情数据"""
    logger.info("从数据库加载回测行情数据...")
    sql = """
        SELECT ts_code, trade_date, open, high, low, close, volume
        FROM daily_qfq
        WHERE trade_date BETWEEN :start AND :end
    """
    params = {"start": start_date, "end": end_date}

    if stock_list:
        sql += " AND ts_code IN :codes"
        params["codes"] = tuple(stock_list)

    df = pd.read_sql(sql, con=engine, params=params)
    if df.empty:
        raise ValueError("未查询到符合条件的行情数据，请先同步数据")

    data_dict = {}
    for code, group in df.groupby("ts_code"):
        group = group.set_index("trade_date").sort_index()
        data_dict[code] = group[["open", "high", "low", "close", "volume"]]

    logger.info(f"数据加载完成，共 {len(data_dict)} 只股票")
    return data_dict


def get_index_daily(index_code: str = "000300.SH", start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """获取基准指数日线数据（默认沪深300）"""
    logger.info(f"获取基准指数 {index_code} 行情数据")
    try:
        df = pro.index_daily(
            ts_code=index_code,
            start_date=start_date,
            end_date=end_date,
            fields="trade_date,close"
        )
        if df.empty:
            raise ValueError("基准指数数据获取为空")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date").sort_index()
        df.rename(columns={"close": "benchmark_close"}, inplace=True)
        df["benchmark_return"] = df["benchmark_close"].pct_change()
        logger.info(f"基准数据获取完成，共 {len(df)} 个交易日")
        return df
    except Exception as e:
        logger.error(f"基准指数数据获取失败: {e}")
        raise


def calc_ma_factor(data_dict: dict, ma_short: int = MA_SHORT, ma_long: int = MA_LONG) -> pd.DataFrame:
    """计算均线因子矩阵（日期×股票）"""
    logger.info("计算均线因子矩阵...")
    factor_dict = {}
    for code, df in data_dict.items():
        if len(df) < ma_long:
            continue
        df["ma_short"] = df["close"].rolling(ma_short).mean()
        df["ma_long"] = df["close"].rolling(ma_long).mean()
        df["factor"] = df["ma_short"] / df["ma_long"]
        factor_dict[code] = df["factor"]

    factor_df = pd.DataFrame(factor_dict).dropna(how="all")
    logger.info(f"因子矩阵计算完成，覆盖 {factor_df.shape[1]} 只股票，{factor_df.shape[0]} 个交易日")
    return factor_df


def calc_forward_return(data_dict: dict, period: int = 1) -> pd.DataFrame:
    """计算未来N期收益率矩阵（日期×股票）"""
    logger.info(f"计算未来 {period} 期收益率矩阵...")
    return_dict = {}
    for code, df in data_dict.items():
        df["fwd_return"] = df["close"].shift(-period) / df["close"] - 1
        return_dict[code] = df["fwd_return"]

    return_df = pd.DataFrame(return_dict).dropna(how="all")
    logger.info("收益率矩阵计算完成")
    return return_df


def save_factor_to_db(factor_df: pd.DataFrame):
    """将因子矩阵保存到数据库"""
    logger.info("因子数据写入数据库...")
    # 宽表转长表
    factor_long = factor_df.reset_index().melt(
        id_vars="index",
        var_name="ts_code",
        value_name="ma_ratio_5_20"
    ).rename(columns={"index": "trade_date"})
    factor_long = factor_long.dropna()

    # 批量写入
    rows = bulk_upsert_factor(factor_long)
    logger.info(f"因子数据写入完成，共 {rows} 条")
    return rows