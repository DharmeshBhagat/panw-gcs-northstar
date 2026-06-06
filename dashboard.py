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

COMPONENT_COLORS = {
    "Deployment × 0.40": "#4A90D9",
    "Sustained × 0.30":  "#9B59B6",
    "Health × 0.20":     "#F39C12",
    "Expansion × 0.10":  "#27AE60",
}

CAPTION = "Data source: BigQuery gcs_north_star · Refreshes every 10 minutes"


# ── BigQuery helpers ──────────────────────────────────────────────────────────

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
        "SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.portfolio_summary` WHERE month = @month",
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
def load_account_list(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            r.account_id,
            a.company_name,
            r.industry,
            r.region,
            r.rep_id,
            r.rep_name,
            r.segment,
            r.contracted_arr,
            r.realized_arr,
            CAST(r.prs AS FLOAT64)                    AS prs,
            r.prs_band,
            r.shelfware_override,
            r.flag_overage,
            r.months_in_window,
            CAST(r.deployment_score       AS FLOAT64) AS deployment_score,
            CAST(r.sustained_usage_score  AS FLOAT64) AS sustained_usage_score,
            CAST(r.technical_health_score AS FLOAT64) AS technical_health_score,
            CAST(r.expansion_momentum     AS FLOAT64) AS expansion_momentum
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        JOIN `{PROJECT_ID}.{DATASET_ID}.accounts` a ON a.account_id = r.account_id
        WHERE r.month = @month
        ORDER BY r.prs ASC
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_all_months_accounts() -> pd.DataFrame:
    """All 12 months — used for the filtered Portfolio trend."""
    return _run(
        """
        SELECT
            r.month, r.account_id, a.company_name,
            r.industry, r.region, r.segment, r.rep_id, r.rep_name,
            r.contracted_arr, r.realized_arr,
            CAST(r.prs AS FLOAT64) AS prs,
            r.prs_band
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        JOIN `{PROJECT_ID}.{DATASET_ID}.accounts` a ON a.account_id = r.account_id
        ORDER BY r.month, r.prs ASC
        """
    )


@st.cache_data(ttl=600)
def load_account_detail(month: str, rep_id: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            r.account_id,
            a.company_name,
            r.industry,
            ROUND(CAST(r.prs                    AS FLOAT64) * 100, 2) AS prs_pct,
            ROUND(CAST(r.deployment_score       AS FLOAT64) * 100, 2) AS deploy_pct,
            ROUND(CAST(r.sustained_usage_score  AS FLOAT64) * 100, 2) AS sustained_pct,
            ROUND(CAST(r.technical_health_score AS FLOAT64) * 100, 2) AS health_pct,
            ROUND(CAST(r.expansion_momentum     AS FLOAT64) * 100, 2) AS momentum_pct,
            r.realized_arr,
            r.prs_band
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        JOIN `{PROJECT_ID}.{DATASET_ID}.accounts` a ON a.account_id = r.account_id
        WHERE r.month = @month AND r.rep_id = @rep_id
        ORDER BY r.prs ASC
        """,
        [
            bigquery.ScalarQueryParameter("month",  "DATE",   month),
            bigquery.ScalarQueryParameter("rep_id", "STRING", rep_id),
        ],
    )


@st.cache_data(ttl=600)
def load_account_trend(account_id: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            month,
            CAST(prs AS FLOAT64)                    AS prs,
            CAST(deployment_score AS FLOAT64)        AS deployment_score,
            CAST(sustained_usage_score AS FLOAT64)   AS sustained_usage_score,
            CAST(technical_health_score AS FLOAT64)  AS technical_health_score,
            CAST(expansion_momentum AS FLOAT64)      AS expansion_momentum,
            realized_arr, contracted_arr, prs_band
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE account_id = @account_id
        ORDER BY month
        """,
        [bigquery.ScalarQueryParameter("account_id", "STRING", account_id)],
    )


# ── Python aggregation helpers ────────────────────────────────────────────────

def _arr_weighted_prs(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    d = df.assign(_w=df["prs"] * df["contracted_arr"].astype(float))
    g = d.groupby(group_col).agg(
        _num=("_w", "sum"), _den=("contracted_arr", "sum")
    ).reset_index()
    g["portfolio_prs_pct"] = (
        g["_num"] / g["_den"].replace(0, float("nan")) * 100
    ).round(2)
    return g[[group_col, "portfolio_prs_pct"]]


def _at_risk_arr(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    return (
        df[df["prs_band"].isin(["Red", "Orange"])]
        .groupby(group_col)["contracted_arr"]
        .sum().rename("at_risk_arr").reset_index()
    )


def compute_region_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    base = df.groupby("region").agg(
        accounts=("account_id", "count"),
        contracted_arr=("contracted_arr", "sum"),
        realized_arr=("realized_arr", "sum"),
    ).reset_index()
    result = (base
              .merge(_arr_weighted_prs(df, "region"), on="region", how="left")
              .merge(_at_risk_arr(df, "region"),       on="region", how="left"))
    result["at_risk_arr"] = result["at_risk_arr"].fillna(0)
    return result.sort_values("portfolio_prs_pct")


def compute_rep_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    base = df.groupby(["rep_id", "rep_name", "region", "segment"]).agg(
        account_count=("account_id", "count"),
        total_contracted_arr=("contracted_arr", "sum"),
        total_realized_arr=("realized_arr", "sum"),
    ).reset_index()
    result = (base
              .merge(_arr_weighted_prs(df, "rep_id"), on="rep_id", how="left")
              .merge(_at_risk_arr(df, "rep_id"),       on="rep_id", how="left"))
    result["at_risk_arr"] = result["at_risk_arr"].fillna(0)
    return result.sort_values("portfolio_prs_pct")


# ── Formatting / navigation helpers ──────────────────────────────────────────

def _fmt(val: float) -> str:
    val = float(val)
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    return f"${val / 1_000:.0f}K"


def _go_to_account(account_id: str) -> None:
    st.session_state["selected_account"] = account_id
    st.session_state["pending_nav"] = "By Account"
    st.rerun()


# ── App config ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="PANW GCS North Star", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────

_PAGES = ["Portfolio", "By Region", "By Rep", "By Account"]

# Resolve pending navigation BEFORE the radio widget renders
if "pending_nav" in st.session_state:
    _nav_default = _PAGES.index(st.session_state.pop("pending_nav"))
else:
    _nav_default = _PAGES.index(st.session_state.get("nav_page", "Portfolio"))

with st.sidebar:
    st.title("PANW GCS\nNorth Star")
    st.divider()

    page = st.radio(
        "Navigation",
        _PAGES,
        index=_nav_default,
        key="nav_page",
    )

    st.divider()

    # Dynamic months from portfolio_summary (cached)
    _trend_df  = load_portfolio_trend()
    all_months = sorted(pd.to_datetime(_trend_df["month"]).dt.date.tolist())

    selected_month = st.selectbox(
        "Month",
        options=all_months,
        index=len(all_months) - 1,
        format_func=lambda x: x.strftime("%b %Y"),
    )
    month_str   = selected_month.isoformat()
    month_label = selected_month.strftime("%B %Y")

    # Load current-month accounts to populate region/industry options
    _month_accts = load_account_list(month_str)

    _region_opts = ["All Regions"] + sorted(
        _month_accts["region"].dropna().unique().tolist()
    )
    selected_region = st.selectbox("Region", _region_opts, index=0)

    selected_segment = st.selectbox(
        "Segment", ["All Segments", "Enterprise", "Mid-Market"], index=0
    )

    st.divider()
    st.markdown("**Account filters**")

    search_company = st.text_input(
        "Search company", placeholder="e.g. Apex", key="search_company"
    )

    selected_band = st.selectbox(
        "Health band",
        ["All Bands"] + BAND_ORDER,
        index=0,
    )

    _industry_opts = ["All Industries"] + sorted(
        _month_accts["industry"].dropna().unique().tolist()
    )
    selected_industry = st.selectbox("Industry", _industry_opts, index=0)


# ── Filter helpers (closures over sidebar values) ─────────────────────────────

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if search_company and "company_name" in df.columns:
        df = df[df["company_name"].str.contains(search_company, case=False, na=False)]
    if selected_band != "All Bands" and "prs_band" in df.columns:
        df = df[df["prs_band"] == selected_band]
    if selected_industry != "All Industries" and "industry" in df.columns:
        df = df[df["industry"] == selected_industry]
    if selected_segment != "All Segments" and "segment" in df.columns:
        df = df[df["segment"] == selected_segment]
    if selected_region != "All Regions" and "region" in df.columns:
        df = df[df["region"] == selected_region]
    return df


def _filters_active() -> bool:
    return bool(
        search_company
        or selected_band     != "All Bands"
        or selected_industry != "All Industries"
        or selected_segment  != "All Segments"
        or selected_region   != "All Regions"
    )


# Precompute once — all pages use these
_FA             = _filters_active()
_all_accts      = load_account_list(month_str)
_filtered_accts = apply_filters(_all_accts)
_n_total        = len(_all_accts)
_n_filtered     = len(_filtered_accts)


def _filter_banner() -> None:
    if _FA:
        st.info(f"Filters active: {_n_filtered:,} of {_n_total:,} accounts shown")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Portfolio Executive Summary
# ═══════════════════════════════════════════════════════════════════════════════

if page == "Portfolio":
    st.header(f"Portfolio Executive Summary — {month_label}")
    _filter_banner()

    if _FA:
        if _filtered_accts.empty:
            st.warning("No accounts match the current filters.")
            st.stop()
        contracted = _filtered_accts["contracted_arr"].astype(float).sum()
        realized   = _filtered_accts["realized_arr"].astype(float).sum()
        gap        = contracted - realized
        rate_pct   = round(realized / contracted * 100, 2) if contracted else 0.0
    else:
        ps = load_portfolio_summary(month_str)
        if ps.empty:
            st.warning("No portfolio data for the selected month.")
            st.stop()
        row        = ps.iloc[0]
        contracted = float(row["total_contracted_arr"])
        realized   = float(row["total_realized_arr"])
        gap        = float(row["unrealized_gap"])
        rate_pct   = float(row["realization_rate_pct"])

    # ── Section A: Metric cards ───────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Contracted ARR", _fmt(contracted))
    c2.metric("Total Realized ARR",   _fmt(realized), delta=f"{rate_pct:.1f}% realized")
    c3.metric("Unrealized Gap",       _fmt(gap),      delta=f"-{_fmt(gap)}", delta_color="inverse")
    c4.metric("Portfolio PRS",        f"{rate_pct:.1f}%")

    st.divider()

    # ── Section B: PRS band distribution ─────────────────────────────────────
    st.subheader(f"ARR by health band — {month_label}")

    if _FA:
        band_rows = [
            {
                "Band": b,
                "ARR_M": _filtered_accts.loc[_filtered_accts["prs_band"] == b, "contracted_arr"]
                         .astype(float).sum() / 1e6,
                "Accounts": int((_filtered_accts["prs_band"] == b).sum()),
                "Portfolio": "Portfolio",
            }
            for b in BAND_ORDER
        ]
    else:
        band_rows = [
            {"Band": "Green",  "ARR_M": float(row["green_arr"])  / 1e6, "Accounts": int(row["green_accounts"]),  "Portfolio": "Portfolio"},
            {"Band": "Yellow", "ARR_M": float(row["yellow_arr"]) / 1e6, "Accounts": int(row["yellow_accounts"]), "Portfolio": "Portfolio"},
            {"Band": "Orange", "ARR_M": float(row["orange_arr"]) / 1e6, "Accounts": int(row["orange_accounts"]), "Portfolio": "Portfolio"},
            {"Band": "Red",    "ARR_M": float(row["red_arr"])    / 1e6, "Accounts": int(row["red_accounts"]),    "Portfolio": "Portfolio"},
        ]

    band_df = pd.DataFrame(band_rows)
    band_df = band_df.assign(label=band_df["Accounts"].astype(str) + " accts")

    fig_band = px.bar(
        band_df, x="ARR_M", y="Portfolio", color="Band",
        orientation="h", barmode="stack", text="label",
        color_discrete_map=BAND_COLORS,
        category_orders={"Band": BAND_ORDER},
        labels={"ARR_M": "ARR ($M)", "Portfolio": ""},
    )
    fig_band.update_traces(textposition="inside", insidetextanchor="middle", textfont_size=12)
    fig_band.update_layout(
        height=160, yaxis_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=40, b=10),
    )
    st.plotly_chart(fig_band, use_container_width=True)

    st.divider()

    # ── Section C: Monthly trend ──────────────────────────────────────────────
    st.subheader("Realized ARR trend")

    if _FA:
        filt_yr = apply_filters(load_all_months_accounts())
        trend = (
            filt_yr.groupby("month")
            .agg(contracted_arr=("contracted_arr", "sum"),
                 realized_arr=("realized_arr", "sum"))
            .reset_index()
            .sort_values("month")
        )
        trend["Contracted ARR ($M)"] = trend["contracted_arr"].astype(float) / 1e6
        trend["Realized ARR ($M)"]   = trend["realized_arr"].astype(float)   / 1e6
    else:
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
    _filter_banner()

    if _filtered_accts.empty:
        st.warning("No accounts match the current filters.")
        st.stop()

    region_df = compute_region_metrics(_filtered_accts)
    region_df["Realized ARR ($M)"]   = region_df["realized_arr"].astype(float)   / 1e6
    region_df["Contracted ARR ($M)"] = region_df["contracted_arr"].astype(float) / 1e6

    contracted_total = _filtered_accts["contracted_arr"].astype(float).sum()
    realized_total   = _filtered_accts["realized_arr"].astype(float).sum()
    portfolio_avg    = (realized_total / contracted_total * 100) if contracted_total else 0.0

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
    st.subheader("Region Summary  (worst PRS first)")

    tbl = region_df.rename(columns={
        "region": "Region", "accounts": "Accounts",
        "portfolio_prs_pct": "PRS%", "at_risk_arr": "At-Risk ARR",
    })[["Region", "Accounts", "Contracted ARR ($M)", "Realized ARR ($M)", "PRS%", "At-Risk ARR"]].copy()
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
    _filter_banner()

    if _filtered_accts.empty:
        st.warning("No accounts match the current filters.")
        st.stop()

    total_counts = _all_accts.groupby("rep_id")["account_id"].count().rename("total_count")
    rep_df = compute_rep_metrics(_filtered_accts)
    rep_df = rep_df.merge(total_counts.reset_index(), on="rep_id", how="left")
    rep_df["total_count"] = rep_df["total_count"].fillna(0).astype(int)
    rep_df = rep_df.reset_index(drop=True)  # keep iloc indices stable for on_select

    st.subheader("Rep Performance  (worst PRS first)")

    tbl = rep_df.copy()
    if _FA:
        tbl["Accounts"] = tbl["account_count"].astype(str) + " / " + tbl["total_count"].astype(str)
    else:
        tbl["Accounts"] = tbl["account_count"].astype(str)

    tbl = tbl.rename(columns={
        "rep_name":             "Rep Name",
        "region":               "Region",
        "segment":              "Segment",
        "total_contracted_arr": "Contracted ARR",
        "total_realized_arr":   "Realized ARR",
        "portfolio_prs_pct":    "PRS%",
        "at_risk_arr":          "At-Risk ARR",
    })[["Rep Name", "Region", "Segment", "Accounts",
        "Contracted ARR", "Realized ARR", "PRS%", "At-Risk ARR"]]

    tbl["Contracted ARR"] = tbl["Contracted ARR"].apply(_fmt)
    tbl["Realized ARR"]   = tbl["Realized ARR"].apply(_fmt)
    tbl["At-Risk ARR"]    = tbl["At-Risk ARR"].apply(_fmt)
    tbl.insert(0, "", "→")

    rep_selection = st.dataframe(
        tbl,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="rep_table",
    )

    if rep_selection.selection.rows:
        clicked_rep = rep_df.iloc[rep_selection.selection.rows[0]]["rep_name"]
        st.session_state["rep_drill_selection"] = clicked_rep

    st.caption("Click a row to populate the drill-down below")

    st.divider()
    st.subheader("Account Detail")

    rep_name_to_id = dict(zip(rep_df["rep_name"], rep_df["rep_id"]))
    rep_name_opts  = rep_df["rep_name"].tolist()
    rep_drill_default = st.session_state.get("rep_drill_selection")
    rep_default_idx   = (
        rep_name_opts.index(rep_drill_default)
        if rep_drill_default in rep_name_opts
        else 0
    )

    selected_rep_name = st.selectbox(
        "Select Rep",
        options=rep_name_opts,
        index=rep_default_idx,
        key="rep_selectbox",
    )
    st.session_state["rep_drill_selection"] = selected_rep_name
    selected_rep_id = rep_name_to_id[selected_rep_name]

    acct = apply_filters(load_account_detail(month_str, selected_rep_id))

    if acct.empty:
        st.info("No accounts match the current filters for this rep.")
    else:
        acct = acct.copy()
        display_acct = acct.drop(columns=["account_id"]).copy()
        display_acct["realized_arr"] = display_acct["realized_arr"].apply(_fmt)
        display_acct.columns = [
            "Company", "Industry", "PRS%", "Deploy%", "Sustained%",
            "Health%", "Momentum%", "Realized ARR", "Band",
        ]

        def _band_row_style(row):
            color = BAND_COLORS.get(row["Band"])
            if color and row["Band"] in ("Red", "Orange"):
                return [f"background-color: {color}; color: white"] * len(row)
            return [""] * len(row)

        st.dataframe(
            display_acct.style.apply(_band_row_style, axis=1),
            use_container_width=True, hide_index=True,
        )

        st.divider()
        acct_name_to_id = dict(zip(acct["company_name"], acct["account_id"]))
        drill_name = st.selectbox(
            "Drill into account →", list(acct_name_to_id.keys()), key="rep_drill_select"
        )
        if st.button("Open in By Account", key="rep_drill_btn"):
            _go_to_account(acct_name_to_id[drill_name])

    st.caption(CAPTION)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — By Account
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "By Account":
    st.header(f"Account Detail — {month_label}")
    _filter_banner()

    st.subheader("Accounts")

    if _filtered_accts.empty:
        st.warning("No accounts match the current sidebar filters.")
        st.stop()

    # Sorted once; row indices here match what on_select returns
    _sorted_accts = _filtered_accts.sort_values("prs").reset_index(drop=True)
    acct_id_map   = dict(zip(_sorted_accts["company_name"], _sorted_accts["account_id"]))

    display_cols = [
        "company_name", "industry", "region", "rep_name", "segment",
        "contracted_arr", "realized_arr", "prs", "prs_band",
        "shelfware_override", "flag_overage",
    ]
    tbl_acct = _sorted_accts[display_cols].copy()
    tbl_acct.columns = [
        "Company", "Industry", "Region", "Rep", "Segment",
        "Contracted ARR", "Realized ARR", "PRS", "Band",
        "Shelfware", "Overage",
    ]
    tbl_acct["Contracted ARR"] = tbl_acct["Contracted ARR"].apply(_fmt)
    tbl_acct["Realized ARR"]   = tbl_acct["Realized ARR"].apply(_fmt)
    tbl_acct["PRS"] = tbl_acct["PRS"].round(4)
    tbl_acct.insert(0, "", "→")

    selection = st.dataframe(
        tbl_acct,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="account_table",
    )

    # Row click → update drill selection
    if selection.selection.rows:
        clicked_name = _sorted_accts.iloc[selection.selection.rows[0]]["company_name"]
        st.session_state["account_drill_selection"] = clicked_name

    st.caption(
        f"{_n_filtered:,} accounts shown · Click a row to populate the drill-down below"
    )

    st.divider()
    st.subheader("Account drill-down")

    # Navigation pre-selection from By Rep (account_id → company_name)
    if "selected_account" in st.session_state:
        _id_to_name = dict(zip(_sorted_accts["account_id"], _sorted_accts["company_name"]))
        _presel_name = _id_to_name.get(st.session_state.pop("selected_account"))
        if _presel_name:
            st.session_state["account_drill_selection"] = _presel_name

    account_options = _sorted_accts["company_name"].tolist()
    drill_default   = st.session_state.get("account_drill_selection")
    default_idx     = (
        account_options.index(drill_default)
        if drill_default in account_options
        else 0
    )

    selected_company = st.selectbox(
        "Select an account to inspect",
        options=account_options,
        index=default_idx,
        key="account_selectbox",
    )
    st.session_state["account_drill_selection"] = selected_company

    selected_acct_id = acct_id_map[selected_company]
    acct_row = _sorted_accts[_sorted_accts["account_id"] == selected_acct_id].iloc[0]

    st.divider()

    # Row 1: Metric cards
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Contracted ARR", _fmt(float(acct_row["contracted_arr"])))
    m2.metric("Realized ARR",   _fmt(float(acct_row["realized_arr"])))
    m3.metric("PRS Score",      f"{float(acct_row['prs']):.4f}")
    m4.metric("Health Band",    str(acct_row["prs_band"]))

    st.divider()

    # Row 2: PRS component waterfall
    st.subheader("PRS component contributions")

    wf_df = pd.DataFrame([
        {"Component": "Deployment × 0.40", "Contribution": float(acct_row["deployment_score"])       * 0.40},
        {"Component": "Sustained × 0.30",  "Contribution": float(acct_row["sustained_usage_score"])  * 0.30},
        {"Component": "Health × 0.20",     "Contribution": float(acct_row["technical_health_score"]) * 0.20},
        {"Component": "Expansion × 0.10",  "Contribution": float(acct_row["expansion_momentum"])     * 0.10},
    ])
    fig_wf = px.bar(
        wf_df, x="Contribution", y="Component",
        orientation="h", color="Component",
        color_discrete_map=COMPONENT_COLORS,
        text=wf_df["Contribution"].map(lambda v: f"{v:.4f}"),
        labels={"Contribution": "Weighted contribution to PRS", "Component": ""},
        range_x=[0, 1],
    )
    prs_val = float(acct_row["prs"])
    fig_wf.add_vline(
        x=prs_val, line_dash="dash", line_color="black",
        annotation_text=f"PRS {prs_val:.4f}", annotation_position="top right",
    )
    fig_wf.update_traces(textposition="inside", insidetextanchor="end", showlegend=False)
    fig_wf.update_layout(height=220, margin=dict(t=20, b=10))
    st.plotly_chart(fig_wf, use_container_width=True)

    st.divider()

    # Row 3: 12-month trend (always full year for context)
    st.subheader(f"{selected_company} — PRS trend 2024")

    trend_acct = load_account_trend(selected_acct_id)
    if not trend_acct.empty:
        trend_acct["Month"] = pd.to_datetime(trend_acct["month"]).dt.strftime("%b")
        fig_atrend = px.line(
            trend_acct, x="Month", y=["prs", "deployment_score"],
            markers=True,
            color_discrete_map={"prs": "#1D9E75", "deployment_score": "#4A90D9"},
            labels={"value": "Score (0–1)", "variable": ""},
        )
        fig_atrend.update_layout(
            yaxis_range=[0, 1],
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=30, b=10),
        )
        fig_atrend.for_each_trace(lambda t: t.update(
            name={"prs": "PRS", "deployment_score": "Deployment Score"}.get(t.name, t.name)
        ))
        st.plotly_chart(fig_atrend, use_container_width=True)

    st.divider()

    # Row 4: Flags
    st.subheader("Flags")

    badge_parts = []
    if acct_row.get("shelfware_override"):
        badge_parts.append(
            f'<span style="background:{BAND_COLORS["Red"]};color:white;'
            f'padding:5px 14px;border-radius:5px;font-weight:bold;margin-right:8px">'
            f'⚠ Shelfware</span>'
        )
    if acct_row.get("flag_overage"):
        badge_parts.append(
            f'<span style="background:{BAND_COLORS["Green"]};color:white;'
            f'padding:5px 14px;border-radius:5px;font-weight:bold;margin-right:8px">'
            f'✓ Expansion Ready</span>'
        )
    months_in_window = int(acct_row.get("months_in_window", 0) or 0)
    badge_parts.append(
        f'<span style="background:#4A90D9;color:white;'
        f'padding:5px 14px;border-radius:5px;font-weight:bold">'
        f'Months in window: {months_in_window}</span>'
    )
    if not acct_row.get("shelfware_override") and not acct_row.get("flag_overage"):
        badge_parts.insert(0,
            f'<span style="background:#6c757d;color:white;'
            f'padding:5px 14px;border-radius:5px;font-weight:bold;margin-right:8px">'
            f'No active flags</span>'
        )

    st.markdown(" ".join(badge_parts), unsafe_allow_html=True)

    st.caption(CAPTION)
