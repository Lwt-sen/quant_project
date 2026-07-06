from datetime import datetime
from db_manager import SyncStatus, get_db_session
import logging

logger = logging.getLogger(__name__)


def get_last_sync_date(table_name: str) -> str:
    """获取指定表的最后同步日期，返回YYYYMMDD格式"""
    with get_db_session() as session:
        record = session.query(SyncStatus).filter_by(table_name=table_name).first()
        if record and record.last_sync_date:
            return record.last_sync_date.strftime("%Y%m%d")
        return "20100101"  # 无记录返回默认起始日期


def update_sync_status(table_name: str, sync_date: str):
    """更新同步状态"""
    sync_date_dt = datetime.strptime(sync_date, "%Y%m%d").date()
    with get_db_session() as session:
        record = session.query(SyncStatus).filter_by(table_name=table_name).first()
        if record:
            record.last_sync_date = sync_date_dt
            record.update_time = sync_date_dt
        else:
            new_record = SyncStatus(
                table_name=table_name,
                last_sync_date=sync_date_dt,
                update_time=sync_date_dt
            )
            session.add(new_record)
    logger.info(f"同步状态已更新：{table_name} -> {sync_date}")