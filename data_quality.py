import pandas as pd
import logging
from config import VALIDATE_RULES

logger = logging.getLogger(__name__)


class DataValidator:
    """日线数据质量校验器"""

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
        self.rules = VALIDATE_RULES
        self.error_count = 0
        self.warning_count = 0
        self.error_details = []

    def validate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """执行全量数据校验，返回清洗后数据和校验报告"""
        if df.empty:
            return df, {"total": 0, "error": 0, "warning": 0, "details": []}

        self.error_count = 0
        self.warning_count = 0
        self.error_details = []
        original_count = len(df)

        # 1. 必填字段非空校验
        if self.rules["null_check"]:
            required_cols = ["ts_code", "trade_date", "open", "close", "low", "high", "volume"]
            before = len(df)
            df = df.dropna(subset=required_cols)
            null_num = before - len(df)
            if null_num > 0:
                self.error_count += null_num
                self.error_details.append(f"空值剔除：{null_num} 条")

        # 2. 数值非负校验
        if self.rules["non_negative"]:
            mask = (df["volume"] < 0) | (df["amount"] < 0)
            negative_num = mask.sum()
            if negative_num > 0:
                self.error_count += negative_num
                self.error_details.append(f"负成交量/成交额剔除：{negative_num} 条")
                df = df[~mask]

        # 3. 价格顺序校验（最高价≥开/收≥最低价）
        if self.rules["price_order"]:
            mask = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))
            price_error_num = mask.sum()
            if price_error_num > 0:
                self.error_count += price_error_num
                self.error_details.append(f"价格逻辑异常剔除：{price_error_num} 条")
                df = df[~mask]

        # 4. 涨跌幅异常校验（仅告警，不剔除）
        if self.rules["price_limit"]:
            df = df.sort_values(["ts_code", "trade_date"])
            df["pre_close"] = df.groupby("ts_code")["close"].shift(1)
            df["pct_change"] = (df["close"] - df["pre_close"]) / df["pre_close"]
            limit = self.rules["price_limit"]
            mask = (df["pct_change"].abs() > limit) & df["pre_close"].notna()
            abnormal_num = mask.sum()
            if abnormal_num > 0:
                self.warning_count += abnormal_num
                self.error_details.append(f"涨跌幅超阈值告警：{abnormal_num} 条（阈值±{limit*100:.0f}%）")
            df = df.drop(columns=["pre_close", "pct_change"])

        report = {
            "total_original": original_count,
            "valid_count": len(df),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "details": self.error_details
        }

        logger.info(
            f"数据校验完成 | 原始 {original_count} 条 | 有效 {len(df)} 条 | "
            f"错误 {self.error_count} 条 | 告警 {self.warning_count} 条"
        )
        if self.error_details:
            for detail in self.error_details:
                logger.warning(f"  - {detail}")

        return df, report