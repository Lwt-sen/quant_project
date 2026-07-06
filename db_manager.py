import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Integer, Date, Float, BigInteger, UniqueConstraint, Index, text
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

load_dotenv()
logger = logging.getLogger(__name__)

# ===================== 数据库连接配置 =====================
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?charset=utf8mb4"
)

try:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        pool_recycle=3600,
        pool_pre_ping=True,
        pool_use_lifo=True,
        echo=False
    )
    logger.info(f"数据库引擎初始化成功 {DB_HOST}:{DB_PORT}/{DB_NAME}")
except Exception as e:
    logger.error(f"数据库引擎初始化失败: {e}")
    raise

# ===================== ORM基础定义 =====================
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_db_session():
    """数据库会话上下文，自动提交/回滚/关闭"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"数据库事务失败，已回滚: {e}")
        raise
    finally:
        session.close()


# ===================== 1. 日线行情表 =====================
class DailyQfq(Base):
    """前复权日线行情表（原始事实层）"""
    __tablename__ = "daily_qfq"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(10), nullable=False, comment="股票代码")
    trade_date = Column(Date, nullable=False, comment="交易日期")
    open = Column(Float, comment="开盘价")
    close = Column(Float, comment="收盘价")
    low = Column(Float, comment="最低价")
    high = Column(Float, comment="最高价")
    volume = Column(BigInteger, comment="成交量")
    amount = Column(Float, comment="成交额")

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uk_code_date"),
        Index("idx_trade_date", "trade_date"),
        {"comment": "股票前复权日线行情表"},
    )


# ===================== 2. 股票基础信息表 =====================
class AllStock(Base):
    """全市场股票基础信息表"""
    __tablename__ = "all_stock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(10), nullable=False, comment="股票代码")
    name = Column(String(20), nullable=False, comment="股票名称")
    list_date = Column(Date, nullable=False, comment="上市日期")
    industry = Column(String(20), nullable=False, comment="所属行业")

    __table_args__ = (
        UniqueConstraint("ts_code", name="uk_ts_code"),
        {"comment": "全市场可交易股票汇总表"},
    )


# ===================== 3. 同步状态表 =====================
class SyncStatus(Base):
    """数据同步状态记录表"""
    __tablename__ = "sync_status"

    table_name = Column(String(50), primary_key=True, comment="数据表名")
    last_sync_date = Column(Date, comment="最后同步日期")
    update_time = Column(Date, comment="更新时间")


# ===================== 4. 因子数据表 =====================
class FactorDaily(Base):
    """日线因子数据表（衍生层）"""
    __tablename__ = "daily_factor"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(10), nullable=False, comment="股票代码")
    trade_date = Column(Date, nullable=False, comment="交易日期")
    ma_ratio_5_20 = Column(Float, comment="5日/20日均线比值因子")

    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uk_factor_code_date"),
        Index("idx_factor_date", "trade_date"),
        {"comment": "日线因子数据表"},
    )


# ===================== 通用工具函数 =====================
def init_db():
    """初始化所有数据表结构"""
    try:
        Base.metadata.create_all(engine)
        logger.info("数据库表结构初始化完成")
    except Exception as e:
        logger.error(f"数据库表结构初始化失败: {e}")
        raise


def bulk_upsert_daily(df):
    """批量Upsert写入日线行情数据"""
    if df.empty:
        return 0

    columns = ["ts_code", "trade_date", "open", "close", "low", "high", "volume", "amount"]
    placeholders = ", ".join([f":{col}" for col in columns])
    update_clause = ", ".join([f"{col}=VALUES({col})" for col in columns if col not in ["ts_code", "trade_date"]])

    sql = text(f"""
        INSERT INTO daily_qfq ({', '.join(columns)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {update_clause}
    """)

    data = df[columns].to_dict("records")
    with engine.connect() as conn:
        result = conn.execute(sql, data)
        conn.commit()
        return result.rowcount


def bulk_upsert_factor(df):
    """批量Upsert写入因子数据"""
    if df.empty:
        return 0

    columns = ["ts_code", "trade_date", "ma_ratio_5_20"]
    placeholders = ", ".join([f":{col}" for col in columns])
    update_clause = ", ".join([f"{col}=VALUES({col})" for col in columns if col not in ["ts_code", "trade_date"]])

    sql = text(f"""
        INSERT INTO daily_factor ({', '.join(columns)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {update_clause}
    """)

    data = df[columns].to_dict("records")
    with engine.connect() as conn:
        result = conn.execute(sql, data)
        conn.commit()
        return result.rowcount