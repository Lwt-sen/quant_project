import logging
import backtrader as bt

logger = logging.getLogger(__name__)


class MACrossStrategy(bt.Strategy):
    """
    均线交叉多股票调仓策略
    - 选股：短期均线上穿长期均线的多头标的
    - 调仓：每N个交易日调仓，最多持有M只股票，等权分配
    - 风控：固定止损、固定止盈、移动止盈
    """
    params = (
        ("ma_short", 5),
        ("ma_long", 20),
        ("stop_lost_pct", 0.1),
        ("stop_won_pct", 0.4),
        ("mv_stop_pct", 0.05),
        ("mv_stop_trigger", 0.1),
        ("max_holdings", 10),
        ("rebalance_period", 10),
    )

    def __init__(self):
        # 为每个标的独立计算技术指标
        self.ma_short = {}
        self.ma_long = {}
        self.cross = {}
        for data in self.datas:
            self.ma_short[data] = bt.indicators.SMA(data.close, period=self.p.ma_short)
            self.ma_long[data] = bt.indicators.SMA(data.close, period=self.p.ma_long)
            self.cross[data] = bt.indicators.CrossOver(self.ma_short[data], self.ma_long[data])

        self.rebalance_counter = 0
        self.buy_price = {}
        self.highest_price = {}
        self.order = None

    def notify_order(self, order):
        """订单状态回调"""
        if order.status == order.Completed:
            data = order.data
            code = data._name
            if order.isbuy():
                self.buy_price[data] = order.executed.price
                self.highest_price[data] = order.executed.price
                logger.info(f"【买入】{code} | 价格:{order.executed.price:.2f} | 数量:{order.executed.size:.0f}")
            elif order.issell():
                profit = (order.executed.price / self.buy_price.get(data, 1) - 1) * 100
                tag = "盈利" if profit > 0 else "亏损"
                logger.info(f"【卖出】{code} | 价格:{order.executed.price:.2f} | {tag}:{profit:.2f}%")
                self.buy_price.pop(data, None)
                self.highest_price.pop(data, None)
        self.order = None

    def next(self):
        if self.order:
            return

        # 每日风控：止盈止损检查
        for data in self.datas:
            if not self.getposition(data).size:
                continue
            self.highest_price[data] = max(self.highest_price.get(data, data.close[0]), data.high[0])
            buy_price = self.buy_price.get(data, 0)
            if buy_price <= 0:
                continue

            # 固定止损
            if data.low[0] <= buy_price * (1 - self.p.stop_lost_pct):
                self.order = self.close(data=data)
                logger.info(f"【固定止损】{data._name}")
                return
            # 固定止盈
            if self.highest_price[data] >= buy_price * (1 + self.p.stop_won_pct):
                self.order = self.close(data=data)
                logger.info(f"【固定止盈】{data._name}")
                return
            # 移动止盈
            if self.highest_price[data] >= buy_price * (1 + self.p.mv_stop_trigger):
                if data.low[0] <= self.highest_price[data] * (1 - self.p.mv_stop_pct):
                    self.order = self.close(data=data)
                    logger.info(f"【移动止盈】{data._name}")
                    return

        # 定期调仓
        if self.rebalance_counter % self.p.rebalance_period == 0:
            self._rebalance()
        self.rebalance_counter += 1

    def _rebalance(self):
        """执行调仓逻辑"""
        logger.info(f"=== 第 {self.rebalance_counter//self.p.rebalance_period+1} 次调仓 ===")
        # 筛选多头标的（均线向上）
        candidates = []
        for data in self.datas:
            if len(data) < self.p.ma_long:
                continue
            if self.ma_short[data][0] > self.ma_long[data][0]:
                candidates.append(data)

        # 卖出不在候选池的持仓
        holdings = [d for d in self.datas if self.getposition(d).size]
        for data in holdings:
            if data not in candidates:
                self.order = self.close(data=data)
                logger.info(f"【调仓卖出】{data._name}")

        # 确定最终持仓，等权分配资金
        target = candidates[:self.p.max_holdings]
        if target:
            per_value = self.broker.getvalue() / len(target)
            for data in target:
                self.order_target_value(data=data, target=per_value)
        logger.info(f"调仓完成，当前持仓 {len(target)} 只")