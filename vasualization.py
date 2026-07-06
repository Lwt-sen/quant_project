import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def plot_backtest_result(
    net_value: pd.Series,
    drawdown: pd.Series,
    metrics: dict,
    output_file: str = "backtest_report.html",
    title: str = "均线策略回测报告"
):
    """生成回测净值+回撤交互式图表"""
    if net_value.empty:
        logger.warning("净值数据为空，跳过绘图")
        return

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("策略净值曲线", "回撤曲线"),
        row_heights=[0.7, 0.3]
    )

    # 净值曲线
    fig.add_trace(
        go.Scatter(
            x=net_value.index, y=net_value.values,
            mode="lines", name="策略净值",
            line=dict(color="#1f77b4", width=2),
            hovertemplate="日期: %{x}<br>净值: %{y:,.2f}元<extra></extra>"
        ),
        row=1, col=1
    )
    fig.add_hline(
        y=net_value.iloc[0], line_dash="dash", line_color="gray",
        annotation_text="初始资金", annotation_position="right",
        row=1, col=1
    )

    # 回撤曲线
    fig.add_trace(
        go.Scatter(
            x=drawdown.index, y=drawdown.values,
            mode="lines", name="回撤",
            fill="tozeroy", fillcolor="rgba(255, 65, 54, 0.2)",
            line=dict(color="#ff4136", width=1.5),
            hovertemplate="日期: %{x}<br>回撤: %{y:.2f}%<extra></extra>"
        ),
        row=2, col=1
    )

    # 右侧指标卡片
    metrics_text = "<br>".join([f"<b>{k}</b>: {v}" for k, v in metrics.items()])
    fig.add_annotation(
        x=1.02, y=0.95, xref="paper", yref="paper",
        text=metrics_text, showarrow=False, align="left",
        bordercolor="#ddd", borderwidth=1, borderpad=10, bgcolor="#f8f9fa"
    )

    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        hovermode="x unified",
        template="plotly_white",
        height=700,
        margin=dict(l=50, r=220, t=80, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="净值（元）", row=1, col=1)
    fig.update_yaxes(title_text="回撤（%）", row=2, col=1)
    fig.update_xaxes(title_text="交易日期", row=2, col=1)

    fig.write_html(output_file)
    logger.info(f"回测图表已生成，保存至：{output_file}")


def plot_factor_analysis(
    ic_series: pd.Series,
    quantile_returns: dict,
    strategy_returns: pd.Series,
    alpha_result: dict,
    output_file: str = "factor_analysis.html"
):
    """生成因子分析综合图表"""
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=("每日IC序列", "因子分位数年化收益", "策略日收益分布", "核心指标"),
        specs=[
            [{"colspan": 2}, None],
            [{}, {}],
            [{"colspan": 2}, None]
        ],
        vertical_spacing=0.1,
        row_heights=[0.4, 0.35, 0.25]
    )

    # 1. 每日IC柱状图
    fig.add_trace(
        go.Bar(x=ic_series.index, y=ic_series.values, name="日IC", marker_color="#1f77b4"),
        row=1, col=1
    )
    fig.add_hline(
        y=ic_series.mean(), line_dash="dash", line_color="red",
        annotation_text=f"IC均值: {ic_series.mean():.4f}", row=1, col=1
    )

    # 2. 分位数收益柱状图
    groups = list(quantile_returns.keys())
    values = [float(v.strip("%")) for v in quantile_returns.values()]
    colors = ["#ff4136" if i == 0 else "#2ca02c" if i == len(groups)-1 else "#7f7f7f" for i in range(len(groups))]
    fig.add_trace(
        go.Bar(x=groups, y=values, name="年化收益(%)", marker_color=colors),
        row=2, col=1
    )
    fig.update_yaxes(title_text="年化收益率(%)", row=2, col=1)

    # 3. 日收益分布直方图
    returns_pct = strategy_returns.dropna() * 100
    fig.add_trace(
        go.Histogram(x=returns_pct, nbinsx=50, name="收益分布", marker_color="#2ca02c"),
        row=2, col=2
    )
    fig.update_yaxes(title_text="频数", row=2, col=2)
    fig.update_xaxes(title_text="日收益率(%)", row=2, col=2)

    # 4. 核心指标文本
    ic_summary = {
        "IC均值": f"{ic_series.mean():.4f}",
        "信息比率IR": f"{ic_series.mean()/ic_series.std():.4f}"
    }
    all_metrics = {**ic_summary, **alpha_result}
    metrics_text = "<br>".join([f"<b>{k}</b>: {v}" for k, v in all_metrics.items()])
    fig.add_annotation(
        x=0.5, y=0.1, xref="paper", yref="paper",
        text=metrics_text, showarrow=False, align="left",
        bordercolor="#ddd", borderwidth=1, borderpad=10, bgcolor="#f8f9fa",
        font=dict(size=12)
    )

    fig.update_layout(
        title="因子与策略绩效分析报告",
        template="plotly_white",
        height=900,
        showlegend=False,
        title_x=0.5
    )

    fig.write_html(output_file)
    logger.info(f"因子分析图表已生成，保存至：{output_file}")