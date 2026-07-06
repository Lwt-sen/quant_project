import pandas as pd
import numpy as np
from scipy import stats
import logging

logger = logging.getLogger(__name__)


class FactorAnalyzer:
    """因子与策略绩效分析器：IC/IR/阿尔法/分位数/收益分布"""

    def __init__(self, factor_df: pd.DataFrame, return_df: pd.DataFrame):
        self.factor_df, self.return_df = factor_df.align(return_df, join="inner")
        self.dates = self.factor_df.index
        logger.info(f"分析数据对齐完成，交易日: {len(self.dates)}, 股票数: {self.factor_df.shape[1]}")

    def calc_ic_ir(self, method: str = "pearson") -> dict:
        """计算每日IC、IC均值、IR、IC胜率"""
        logger.info(f"计算IC/IR，相关系数方法：{method}")
        ic_series = []

        for date in self.dates:
            factor = self.factor_df.loc[date].dropna()
            ret = self.return_df.loc[date].dropna()
            common = factor.index.intersection(ret.index)
            if len(common) < 30:
                ic_series.append(np.nan)
                continue

            if method == "pearson":
                ic, _ = stats.pearsonr(factor[common], ret[common])
            elif method == "spearman":
                ic, _ = stats.spearmanr(factor[common], ret[common])
            else:
                raise ValueError(f"不支持的相关系数方法：{method}")
            ic_series.append(ic)

        ic_series = pd.Series(ic_series, index=self.dates, name="IC").dropna()
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ir = ic_mean / ic_std if ic_std != 0 else 0
        ic_win_rate = (ic_series > 0).sum() / len(ic_series) if len(ic_series) > 0 else 0

        result = {
            "IC均值": round(ic_mean, 4),
            "IC标准差": round(ic_std, 4),
            "信息比率IR": round(ir, 4),
            "IC胜率": f"{ic_win_rate*100:.2f}%",
            "IC序列": ic_series
        }

        logger.info(f"IC计算完成 | 均值:{ic_mean:.4f} | IR:{ir:.4f} | 胜率:{ic_win_rate*100:.2f}%")
        return result

    def calc_quantile_return(self, groups: int = 5) -> dict:
        """因子分位数分组收益分析"""
        logger.info(f"因子分位数分析，分 {groups} 组")
        group_returns = {i+1: [] for i in range(groups)}

        for date in self.dates:
            factor = self.factor_df.loc[date].dropna()
            ret = self.return_df.loc[date].dropna()
            common = factor.index.intersection(ret.index)
            if len(common) < groups * 10:
                continue

            cross = pd.DataFrame({"factor": factor[common], "return": ret[common]})
            cross["group"] = pd.qcut(cross["factor"], q=groups, labels=False) + 1

            for g in range(1, groups+1):
                group_ret = cross[cross["group"] == g]["return"].mean()
                group_returns[g].append(group_ret)

        avg_returns = {}
        for g in range(1, groups+1):
            daily_avg = np.mean(group_returns[g])
            annualized = daily_avg * 252 * 100
            avg_returns[f"第{g}组"] = f"{annualized:.2f}%"

        long_short_daily = np.mean(group_returns[groups]) - np.mean(group_returns[1])
        long_short_annual = long_short_daily * 252 * 100
        avg_returns["多空组合年化"] = f"{long_short_annual:.2f}%"

        logger.info(f"分位数分析完成，多空组合年化收益: {long_short_annual:.2f}%")
        return avg_returns

    @staticmethod
    def calc_alpha_beta(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> dict:
        """基于CAPM计算年化阿尔法与贝塔"""
        logger.info("计算策略阿尔法与贝塔...")
        df = pd.concat([strategy_returns, benchmark_returns], axis=1).dropna()
        df.columns = ["strategy", "benchmark"]

        if len(df) < 30:
            raise ValueError("有效交易日不足，无法计算阿尔法")

        beta, alpha_daily, r_value, p_value, std_err = stats.linregress(df["benchmark"], df["strategy"])
        alpha_annual = (1 + alpha_daily) ** 252 - 1
        annual_return_strategy = (1 + df["strategy"].mean()) ** 252 - 1
        annual_return_benchmark = (1 + df["benchmark"].mean()) ** 252 - 1

        result = {
            "年化阿尔法": f"{alpha_annual*100:.2f}%",
            "贝塔系数": round(beta, 4),
            "策略年化收益": f"{annual_return_strategy*100:.2f}%",
            "基准年化收益": f"{annual_return_benchmark*100:.2f}%"
        }

        logger.info(f"阿尔法计算完成 | 年化阿尔法:{alpha_annual*100:.2f}% | 贝塔:{beta:.4f}")
        return result

    @staticmethod
    def calc_return_distribution(strategy_returns: pd.Series) -> dict:
        """策略收益中值与分布统计"""
        logger.info("计算策略收益分布统计...")
        returns = strategy_returns.dropna() * 100

        result = {
            "日收益均值(%)": round(returns.mean(), 4),
            "日收益中位数(%)": round(returns.median(), 4),
            "日收益标准差(%)": round(returns.std(), 4),
            "偏度": round(stats.skew(returns), 4),
            "峰度": round(stats.kurtosis(returns), 4),
            "最大单日涨幅(%)": round(returns.max(), 2),
            "最大单日跌幅(%)": round(returns.min(), 2)
        }

        logger.info(f"收益分布分析完成 | 中位数:{result['日收益中位数(%)']}% | 偏度:{result['偏度']}")
        return result