from datetime import datetime, timedelta

# ===================== 基础日期参数 =====================
START_DATE = "20230101"
yesterday = datetime.now() - timedelta(days=1)
END_DATE = yesterday.strftime("%Y%m%d")

# ===================== 技术指标参数 =====================
MA_SHORT = 5
MA_LONG = 20
STOP_LOST_PCT = 0.1   # 固定止损10%
STOP_WON_PCT = 0.4    # 固定止盈40%
MV_STOP_PCT = 0.05    # 移动止盈回撤5%
MV_STOP_TRIGGER = 0.1 # 移动止盈触发阈值10%

# ===================== 持仓调仓参数 =====================
MAX_HOLDINGS = 10         # 最大持仓数
REBALANCE_PERIOD = 10     # 调仓周期（交易日）

# ===================== 资金交易参数 =====================
INITIAL_CAP = 1000000     # 初始资金100万
COMMISSION = 0.0003       # 佣金万三
SLIPPAGE = 0.001          # 滑点千一
RISK_FREE = 0.02          # 无风险利率年化2%

# ===================== 数据同步配置 =====================
BATCH_SIZE = 400          # 单次接口拉取股票数
MAX_RETRY = 3             # 接口最大重试次数
RETRY_BACKOFF = 2         # 重试指数退避基数
ENABLE_DATA_VALIDATE = True  # 是否开启数据校验
STRICT_VALIDATE = False   # 是否强校验（不通过则拒绝入库）

# ===================== 数据质量校验规则 =====================
VALIDATE_RULES = {
    "price_order": True,      # 价格顺序校验
    "non_negative": True,     # 成交量非负校验
    "price_limit": 0.11,      # 单日涨跌幅阈值
    "null_check": True,       # 空值校验
    "duplicate_check": True   # 重复值校验
}
