"""
dashboard.py
Interactive Streamlit DCF screening dashboard.

Run:
  streamlit run dashboard.py

Features:
  - Full S&P 500 DCF results table with sorting + filtering
  - Sector / verdict / upside range filters
  - Single-ticker deep-dive: value bridge, financials chart, sensitivity heatmap
  - Download buttons for individual reports and batch summary
"""

import json
import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from config.settings import REPORTS_DIR, WACC_DELTAS, TG_DELTAS
from db.database import (
    fetch_results_summary,
    fetch_financials,
    fetch_assumptions,
    get_conn,
)
from engine.sensitivity import grid_to_matrix

log = logging.getLogger(__name__)

# ── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="S&P 500 DCF Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card {
        background: #f0f4fb;
        border-radius: 10px;
        padding: 16px 20px;
        margin: 6px 0;
    }
    .undervalued  { color: #276221; font-weight: 700; }
    .overvalued   { color: #9C0006; font-weight: 700; }
    .fairly       { color: #7D6608; font-weight: 700; }
    .big-number   { font-size: 2rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ── Data loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_summary() -> pd.DataFrame:
    sql = """
        SELECT
            c.ticker, c.name, c.sector, c.industry,
            r.intrinsic_price, r.market_price, r.upside_pct,
            r.verdict, r.pv_fcf_sum, r.pv_terminal_value,
            r.enterprise_value, r.equity_value,
            a.wacc, a.beta, a.terminal_growth, a.fcf_margin,
            a.revenue_growth_y1, a.net_debt, a.cost_of_equity,
            r.sensitivity_json, r.calculated_at
        FROM dcf_results r
        JOIN companies c ON c.ticker = r.ticker
        LEFT JOIN dcf_assumptions a ON a.ticker = r.ticker
        ORDER BY r.upside_pct DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["upside_pct"] = pd.to_numeric(df["upside_pct"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_financials(ticker: str) -> pd.DataFrame:
    rows = fetch_financials(ticker)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("fiscal_year")
    return df


# ── Sidebar filters ───────────────────────────────────────────────────────────

def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.title("🔎 Filters")

    sectors = sorted(df["sector"].dropna().unique().tolist())
    sel_sectors = st.sidebar.multiselect(
        "Sector", sectors, default=sectors, key="sectors"
    )

    verdicts = ["UNDERVALUED", "FAIRLY_VALUED", "OVERVALUED"]
    sel_verdicts = st.sidebar.multiselect(
        "Verdict", verdicts, default=verdicts, key="verdicts"
    )

    upside_min, upside_max = float(df["upside_pct"].min() or -200), float(df["upside_pct"].max() or 200)
    upside_range = st.sidebar.slider(
        "Upside % range",
        min_value=round(upside_min, 0),
        max_value=round(upside_max, 0),
        value=(round(upside_min, 0), round(upside_max, 0)),
        step=5.0,
    )

    wacc_max = st.sidebar.slider("Max WACC (%)", 5, 25, 20, step=1)
    beta_max  = st.sidebar.slider("Max Beta", 0.5, 3.0, 2.5, step=0.1)

    filtered = df[
        df["sector"].isin(sel_sectors) &
        df["verdict"].isin(sel_verdicts) &
        df["upside_pct"].between(upside_range[0], upside_range[1]) &
        (df["wacc"].fillna(0) * 100 <= wacc_max) &
        (df["beta"].fillna(1) <= beta_max)
    ].copy()

    return filtered


# ── KPI summary row ───────────────────────────────────────────────────────────

def render_kpis(df: pd.DataFrame, filtered: pd.DataFrame):
    total     = len(df)
    n_und     = (df["verdict"] == "UNDERVALUED").sum()
    n_over    = (df["verdict"] == "OVERVALUED").sum()
    n_fair    = (df["verdict"] == "FAIRLY_VALUED").sum()
    avg_up    = df["upside_pct"].mean()
    showing   = len(filtered)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total companies",  total)
    c2.metric("Showing",          showing)
    c3.metric("🟢 Undervalued",   n_und,  f"{n_und/total*100:.0f}%")
    c4.metric("🟡 Fairly valued", n_fair, f"{n_fair/total*100:.0f}%")
    c5.metric("🔴 Overvalued",    n_over, f"{n_over/total*100:.0f}%")
    c6.metric("Avg upside %",     f"{avg_up:.1f}%")


# ── Main screener table ───────────────────────────────────────────────────────

def render_screener(filtered: pd.DataFrame):
    st.subheader("📋 Screener Results")

    display_cols = {
        "ticker":          "Ticker",
        "name":            "Company",
        "sector":          "Sector",
        "intrinsic_price": "Intrinsic ($)",
        "market_price":    "Market ($)",
        "upside_pct":      "Upside %",
        "verdict":         "Verdict",
        "wacc":            "WACC",
        "beta":            "Beta",
        "fcf_margin":      "FCF Margin",
    }

    disp = filtered[list(display_cols.keys())].rename(columns=display_cols).copy()
    disp["Upside %"]   = disp["Upside %"].map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "—")
    disp["Intrinsic ($)"] = disp["Intrinsic ($)"].map(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")
    disp["Market ($)"] = disp["Market ($)"].map(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")
    disp["WACC"]       = disp["WACC"].map(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—")
    disp["FCF Margin"] = disp["FCF Margin"].map(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—")
    disp["Beta"]       = disp["Beta"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")

    def color_verdict(val):
        if val == "UNDERVALUED":   return "background-color: #C6EFCE; color: #276221; font-weight:bold"
        elif val == "OVERVALUED":  return "background-color: #FFC7CE; color: #9C0006; font-weight:bold"
        else:                       return "background-color: #FFEB9C; color: #7D6608; font-weight:bold"

    styled = disp.style.map(color_verdict, subset=["Verdict"])
    st.dataframe(styled, use_container_width=True, height=450)

    # Download filtered table
    csv = filtered.to_csv(index=False)
    st.download_button(
        "⬇️  Download filtered results (CSV)",
        data=csv, file_name="dcf_filtered.csv", mime="text/csv"
    )


# ── Sector distribution chart ─────────────────────────────────────────────────

def render_sector_chart(df: pd.DataFrame):
    st.subheader("📊 Sector Overview")

    sector_df = (
        df.groupby(["sector", "verdict"])
        .size().reset_index(name="count")
    )
    color_map = {
        "UNDERVALUED":  "#276221",
        "FAIRLY_VALUED":"#B8860B",
        "OVERVALUED":   "#9C0006",
    }

    fig = px.bar(
        sector_df, x="count", y="sector", color="verdict",
        orientation="h",
        color_discrete_map=color_map,
        labels={"count": "# Companies", "sector": "", "verdict": "Verdict"},
        title="Verdict breakdown by sector",
        height=420,
    )
    fig.update_layout(
        legend_title_text="",
        plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#eee"),
        margin=dict(l=10, r=10, t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Single-ticker deep dive ────────────────────────────────────────────────────

def render_ticker_detail(df: pd.DataFrame):
    st.markdown("---")
    st.subheader("🔬 Ticker Deep Dive")

    ticker = st.selectbox(
        "Select a ticker",
        options=df["ticker"].tolist(),
        index=0,
        key="ticker_select",
    )

    row = df[df["ticker"] == ticker].iloc[0]

    # ── Header ─────────────────────────────────────────────────────────────
    verdict = row.get("verdict", "")
    verdict_color = {"UNDERVALUED": "🟢", "OVERVALUED": "🔴", "FAIRLY_VALUED": "🟡"}.get(verdict, "⚪")
    st.markdown(f"### {verdict_color} {row['ticker']} — {row['name']}")
    st.caption(f"{row.get('sector', '')} · {row.get('industry', '')}")

    # ── Key metrics ─────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Intrinsic price", f"${row['intrinsic_price']:,.2f}" if pd.notna(row['intrinsic_price']) else "—")
    m2.metric("Market price",    f"${row['market_price']:,.2f}"    if pd.notna(row['market_price']) else "—")
    upside = row.get("upside_pct")
    m3.metric("Upside / downside", f"{upside:+.1f}%" if pd.notna(upside) else "—",
              delta=f"{upside:+.1f}%" if pd.notna(upside) else None)
    m4.metric("WACC",  f"{row['wacc']*100:.1f}%" if pd.notna(row.get('wacc')) else "—")
    m5.metric("Beta",  f"{row['beta']:.2f}"       if pd.notna(row.get('beta')) else "—")

    col_left, col_right = st.columns(2)

    # ── Value bridge waterfall ───────────────────────────────────────────────
    with col_left:
        st.markdown("**Value bridge**")
        pv_fcf = row.get("pv_fcf_sum") or 0
        pv_tv  = row.get("pv_terminal_value") or 0
        ev     = row.get("enterprise_value") or 0
        net_d  = row.get("net_debt") or 0
        eq_val = row.get("equity_value") or 0

        fig = go.Figure(go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "total", "relative", "total"],
            x=["PV of FCFs", "PV terminal value", "Enterprise value",
               "Less: Net debt", "Equity value"],
            y=[pv_fcf / 1e9, pv_tv / 1e9, 0, -net_d / 1e9, 0],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            increasing={"marker": {"color": "#276221"}},
            decreasing={"marker": {"color": "#9C0006"}},
            totals={"marker": {"color": "#2E75B6"}},
            text=[f"${v/1e9:,.1f}B" for v in
                  [pv_fcf, pv_tv, ev, -net_d, eq_val]],
            textposition="outside",
        ))
        fig.update_layout(
            height=350,
            plot_bgcolor="white",
            yaxis_title="USD Billions",
            margin=dict(l=10, r=10, t=20, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Sensitivity heatmap ──────────────────────────────────────────────────
    with col_right:
        st.markdown("**Sensitivity heatmap — intrinsic price**")
        sens_json = row.get("sensitivity_json")
        if sens_json:
            grid = json.loads(sens_json)
            mat  = grid_to_matrix(grid)

            z = mat["matrix"]
            market = row.get("market_price") or 0

            fig = go.Figure(go.Heatmap(
                z=z,
                x=mat["tg_labels"],
                y=mat["wacc_labels"],
                colorscale=[
                    [0.0, "#9C0006"],
                    [0.5, "#FFEB9C"],
                    [1.0, "#276221"],
                ],
                zmid=market,
                text=[[f"${v:,.2f}" if v else "N/A" for v in row_] for row_ in z],
                texttemplate="%{text}",
                textfont={"size": 11},
                hovertemplate="WACC: %{y}<br>TG: %{x}<br>Price: %{text}<extra></extra>",
                colorbar=dict(title="Intrinsic $"),
            ))
            fig.add_annotation(
                text=f"Market: ${market:,.2f}",
                xref="paper", yref="paper",
                x=1.15, y=-0.12, showarrow=False,
                font=dict(size=10, color="gray"),
            )
            fig.update_layout(
                height=350,
                xaxis_title="Terminal growth rate",
                yaxis_title="WACC",
                margin=dict(l=10, r=80, t=20, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sensitivity data. Re-run pipeline for this ticker.")

    # ── Historical financials chart ──────────────────────────────────────────
    st.markdown("**Historical financials**")
    fin_df = load_financials(ticker)
    if not fin_df.empty:
        metric_options = {
            "Revenue":         "revenue",
            "Free cash flow":  "free_cash_flow",
            "EBITDA":          "ebitda",
            "Net income":      "net_income",
            "Operating CF":    "operating_cf",
        }
        sel_metrics = st.multiselect(
            "Metrics to display",
            list(metric_options.keys()),
            default=["Revenue", "Free cash flow", "EBITDA"],
            key=f"metrics_{ticker}",
        )

        fig = go.Figure()
        colors = ["#2E75B6", "#276221", "#E8883A", "#9C0006", "#7B2D8B"]
        for i, m in enumerate(sel_metrics):
            col = metric_options[m]
            if col in fin_df.columns:
                fig.add_trace(go.Bar(
                    x=fin_df["fiscal_year"],
                    y=fin_df[col] / 1e9,
                    name=m,
                    marker_color=colors[i % len(colors)],
                ))

        fig.update_layout(
            barmode="group",
            height=340,
            plot_bgcolor="white",
            yaxis_title="USD Billions",
            xaxis_title="Fiscal Year",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=10, r=10, t=30, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── WACC assumptions table ───────────────────────────────────────────────
    with st.expander("📐 WACC & DCF Assumptions"):
        asmp = fetch_assumptions(ticker)
        if asmp:
            cols_show = {
                "wacc":              ("WACC",               "{:.2%}"),
                "cost_of_equity":    ("Cost of equity",     "{:.2%}"),
                "cost_of_debt":      ("Cost of debt",       "{:.2%}"),
                "beta":              ("Beta",                "{:.2f}"),
                "risk_free_rate":    ("Risk-free rate",      "{:.2%}"),
                "equity_risk_premium": ("Equity risk prem.", "{:.2%}"),
                "tax_rate":          ("Tax rate",            "{:.2%}"),
                "debt_weight":       ("Debt weight",         "{:.2%}"),
                "equity_weight":     ("Equity weight",       "{:.2%}"),
                "terminal_growth":   ("Terminal growth",     "{:.2%}"),
                "fcf_margin":        ("FCF margin",          "{:.2%}"),
                "revenue_growth_y1": ("Y1 revenue growth",   "{:.2%}"),
                "net_debt":          ("Net debt",            "${:,.0f}"),
            }
            rows_out = []
            for key, (label, fmt) in cols_show.items():
                val = asmp.get(key)
                rows_out.append({
                    "Assumption": label,
                    "Value": fmt.format(val) if val is not None else "—",
                })
            st.dataframe(pd.DataFrame(rows_out), use_container_width=True,
                         hide_index=True)

    # ── Download individual Excel report ─────────────────────────────────────
    report_path = REPORTS_DIR / f"{ticker}_DCF.xlsx"
    if report_path.exists():
        with open(report_path, "rb") as f:
            st.download_button(
                f"⬇️  Download {ticker} Excel report",
                data=f.read(),
                file_name=report_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.caption(f"No Excel report found for {ticker}. Run `python pipeline.py {ticker}` to generate it.")


# ── Batch summary download ────────────────────────────────────────────────────

def render_batch_download():
    summary_path = REPORTS_DIR / "SP500_DCF_Summary.xlsx"
    if summary_path.exists():
        with open(summary_path, "rb") as f:
            st.sidebar.download_button(
                "⬇️  Download S&P 500 Summary (Excel)",
                data=f.read(),
                file_name="SP500_DCF_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.sidebar.caption("Run `python -m output.batch_summary` to generate the master Excel file.")


# ── Main app ──────────────────────────────────────────────────────────────────

def main():
    st.title("📊 S&P 500 Automated DCF Screener")
    st.caption("Powered by yfinance · Updated from local SQLite database")

    df = load_summary()

    if df.empty:
        st.error(
            "No DCF results found in the database.\n\n"
            "Run the pipeline first:\n"
            "```\npython pipeline.py AAPL MSFT GOOGL\n```"
        )
        st.stop()

    filtered = sidebar_filters(df)
    render_batch_download()

    render_kpis(df, filtered)
    st.markdown("---")

    tab1, tab2 = st.tabs(["📋 Screener", "📊 Sector View"])
    with tab1:
        render_screener(filtered)
    with tab2:
        render_sector_chart(df)

    render_ticker_detail(df)


if __name__ == "__main__":
    main()
