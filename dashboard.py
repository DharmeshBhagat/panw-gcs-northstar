import datetime
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

PROJECT_ID = os.environ["BIGQUERY_PROJECT_ID"]
DATASET_ID = os.environ.get("BIGQUERY_DATASET_ID", "gcs_north_star")

BAND_COLORS = {
    "Green":  "#1D9E75",
    "Yellow": "#BA7517",
    "Orange": "#D85A30",
    "Red":    "#A32D2D",
}
BAND_ORDER = ["Green", "Yellow", "Orange", "Red"]

ALL_MONTHS = [datetime.date(2024, m, 1) for m in range(1, 13)]
MONTH_LABELS = [m.strftime("%B %Y") for m in ALL_MONTHS]
MONTH_BY_LABEL = {m.strftime("%B %Y"): m for m in ALL_MONTHS}

CAPTION = "Data source: BigQuery gcs_north_star · Refreshes every 10 minutes"


# ── BigQuery client (singleton) ───────────────────────────────────────────────

@st.cache_resource
def _bq_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT_ID)


def _coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        dtype_str = str(df[col].dtype)
        if df[col].dtype == object or "decimal" in dtype_str or "numeric" in dtype_str.lower():
            try:
                df[col] = df[col].astype(float)
            except (ValueError, TypeError):
                pass
    return df


def _run(sql: str, params: list | None = None) -> pd.DataFrame:
    sql = sql.replace("{PROJECT_ID}", PROJECT_ID).replace("{DATASET_ID}", DATASET_ID)
    cfg = bigquery.QueryJobConfig(query_parameters=params or [])
    df = _bq_client().query(sql, job_config=cfg).result().to_dataframe()
    return _coerce_numerics(df)


# ── Cached data loaders ───────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_portfolio_summary(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT *
        FROM `{PROJECT_ID}.{DATASET_ID}.portfolio_summary`
        WHERE month = @month
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_portfolio_trend() -> pd.DataFrame:
    return _run(
        """
        SELECT month, total_contracted_arr, total_realized_arr,
               CAST(portfolio_prs AS FLOAT64)        AS portfolio_prs,
               CAST(realization_rate_pct AS FLOAT64) AS realization_rate_pct
        FROM `{PROJECT_ID}.{DATASET_ID}.portfolio_summary`
        ORDER BY month
        """
    )


@st.cache_data(ttl=600)
def load_region_summary(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            region,
            COUNT(DISTINCT account_id)                                                   AS accounts,
            SUM(contracted_arr)                                                          AS contracted_arr,
            SUM(realized_arr)                                                            AS realized_arr,
            ROUND(SAFE_DIVIDE(SUM(prs * contracted_arr), SUM(contracted_arr)) * 100, 2) AS portfolio_prs_pct,
            SUM(CASE WHEN prs_band IN ('Red','Orange') THEN contracted_arr ELSE 0 END)  AS at_risk_arr
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @month
        GROUP BY region
        ORDER BY portfolio_prs_pct ASC
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_rep_summary(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            csm_id, rep_name, region, segment, account_count,
            total_contracted_arr, total_realized_arr,
            ROUND(CAST(portfolio_prs AS FLOAT64) * 100, 2) AS portfolio_prs_pct,
            at_risk_arr
        FROM `{PROJECT_ID}.{DATASET_ID}.csm_monthly_summary`
        WHERE month = @month
        ORDER BY portfolio_prs_pct ASC
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_account_detail(month: str, rep_id: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            a.company_name,
            r.industry,
            ROUND(CAST(r.prs                   AS FLOAT64) * 100, 2) AS prs_pct,
            ROUND(CAST(r.deployment_score      AS FLOAT64) * 100, 2) AS deploy_pct,
            ROUND(CAST(r.sustained_usage_score AS FLOAT64) * 100, 2) AS sustained_pct,
            ROUND(CAST(r.technical_health_score AS FLOAT64) * 100, 2) AS health_pct,
            ROUND(CAST(r.expansion_momentum    AS FLOAT64) * 100, 2) AS momentum_pct,
            r.realized_arr,
            r.prs_band
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        JOIN `{PROJECT_ID}.{DATASET_ID}.accounts` a ON a.account_id = r.account_id
        WHERE r.month = @month
          AND r.rep_id = @rep_id
        ORDER BY r.prs ASC
        """,
        [
            bigquery.ScalarQueryParameter("month",  "DATE",   month),
            bigquery.ScalarQueryParameter("rep_id", "STRING", rep_id),
        ],
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt(val: float) -> str:
    val = float(val)
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    return f"${val / 1_000:.0f}K"


def _apply_filters(df: pd.DataFrame, regions: list[str], segment: str) -> pd.DataFrame:
    if "region" in df.columns and "All" not in regions and regions:
        df = df[df["region"].isin(regions)]
    if "segment" in df.columns and segment != "All":
        df = df[df["segment"] == segment]
    return df


# ── App config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PANW GCS North Star",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("PANW GCS\nNorth Star")
    st.divider()

    page = st.radio("Navigation", ["Portfolio", "By Region", "By Rep"])

    st.divider()

    month_label = st.selectbox("Month", MONTH_LABELS, index=11)
    selected_month = MONTH_BY_LABEL[month_label]
    month_str = selected_month.isoformat()

    selected_regions = st.multiselect(
        "Region",
        options=["All", "North America", "EMEA", "APAC", "LATAM"],
        default=["All"],
    )

    selected_segment = st.radio("Segment", ["All", "Enterprise", "Mid-Market"])


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Portfolio Executive Summary
# ═══════════════════════════════════════════════════════════════════════════════

if page == "Portfolio":
    st.header(f"Portfolio Executive Summary — {month_label}")

    ps = load_portfolio_summary(month_str)
    if ps.empty:
        st.warning("No portfolio data for the selected month.")
        st.stop()

    row = ps.iloc[0]
    contracted   = float(row["total_contracted_arr"])
    realized     = float(row["total_realized_arr"])
    gap          = float(row["unrealized_gap"])
    rate_pct     = float(row["realization_rate_pct"])
    portfolio_prs = float(row["portfolio_prs"])

    # ── Section A: Metric cards ───────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Contracted ARR", _fmt(contracted))
    c2.metric("Total Realized ARR",   _fmt(realized), delta=f"{rate_pct:.1f}% realized")
    c3.metric("Unrealized Gap",       _fmt(gap),      delta=f"-{_fmt(gap)}", delta_color="inverse")
    c4.metric("Portfolio PRS",        f"{rate_pct:.1f}%")

    st.divider()

    # ── Section B: PRS band distribution ─────────────────────────────────────
    st.subheader(f"ARR by health band — {month_label}")

    band_df = pd.DataFrame([
        {"Band": "Green",  "ARR_M": float(row["green_arr"])  / 1e6, "Accounts": int(row["green_accounts"]), "Portfolio": "Portfolio"},
        {"Band": "Yellow", "ARR_M": float(row["yellow_arr"]) / 1e6, "Accounts": int(row["yellow_accounts"]), "Portfolio": "Portfolio"},
        {"Band": "Orange", "ARR_M": float(row["orange_arr"]) / 1e6, "Accounts": int(row["orange_accounts"]), "Portfolio": "Portfolio"},
        {"Band": "Red",    "ARR_M": float(row["red_arr"])    / 1e6, "Accounts": int(row["red_accounts"]),    "Portfolio": "Portfolio"},
    ])
    band_df = band_df.assign(label=band_df["Accounts"].astype(str) + " accts")

    fig_band = px.bar(
        band_df,
        x="ARR_M", y="Portfolio", color="Band",
        orientation="h", barmode="stack", text="label",
        color_discrete_map=BAND_COLORS,
        category_orders={"Band": BAND_ORDER},
        labels={"ARR_M": "ARR ($M)", "Portfolio": ""},
    )
    fig_band.update_traces(textposition="inside", insidetextanchor="middle", textfont_size=12)
    fig_band.update_layout(
        height=160,
        yaxis_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=40, b=10),
    )
    st.plotly_chart(fig_band, use_container_width=True)

    st.divider()

    # ── Section C: Monthly trend ──────────────────────────────────────────────
    st.subheader("Realized ARR trend")

    trend = load_portfolio_trend()
    trend["Contracted ARR ($M)"] = trend["total_contracted_arr"].astype(float) / 1e6
    trend["Realized ARR ($M)"]   = trend["total_realized_arr"].astype(float)   / 1e6
    trend["Month"] = pd.to_datetime(trend["month"]).dt.strftime("%b")

    fig_trend = px.line(
        trend, x="Month",
        y=["Contracted ARR ($M)", "Realized ARR ($M)"],
        markers=True,
        color_discrete_sequence=["#4A90D9", "#1D9E75"],
        labels={"value": "ARR ($M)", "variable": ""},
    )
    fig_trend.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=40, b=10),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.caption(CAPTION)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — By Region
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "By Region":
    st.header(f"Performance by Region — {month_label}")

    region_df = _apply_filters(
        load_region_summary(month_str), selected_regions, selected_segment
    )
    if region_df.empty:
        st.warning("No data for the selected filters.")
        st.stop()

    region_df = region_df.copy()
    region_df["Realized ARR ($M)"]   = region_df["realized_arr"].astype(float)   / 1e6
    region_df["Contracted ARR ($M)"] = region_df["contracted_arr"].astype(float) / 1e6

    ps_row = load_portfolio_summary(month_str)
    portfolio_avg = float(ps_row.iloc[0]["realization_rate_pct"]) if not ps_row.empty else 0.0

    # ── Section A: Side-by-side bar charts ───────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        fig_arr = px.bar(
            region_df, x="region", y="Realized ARR ($M)",
            color_discrete_sequence=["#1D9E75"],
            title="Total Realized ARR by Region",
            labels={"region": "Region"},
        )
        fig_arr.update_layout(showlegend=False)
        st.plotly_chart(fig_arr, use_container_width=True)

    with col2:
        fig_prs = px.bar(
            region_df, x="region", y="portfolio_prs_pct",
            color_discrete_sequence=["#4A90D9"],
            title="Portfolio PRS % by Region",
            labels={"region": "Region", "portfolio_prs_pct": "PRS (%)"},
        )
        fig_prs.add_hline(
            y=portfolio_avg, line_dash="dash", line_color="gray",
            annotation_text=f"Portfolio avg {portfolio_avg:.1f}%",
            annotation_position="top right",
        )
        fig_prs.update_layout(showlegend=False)
        st.plotly_chart(fig_prs, use_container_width=True)

    st.divider()

    # ── Section B: Region summary table ──────────────────────────────────────
    st.subheader("Region Summary  (worst PRS first)")

    tbl = region_df[[
        "region", "accounts", "Contracted ARR ($M)", "Realized ARR ($M)",
        "portfolio_prs_pct", "at_risk_arr",
    ]].copy()
    tbl.columns = ["Region", "Accounts", "Contracted ARR ($M)", "Realized ARR ($M)", "PRS%", "At-Risk ARR"]
    tbl["Contracted ARR ($M)"] = tbl["Contracted ARR ($M)"].round(1)
    tbl["Realized ARR ($M)"]   = tbl["Realized ARR ($M)"].round(1)
    tbl["At-Risk ARR"] = tbl["At-Risk ARR"].apply(_fmt)

    st.dataframe(tbl, use_container_width=True, hide_index=True)
    st.caption(CAPTION)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — By Sales Rep
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "By Rep":
    st.header(f"Performance by Sales Rep — {month_label}")

    rep_df = _apply_filters(
        load_rep_summary(month_str), selected_regions, selected_segment
    )
    if rep_df.empty:
        st.warning("No data for the selected filters.")
        st.stop()

    rep_df = rep_df.copy()

    # ── Section A: Rep performance table ─────────────────────────────────────
    st.subheader("Rep Performance  (worst PRS first)")

    tbl = rep_df[[
        "rep_name", "region", "segment", "account_count",
        "total_contracted_arr", "total_realized_arr", "portfolio_prs_pct", "at_risk_arr",
    ]].copy()
    tbl.columns = [
        "Rep Name", "Region", "Segment", "Accounts",
        "Contracted ARR", "Realized ARR", "PRS%", "At-Risk ARR",
    ]
    tbl["Contracted ARR"] = tbl["Contracted ARR"].apply(_fmt)
    tbl["Realized ARR"]   = tbl["Realized ARR"].apply(_fmt)
    tbl["At-Risk ARR"]    = tbl["At-Risk ARR"].apply(_fmt)

    def _rep_row_style(row):
        prs = row["PRS%"]
        if prs < 30:
            return [f"background-color: {BAND_COLORS['Red']}; color: white"] * len(row)
        if prs < 60:
            return [f"background-color: {BAND_COLORS['Orange']}; color: white"] * len(row)
        return [""] * len(row)

    st.dataframe(
        tbl.style.apply(_rep_row_style, axis=1),
        use_container_width=True, hide_index=True,
    )

    st.divider()

    # ── Section B: Rep drill-down ─────────────────────────────────────────────
    st.subheader("Account Detail")

    rep_options = dict(zip(rep_df["rep_name"], rep_df["csm_id"]))
    selected_rep_name = st.selectbox("Select Rep", list(rep_options.keys()))
    selected_rep_id   = rep_options[selected_rep_name]

    acct = load_account_detail(month_str, selected_rep_id)
    if acct.empty:
        st.info("No accounts found for this rep.")
    else:
        acct = acct.copy()
        acct["realized_arr"] = acct["realized_arr"].apply(_fmt)
        acct.columns = [
            "Company", "Industry", "PRS%", "Deploy%", "Sustained%",
            "Health%", "Momentum%", "Realized ARR", "Band",
        ]

        def _band_row_style(row):
            band = row["Band"]
            color = BAND_COLORS.get(band)
            if color and band in ("Red", "Orange"):
                return [f"background-color: {color}; color: white"] * len(row)
            return [""] * len(row)

        st.dataframe(
            acct.style.apply(_band_row_style, axis=1),
            use_container_width=True, hide_index=True,
        )

    st.caption(CAPTION)
