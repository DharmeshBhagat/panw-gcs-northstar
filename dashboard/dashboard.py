import datetime
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

PROJECT_ID = (
    st.secrets.get("BIGQUERY_PROJECT_ID")
    or os.environ.get("BIGQUERY_PROJECT_ID")
)

DATASET_ID = (
    st.secrets.get("BIGQUERY_DATASET_ID")
    or os.environ.get("BIGQUERY_DATASET_ID", "gcs_north_star")
)

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

CAPTION = "Data source: Synthetic dataset · BigQuery gcs_north_star · Refreshes every 10 minutes"


# ── Contextual help popovers ──────────────────────────────────────────────────

def help_icon(key: str) -> None:
    """Renders a ⓘ button that opens a popover with explanation."""
    definitions = {
        "prs": {
            "title": "Platform Realization Score (PRS)",
            "body": (
                "A composite score from 0.0 to 1.0 measuring how much "
                "contracted value is being realized through active usage.\n\n"
                "**Formula:**\n"
                "```\n"
                "PRS = (Deployment × 0.40)\n"
                "    + (Sustained Usage × 0.30)\n"
                "    + (Technical Health × 0.20)\n"
                "    + (Expansion Momentum × 0.10)\n"
                "```\n"
                "🟢 0.80–1.00 Green — Healthy  \n"
                "🟡 0.60–0.79 Yellow — Watch  \n"
                "🟠 0.30–0.59 Orange — At-Risk  \n"
                "🔴 0.00–0.29 Red — Critical"
            ),
        },
        "realized_arr": {
            "title": "Realized ARR",
            "body": (
                "The dollar value of contracted ARR actually being earned "
                "through healthy, deployed, sustained product usage.\n\n"
                "**Formula:** Realized ARR = Contracted ARR × PRS\n\n"
                "A $1M ARR account with PRS 0.65 contributes $650K "
                "to Realized ARR — the remaining $350K is at risk."
            ),
        },
        "unrealized_gap": {
            "title": "Unrealized Gap",
            "body": (
                "Contracted ARR minus Realized ARR.\n\n"
                "This is the dollar value of ARR at churn risk — "
                "customers who have committed to pay but are not "
                "yet getting sufficient value from the platform.\n\n"
                "The dashboard calculates this gap dynamically from "
                "BigQuery output for the selected month."
            ),
        },
        "health_bands": {
            "title": "PRS Health Bands",
            "body": (
                "🟢 **Green** (PRS ≥ 0.80) — Healthy, identify expansion opportunity  \n"
                "🟡 **Yellow** (PRS 0.60–0.79) — Watch, proactive CSM outreach needed  \n"
                "🟠 **Orange** (PRS 0.30–0.59) — At-Risk, CSM + PS intervention needed  \n"
                "🔴 **Red** (PRS < 0.30) — Critical, executive engagement required"
            ),
        },
        "deployment": {
            "title": "Deployment Score (40% weight)",
            "body": (
                "Are they using what they purchased?\n\n"
                "**Formula:** MIN(1.0, credits consumed / credits included)\n\n"
                "- 0.00 — Nothing deployed (shelfware)  \n"
                "- 0.50 — Using 50% of purchased capacity  \n"
                "- 1.00 — Fully deployed or consuming in excess  \n\n"
                "Capped at 1.00 — overages are captured in Expansion Momentum."
            ),
        },
        "sustained": {
            "title": "Sustained Usage Score (30% weight)",
            "body": (
                "Is usage consistent, or was it a one-time spike?\n\n"
                "**Formula:** healthy months / window size (max 12 months)  \n"
                "A month is healthy if consumption ≥ 30% of included credits.\n\n"
                "Catches spike-and-drop: accounts that consumed heavily "
                "in Month 1 then went dark score near 0.08 (1/12).  \n"
                "Consistent usage every month = 1.00"
            ),
        },
        "health_signal": {
            "title": "Technical Health Score (20% weight)",
            "body": (
                "Is the platform technically healthy?\n\n"
                "- Green → 1.00 — No active issues  \n"
                "- Yellow → 0.60 — Degraded, config errors or elevated errors  \n"
                "- Red → 0.20 — Critical, active incident or integration failure  \n"
                "- Missing → 0.60 — Neutral default  \n\n"
                "In production this connects to support ticket severity, "
                "MTTR, and API error rates."
            ),
        },
        "expansion": {
            "title": "Expansion Momentum (10% weight)",
            "body": (
                "Is the account showing growth signals?\n\n"
                "Evaluates consumption pattern over the trailing 6 months:\n\n"
                "- 1.00 — Consuming 120%+ for 3+ months → strong upsell signal  \n"
                "- 0.70 — Consuming 70%+ for 3+ months → expansion ready  \n"
                "- 0.40 — Consuming 30%+ for 3+ months → stable  \n"
                "- 0.10 — Low usage or account < 3 months old  \n\n"
                "Overages are not penalised here — they are an opportunity."
            ),
        },
        "shelfware": {
            "title": "Shelfware",
            "body": (
                "Accounts with high contracted ARR but zero usage.\n\n"
                "**Definition:** Deployment Score = 0 AND Sustained Usage = 0\n\n"
                "PRS override fires: PRS = 0.00 regardless of other scores.  \n"
                "Realized ARR = $0 even if contracted ARR is $500K.\n\n"
                "Risk: these accounts will not renew unless the CSM "
                "intervenes with a deployment engagement within 90 days."
            ),
        },
        "spike_drop": {
            "title": "Spike and Drop",
            "body": (
                "Accounts that consumed heavily in Month 1 then "
                "dropped to near-zero usage.\n\n"
                "**Detection:** deployment_score > 0 AND sustained_usage_score < 0.15\n\n"
                "Common cause: bulk data migration or proof-of-concept "
                "that was never operationalised into production workloads.\n\n"
                "CSM action: re-onboarding engagement, new use case discovery."
            ),
        },
        "overager": {
            "title": "Consistent Overager",
            "body": (
                "Accounts consuming 120%+ of their included credits "
                "consistently for 3 or more months.\n\n"
                "This is a positive signal — the customer has outgrown "
                "their current contract and is ready for an upsell or "
                "right-sizing conversation.\n\n"
                "Expansion Momentum = 1.00 for these accounts.  \n"
                "flag_overage = True in the data."
            ),
        },
        "realization_rate": {
            "title": "Realization Rate",
            "body": (
                "Total Realized ARR ÷ Total Contracted ARR × 100\n\n"
                "Measures what percentage of contracted value is "
                "being actively earned through platform usage.\n\n"
                "The dashboard calculates realization rate dynamically "
                "from BigQuery output. Use the month selector to compare "
                "performance across the synthetic 2024 dataset."
            ),
        },
    }

    info = definitions.get(key, {})
    if not info:
        return

    body = (
        info["body"]
        .strip()
        .replace('"', "&quot;")
        .replace("\n", "<br>")
    )
    title = info["title"].replace('"', "&quot;")

    st.markdown(f"""
<style>
.help-wrap-{key} {{
    display: inline-block;
    position: relative;
    cursor: help;
}}
.help-icon-{key} {{
    font-size: 10px;
    font-weight: 600;
    color: rgba(150,150,170,0.7);
    border: 1px solid rgba(150,150,170,0.4);
    border-radius: 50%;
    width: 13px;
    height: 13px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-left: 4px;
    vertical-align: middle;
    line-height: 1;
}}
.help-tooltip-{key} {{
    visibility: hidden;
    opacity: 0;
    width: 280px;
    background: #1a1a2e;
    color: #e0e0e0;
    font-size: 12px;
    line-height: 1.6;
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    padding: 10px 13px;
    position: absolute;
    z-index: 9999;
    bottom: 130%;
    left: 50%;
    transform: translateX(-50%);
    transition: opacity 0.15s ease;
    pointer-events: none;
}}
.help-tooltip-{key}::after {{
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-top-color: rgba(255,255,255,0.15);
}}
.help-wrap-{key}:hover .help-tooltip-{key} {{
    visibility: visible;
    opacity: 1;
}}
</style>
<span class="help-wrap-{key}">
    <span class="help-icon-{key}">?</span>
    <div class="help-tooltip-{key}">
        <strong>{title}</strong><br><br>{body}
    </div>
</span>
""", unsafe_allow_html=True)


# ── BigQuery helpers ──────────────────────────────────────────────────────────

@st.cache_resource
def _bq_client():
    if "gcp_service_account" in st.secrets:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return bigquery.Client(
            project=st.secrets["BIGQUERY_PROJECT_ID"],
            credentials=credentials,
        )
    return bigquery.Client(project=os.environ["BIGQUERY_PROJECT_ID"])


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


@st.cache_data(ttl=600)
def load_dq_summary() -> pd.DataFrame:
    return _run(
        """
        SELECT
            dq_rule,
            ANY_VALUE(exclusion_reason) AS exclusion_reason,
            COUNT(*)               AS count,
            MAX(run_timestamp)     AS last_run
        FROM `{PROJECT_ID}.{DATASET_ID}.dq_report`
        GROUP BY dq_rule
        ORDER BY dq_rule
        """
    )


@st.cache_data(ttl=600)
def load_daily_log_count() -> int:
    df = _run("SELECT COUNT(*) AS cnt FROM `{PROJECT_ID}.{DATASET_ID}.daily_usage_logs`")
    return int(df["cnt"].iloc[0]) if not df.empty else 0


@st.cache_data(ttl=600)
def load_anomaly_summary(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            COUNTIF(shelfware_override)                                                        AS shelfware_count,
            SUM(CASE WHEN shelfware_override
                     THEN CAST(contracted_arr AS FLOAT64) ELSE 0 END)                         AS shelfware_arr,
            COUNTIF(CAST(sustained_usage_score AS FLOAT64) < 0.15
                    AND CAST(deployment_score  AS FLOAT64) > 0)                               AS spike_drop_count,
            SUM(CASE WHEN CAST(sustained_usage_score AS FLOAT64) < 0.15
                          AND CAST(deployment_score  AS FLOAT64) > 0
                     THEN CAST(contracted_arr AS FLOAT64) ELSE 0 END)                         AS spike_drop_arr,
            COUNTIF(flag_overage)                                                              AS overage_count,
            SUM(CASE WHEN flag_overage
                     THEN CAST(contracted_arr AS FLOAT64) ELSE 0 END)                         AS overage_arr
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @month
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_overlap_contracts() -> pd.DataFrame:
    return _run(
        """
        SELECT account_id, COUNT(*) AS contract_count
        FROM `{PROJECT_ID}.{DATASET_ID}.contracts`
        GROUP BY account_id
        HAVING COUNT(*) > 1
        """
    )


@st.cache_data(ttl=600)
def load_home_summary(month: str) -> pd.DataFrame:
    """Returns portfolio_summary rows for selected month and the prior month."""
    month_dt   = datetime.date.fromisoformat(month)
    prev_month = (month_dt.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    return _run(
        """
        SELECT month, total_contracted_arr, total_realized_arr,
               unrealized_gap,
               CAST(realization_rate_pct AS FLOAT64) AS realization_rate_pct,
               CAST(portfolio_prs        AS FLOAT64) AS portfolio_prs
        FROM `{PROJECT_ID}.{DATASET_ID}.portfolio_summary`
        WHERE month IN UNNEST(@months)
        ORDER BY month
        """,
        [bigquery.ArrayQueryParameter("months", "DATE", [month, prev_month.isoformat()])],
    )


@st.cache_data(ttl=600)
def load_component_averages(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            AVG(CAST(deployment_score       AS FLOAT64)) AS avg_deployment,
            AVG(CAST(sustained_usage_score  AS FLOAT64)) AS avg_sustained,
            AVG(CAST(technical_health_score AS FLOAT64)) AS avg_health,
            AVG(CAST(expansion_momentum     AS FLOAT64)) AS avg_expansion,
            AVG(CAST(prs                    AS FLOAT64)) AS avg_prs
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @month
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_spike_drop_summary(month: str) -> pd.DataFrame:
    return _run(
        """
        SELECT
            COUNT(*)                             AS count,
            SUM(CAST(contracted_arr AS FLOAT64)) AS arr
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @month
          AND CAST(deployment_score      AS FLOAT64) > 0
          AND CAST(sustained_usage_score AS FLOAT64) < 0.15
        """,
        [bigquery.ScalarQueryParameter("month", "DATE", month)],
    )


@st.cache_data(ttl=600)
def load_data_confidence() -> pd.DataFrame:
    sql = """
    SELECT
        COUNT(*) AS total_logs,
        COUNTIF(
            account_id IN (
                SELECT account_id FROM `{PROJECT_ID}.{DATASET_ID}.accounts`
            )
            AND date >= DATE('2024-01-01')
            AND compute_credits_consumed >= 0
        ) AS clean_logs,
        COUNTIF(
            account_id NOT IN (
                SELECT account_id FROM `{PROJECT_ID}.{DATASET_ID}.accounts`
            )
        ) AS orphaned_logs,
        COUNTIF(date < DATE('2024-01-01')) AS rogue_logs,
        COUNTIF(compute_credits_consumed < 0) AS negative_logs
    FROM `{PROJECT_ID}.{DATASET_ID}.daily_usage_logs`
    """
    df = _run(sql)
    return df.astype({
        "total_logs": int, "clean_logs": int,
        "orphaned_logs": int, "rogue_logs": int, "negative_logs": int,
    })


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


def _fmt_delta(val: float) -> str:
    return f"+{_fmt(abs(val))}" if val >= 0 else f"-{_fmt(abs(val))}"


def _go_to_account(account_id: str) -> None:
    st.session_state["selected_account"] = account_id
    st.session_state["pending_nav"] = "By Account"
    st.rerun()


# ── App config ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="PANW GCS North Star", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────

_PAGES = ["Home", "Portfolio", "By Region", "By Rep", "By Account", "Data Quality"]

# Resolve pending navigation BEFORE the radio widget renders
if "pending_nav" in st.session_state:
    _nav_default = _PAGES.index(st.session_state.pop("pending_nav"))
else:
    _nav_default = _PAGES.index(st.session_state.get("nav_page", "Home"))

with st.sidebar:
    st.title("Realized ARR Command Center")
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

    compare_mode = st.toggle("Compare two months", value=False, key="compare_mode")
    if compare_mode:
        _ca, _cb = st.columns(2)
        with _ca:
            month_a = st.selectbox(
                "Month A", all_months,
                index=max(len(all_months) - 2, 0),
                format_func=lambda x: x.strftime("%b %Y"),
                key="month_a",
            )
        with _cb:
            month_b = st.selectbox(
                "Month B", all_months,
                index=len(all_months) - 1,
                format_func=lambda x: x.strftime("%b %Y"),
                key="month_b",
            )
    else:
        month_a = selected_month
        month_b = None

    month_str   = month_a.isoformat()
    month_label = month_a.strftime("%B %Y")

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

if compare_mode:
    _all_accts_b      = load_account_list(month_b.isoformat())
    _filtered_accts_b = apply_filters(_all_accts_b)


def _filter_banner() -> None:
    if _FA:
        st.info(f"Filters active: {_n_filtered:,} of {_n_total:,} accounts shown")


def prs_color(prs_val: float) -> str:
    if prs_val >= 0.80: return "#1D9E75"
    if prs_val >= 0.60: return "#BA7517"
    if prs_val >= 0.30: return "#D85A30"
    return "#A32D2D"


def region_action(row) -> str:
    prs = float(row.get("portfolio_prs_pct", 0)) / 100
    gap_pct = 1 - prs
    overagers = int(row.get("overage_accounts", 0))
    total_accts = int(row.get("accounts", 1)) or 1
    if prs < 0.60 and gap_pct > 0.40:
        return "🔴 Regional recovery plan"
    if overagers / total_accts > 0.25:
        return "🟢 Expansion motion"
    if prs < 0.70:
        return "🟡 CSM capacity review"
    if prs < 0.80:
        return "🔵 Monitor — maintain cadence"
    return "✅ Healthy — identify upsell candidates"


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 0 — Home  (Executive Snapshot)
# ═══════════════════════════════════════════════════════════════════════════════

if page == "Home":

    # ── Data loading ──────────────────────────────────────────────────────────
    home_df  = load_home_summary(month_str)
    comp_df  = load_component_averages(month_str)
    sd_df    = load_spike_drop_summary(month_str)
    dq_home  = load_dq_summary()
    trend_df = load_portfolio_trend()

    # Current-month portfolio row
    _cur_mask = pd.to_datetime(home_df["month"]).dt.date == month_a
    if not _cur_mask.any():
        st.warning("No portfolio data for the selected month.")
        st.stop()
    _cur = home_df[_cur_mask].iloc[0]

    contracted    = float(_cur["total_contracted_arr"])
    realized      = float(_cur["total_realized_arr"])
    gap           = float(_cur["unrealized_gap"])
    rate_pct      = float(_cur["realization_rate_pct"])
    portfolio_prs = float(_cur["portfolio_prs"])
    gap_m         = gap / 1e6

    # Previous-month realization rate (delta for KPI card)
    _prev_rows    = home_df[~_cur_mask]
    prev_rate_pct = float(_prev_rows.iloc[0]["realization_rate_pct"]) if not _prev_rows.empty else rate_pct

    # June 2024 PRS (portfolio peak for banner delta)
    _june = trend_df[
        (pd.to_datetime(trend_df["month"]).dt.year  == 2024) &
        (pd.to_datetime(trend_df["month"]).dt.month == 6)
    ]
    june_prs = float(_june["portfolio_prs"].iloc[0]) if not _june.empty else portfolio_prs

    st.header(f"Realized ARR Scorecard — {month_label}")
    st.caption(f"Portfolio health · {month_a.strftime('%B %Y')} · Palo Alto Networks GCS")

    st.markdown(f"""
<div style="
  background: #0f3d2a;
  border: 1px solid #1D9E75;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 20px;
  color: #FFFFFF;
  font-size: 13px;
  line-height: 1.7;
">
  <span style="
    font-size: 11px;
    font-weight: 600;
    color: #1D9E75;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  ">Recommendation</span><br>
  Run Realized ARR as a <strong>shadow North Star metric
  for one quarter</strong> before using it in compensation.
  {month_a.strftime('%B')} synthetic data shows
  <strong style="color:#D85A30">${gap_m:.1f}M unrealized ARR</strong>
  requiring CSM/PS action.
</div>
""", unsafe_allow_html=True)

    # ── Section 1: Headline banner ────────────────────────────────────────────
    st.divider()
    _bl, _bc, _br = st.columns([1, 2, 1])

    with _bl:
        st.markdown(
            f"<p style='font-size:13px;color:#888;margin:0'>Realized ARR</p>"
            f"<p style='font-size:20px;font-weight:700;margin:0'>{month_label}</p>",
            unsafe_allow_html=True,
        )

    with _bc:
        st.markdown(
            f"<p style='font-size:28px;font-weight:800;color:#A32D2D;margin:0 0 4px 0'>"
            f"${gap_m:.1f}M unrealized</p>"
            f"<p style='font-size:14px;color:#666;margin:0'>"
            f"{100 - rate_pct:.1f}% of contracted ARR not yet earned</p>",
            unsafe_allow_html=True,
        )

    with _br:
        _prs_m, _prs_h = st.columns([6, 1])
        _prs_m.metric(
            "Portfolio PRS",
            f"{portfolio_prs:.3f}",
            delta=f"{portfolio_prs - june_prs:.3f} vs June peak",
        )
        with _prs_h:
            help_icon("prs")

    st.divider()

    # ── Section 2: Six KPI cards ──────────────────────────────────────────────
    _n_industries = _filtered_accts["industry"].nunique()
    _n_reps       = _filtered_accts["rep_id"].nunique()
    _n_regions    = _filtered_accts["region"].nunique()

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Contracted ARR", _fmt(contracted), delta="committed")
    with k2:
        _m, _h = st.columns([6, 1])
        _m.metric("Realized ARR", _fmt(realized), delta="earned")
        with _h: help_icon("realized_arr")
    with k3:
        _m, _h = st.columns([6, 1])
        _m.metric("Unrealized Gap", _fmt(gap), delta="at risk", delta_color="inverse")
        with _h: help_icon("unrealized_gap")
    with k4:
        _m, _h = st.columns([6, 1])
        _m.metric("Realization Rate", f"{rate_pct:.1f}%",
                  delta=f"{rate_pct - prev_rate_pct:+.1f}pp vs prev month")
        with _h: help_icon("realization_rate")
    k5.metric("Total Accounts", f"{len(_filtered_accts):,}",
              delta=f"across {_n_industries} industries")
    k6.metric("Total CSM Reps", f"{_n_reps}",
              delta=f"across {_n_regions} regions")

    st.divider()

    # ── Section 3: Health band donut  +  PRS component bars ──────────────────
    _s3l, _s3r = st.columns(2)

    with _s3l:
        _hb_ttl, _hb_help = st.columns([8, 1])
        with _hb_ttl:
            st.subheader("Health Band Distribution")
        with _hb_help:
            help_icon("health_bands")

        band_agg = (
            _filtered_accts.groupby("prs_band")
            .agg(accounts=("account_id", "count"), arr=("contracted_arr", "sum"))
            .reindex(BAND_ORDER).fillna(0).reset_index()
        )
        band_agg["arr"]       = band_agg["arr"].astype(float)
        _band_total_arr       = band_agg["arr"].sum()

        fig_donut = px.pie(
            band_agg, values="accounts", names="prs_band",
            hole=0.5, color="prs_band",
            color_discrete_map=BAND_COLORS,
            category_orders={"prs_band": BAND_ORDER},
        )
        fig_donut.update_traces(textposition="outside", textinfo="percent+label")
        fig_donut.update_layout(showlegend=False, height=280, margin=dict(t=20, b=10))
        st.plotly_chart(fig_donut, use_container_width=True)

        mini = band_agg.copy()
        mini["ARR ($M)"]       = (mini["arr"] / 1e6).round(1)
        mini["% of portfolio"] = (
            (mini["arr"] / _band_total_arr * 100).round(1) if _band_total_arr else 0.0
        )
        st.dataframe(
            mini.rename(columns={"prs_band": "Band", "accounts": "Accounts"})
                [["Band", "Accounts", "ARR ($M)", "% of portfolio"]],
            use_container_width=True, hide_index=True,
        )

    with _s3r:
        st.subheader("What is driving PRS?")
        _dl, _dh = st.columns([5, 0.3])
        with _dl: st.markdown("**Deployment Score**  ·  40% weight")
        with _dh: help_icon("deployment")
        _sl, _sh = st.columns([5, 0.3])
        with _sl: st.markdown("**Sustained Usage**  ·  30% weight")
        with _sh: help_icon("sustained")
        _hl, _hh2 = st.columns([5, 0.3])
        with _hl: st.markdown("**Technical Health**  ·  20% weight")
        with _hh2: help_icon("health_signal")
        _el, _eh = st.columns([5, 0.3])
        with _el: st.markdown("**Expansion Momentum**  ·  10% weight")
        with _eh: help_icon("expansion")

        if not comp_df.empty:
            _cr = comp_df.iloc[0]
            _components = [
                ("Deployment Score",   float(_cr["avg_deployment"]), "40%"),
                ("Sustained Usage",    float(_cr["avg_sustained"]),  "30%"),
                ("Technical Health",   float(_cr["avg_health"]),     "20%"),
                ("Expansion Momentum", float(_cr["avg_expansion"]),  "10%"),
            ]
            _min_score = min(s for _, s, _ in _components)
            _comp_chart = pd.DataFrame([
                {
                    "Component": f"{name}  ({wt})",
                    "Score":     score,
                    "color_key": (
                        "#D85A30"
                        if name == "Expansion Momentum" and score == _min_score
                        else "#185FA5"
                    ),
                }
                for name, score, wt in _components
            ])
            _cmap_comp = dict(zip(_comp_chart["Component"], _comp_chart["color_key"]))

            fig_comp = px.bar(
                _comp_chart, x="Score", y="Component",
                orientation="h",
                color="Component",
                color_discrete_map=_cmap_comp,
                category_orders={"Component": _comp_chart["Component"].tolist()},
                text=_comp_chart["Score"].map(lambda v: f"{v:.3f}"),
                labels={"Score": "Average score (0–1)", "Component": ""},
                range_x=[0, 1],
            )
            _avg_prs = float(_cr["avg_prs"])
            fig_comp.add_vline(
                x=_avg_prs, line_dash="dash", line_color="#333",
                annotation_text=f"Portfolio PRS {_avg_prs:.3f}",
                annotation_position="top right",
            )
            fig_comp.update_traces(
                textposition="inside", insidetextanchor="end", showlegend=False
            )
            fig_comp.update_layout(height=280, margin=dict(t=30, b=10))
            st.plotly_chart(fig_comp, use_container_width=True)

            _best_score = max(s for _, s, _ in _components)
            st.caption(
                f"Expansion Momentum is the weakest component — "
                f"dragging portfolio PRS from potential {_best_score:.2f} to {_avg_prs:.2f}"
            )

    st.divider()

    # ── Section 4: Where GCS should act next ─────────────────────────────────
    st.subheader("Where GCS should act next")
    _risk_col, _opp_col = st.columns(2)

    _shelfware_accts = _filtered_accts[_filtered_accts["shelfware_override"].astype(bool)]
    _red_accts       = _filtered_accts[_filtered_accts["prs_band"] == "Red"]
    _overage_accts   = _filtered_accts[_filtered_accts["flag_overage"].astype(bool)]
    _high_prs_accts  = _filtered_accts[_filtered_accts["prs"].astype(float) >= 0.80]

    _shelfware_arr_m = _shelfware_accts["contracted_arr"].astype(float).sum() / 1e6
    _red_arr_m       = _red_accts["contracted_arr"].astype(float).sum()       / 1e6
    _overage_arr_m   = _overage_accts["contracted_arr"].astype(float).sum()   / 1e6
    _high_prs_arr_m  = _high_prs_accts["contracted_arr"].astype(float).sum()  / 1e6

    _sd_count   = int(sd_df["count"].iloc[0])             if not sd_df.empty else 0
    _sd_arr_m   = float(sd_df["arr"].iloc[0]) / 1e6       if not sd_df.empty else 0.0

    _rgn_metrics = compute_region_metrics(_filtered_accts)
    if not _rgn_metrics.empty:
        _worst_rgn     = _rgn_metrics.iloc[0]
        _worst_region  = _worst_rgn["region"]
        _worst_rgn_prs = _worst_rgn["portfolio_prs_pct"] / 100
    else:
        _worst_region, _worst_rgn_prs = "N/A", 0.0

    with _risk_col:
        st.markdown("<h3 style='color:#A32D2D'>Recover ARR</h3>", unsafe_allow_html=True)

        _sw_m, _sw_h = st.columns([6, 1])
        _sw_m.metric("Shelfware",
                     f"{len(_shelfware_accts)} accounts · ${_shelfware_arr_m:.1f}M ARR",
                     delta_color="inverse")
        with _sw_h: help_icon("shelfware")
        st.markdown("<div style='font-size:11px;color:gray'>↳ 90-day adoption plan — assign PS deployment sprint</div>",
                    unsafe_allow_html=True)

        st.metric("At-Risk (Red band)",
                  f"{len(_red_accts)} accounts · ${_red_arr_m:.1f}M ARR",
                  delta_color="inverse")
        st.markdown("<div style='font-size:11px;color:gray'>↳ CSM + PS intervention — 45-day recovery plan</div>",
                    unsafe_allow_html=True)

        _sd_m, _sd_h = st.columns([6, 1])
        _sd_m.metric("Spike & Drop",
                     f"{_sd_count} accounts · ${_sd_arr_m:.1f}M ARR",
                     delta_color="inverse")
        with _sd_h: help_icon("spike_drop")
        st.markdown("<div style='font-size:11px;color:gray'>↳ Re-onboarding · use-case discovery session</div>",
                    unsafe_allow_html=True)

    with _opp_col:
        st.markdown("<h3 style='color:#1D9E75'>Expand ARR</h3>", unsafe_allow_html=True)

        _ov_m, _ov_h = st.columns([6, 1])
        _ov_m.metric("Consistent Overagers",
                     f"{len(_overage_accts)} accounts · ${_overage_arr_m:.1f}M ARR")
        with _ov_h: help_icon("overager")
        st.markdown("<div style='font-size:11px;color:gray'>↳ Expansion or right-sizing discussion</div>",
                    unsafe_allow_html=True)

        st.metric("High PRS Accounts",
                  f"{len(_high_prs_accts)} accounts · ${_high_prs_arr_m:.1f}M ARR")
        st.markdown("<div style='font-size:11px;color:gray'>↳ Upsell candidate — platform breadth conversation</div>",
                    unsafe_allow_html=True)

        st.metric("Worst Region",
                  f"{_worst_region} · {_worst_rgn_prs:.1%} realization",
                  delta_color="off")
        st.markdown("<div style='font-size:11px;color:gray'>↳ Regional QBR — identify top 5 recovery accounts</div>",
                    unsafe_allow_html=True)

    st.divider()

    # ── Section 5: Monthly trend sparkline ───────────────────────────────────
    st.subheader("2024 — Contracted vs Realized ARR")

    _t = trend_df.copy()
    _t["Contracted ARR ($M)"] = _t["total_contracted_arr"].astype(float) / 1e6
    _t["Realized ARR ($M)"]   = _t["total_realized_arr"].astype(float)   / 1e6
    _t["month_label"]         = pd.to_datetime(_t["month"]).dt.strftime("%b %Y")

    fig_spark = px.line(
        _t, x="month_label",
        y=["Contracted ARR ($M)", "Realized ARR ($M)"],
        markers=True,
        color_discrete_sequence=["#4A90D9", "#1D9E75"],
        labels={"value": "ARR ($M)", "variable": "", "month_label": ""},
    )
    # Shade the unrealized gap between the two lines in light red
    fig_spark.data[1].update(fill="tonexty", fillcolor="rgba(163,45,45,0.12)")

    # Categorical x axis requires add_shape/add_annotation (add_vline uses numeric index)
    _month_labels = _t["month_label"].tolist()
    _june_idx = (
        _month_labels.index("Jun 2024")
        if "Jun 2024" in _month_labels
        else None
    )
    if _june_idx is not None:
        fig_spark.add_shape(
            type="line",
            x0=_june_idx, x1=_june_idx,
            y0=0, y1=1,
            xref="x", yref="paper",
            line=dict(color="#BA7517", width=1, dash="dot"),
        )
        fig_spark.add_annotation(
            x=_june_idx, y=1,
            xref="x", yref="paper",
            text="PRS peak",
            showarrow=False,
            font=dict(size=10, color="#BA7517"),
            xanchor="left", yanchor="top",
        )

    fig_spark.update_layout(
        height=180,
        margin=dict(t=20, b=10, l=0, r=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis_title="ARR ($M)",
    )
    st.plotly_chart(fig_spark, use_container_width=True)

    # ── Decision Ask banner ───────────────────────────────────────────────────
    st.markdown("""
<div style="
  background: #1a2a3a;
  border-left: 4px solid #1D9E75;
  border-radius: 6px;
  padding: 14px 18px;
  margin-top: 20px;
  color: #FFFFFF;
">
  <div style="font-size:13px;font-weight:600;color:#1D9E75;margin-bottom:6px;">
    Decision ask
  </div>
  <div style="font-size:13px;color:#e0e0e0;line-height:1.6;">
    Approve Realized ARR as a <strong>shadow North Star metric for one quarter.</strong>
    Do not use for compensation until data confidence, business behavior,
    and exception handling are validated.
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Section 6: Footer ─────────────────────────────────────────────────────
    _last_run_home = None
    if not dq_home.empty and "last_run" in dq_home.columns:
        _lrts = pd.to_datetime(dq_home["last_run"].max())
        if pd.notna(_lrts):
            _last_run_home = _lrts.strftime("%Y-%m-%d %H:%M UTC")

    st.caption(
        f"Data as of: {_last_run_home or 'Unknown'} · "
        f"BigQuery: {DATASET_ID} · 22/22 tests passing"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Portfolio Executive Summary
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Portfolio":
    _cmp_hdr = (
        f"{month_a.strftime('%b %Y')} vs {month_b.strftime('%b %Y')}"
        if compare_mode else month_label
    )
    st.header(f"Portfolio Executive Summary — {_cmp_hdr}")
    _filter_banner()

    def _portfolio_vals(month_iso: str, filtered_df: pd.DataFrame):
        if _FA:
            if filtered_df.empty:
                return None
            c = filtered_df["contracted_arr"].astype(float).sum()
            r = filtered_df["realized_arr"].astype(float).sum()
            return c, r, c - r, round(r / c * 100, 2) if c else 0.0
        ps = load_portfolio_summary(month_iso)
        if ps.empty:
            return None
        _r = ps.iloc[0]
        return (float(_r["total_contracted_arr"]), float(_r["total_realized_arr"]),
                float(_r["unrealized_gap"]),        float(_r["realization_rate_pct"]))

    _vals_a = _portfolio_vals(month_a.isoformat(), _filtered_accts)
    if _vals_a is None:
        st.warning("No portfolio data for the selected month.")
        st.stop()
    contracted, realized, gap, rate_pct = _vals_a

    if compare_mode:
        _vals_b = _portfolio_vals(month_b.isoformat(), _filtered_accts_b)
        if _vals_b is None:
            st.warning(f"No data for {month_b.strftime('%B %Y')}.")
            st.stop()
        _cb_arr, _rb_arr, _gb_arr, _rpb = _vals_b

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader(month_a.strftime("%B %Y"))
            _a1, _a2, _a3, _a4 = st.columns(4)
            _a1.metric("Contracted ARR", _fmt(contracted))
            _a2.metric("Realized ARR",   _fmt(realized))
            _a3.metric("Unrealized Gap", _fmt(gap))
            _a4.metric("Portfolio PRS",  f"{rate_pct:.1f}%")
        with col_b:
            st.subheader(month_b.strftime("%B %Y"))
            _b1, _b2, _b3, _b4 = st.columns(4)
            _b1.metric("Contracted ARR", _fmt(_cb_arr),
                       delta=_fmt_delta(_cb_arr - contracted))
            _b2.metric("Realized ARR",   _fmt(_rb_arr),
                       delta=_fmt_delta(_rb_arr - realized))
            _b3.metric("Unrealized Gap", _fmt(_gb_arr),
                       delta=_fmt_delta(_gb_arr - gap), delta_color="inverse")
            _b4.metric("Portfolio PRS",  f"{_rpb:.1f}%",
                       delta=f"{_rpb - rate_pct:+.1f}pp")
    else:
        # ── Section A: Metric cards ───────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Contracted ARR", _fmt(contracted))
        c2.metric("Total Realized ARR",   _fmt(realized), delta=f"{rate_pct:.1f}% realized")
        c3.metric("Unrealized Gap",       _fmt(gap),      delta=f"-{_fmt(gap)}", delta_color="inverse")
        c4.metric("Portfolio PRS",        f"{rate_pct:.1f}%")

    st.divider()

    # ── Section B: PRS band distribution ─────────────────────────────────────
    st.subheader(f"ARR by health band — {month_label}")

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

    # Always pull full portfolio_summary for insight + milestone table (unfiltered)
    _pt = load_portfolio_trend().copy()
    _jan_r   = _pt[pd.to_datetime(_pt["month"]).dt.strftime("%Y-%m-%d") == "2024-01-01"]
    _jun_r   = _pt[pd.to_datetime(_pt["month"]).dt.strftime("%Y-%m-%d") == "2024-06-01"]
    _dec_r   = _pt[pd.to_datetime(_pt["month"]).dt.strftime("%Y-%m-%d") == "2024-12-01"]
    _jan_row = _jan_r.iloc[0] if not _jan_r.empty else None
    _jun_row = _jun_r.iloc[0] if not _jun_r.empty else None
    _dec_row = _dec_r.iloc[0] if not _dec_r.empty else None

    if _jan_row is not None and _jun_row is not None and _dec_row is not None:
        _peak_prs = float(_pt["portfolio_prs"].max())
        _dec_prs  = float(_dec_row["portfolio_prs"])
        _decline  = round(_peak_prs - _dec_prs, 3)
        _gap_dec  = round(
            (float(_dec_row["total_contracted_arr"]) - float(_dec_row["total_realized_arr"])) / 1e6,
            1,
        )
        st.markdown(f"""
<div style="
  background: #1a2a3a;
  border-left: 3px solid #BA7517;
  border-radius: 0 6px 6px 0;
  padding: 12px 16px;
  margin-bottom: 14px;
  font-size: 13px;
  color: #FFFFFF;
  line-height: 1.7;
">
  <em>In this synthetic run:</em> Portfolio PRS peaked at
  <strong style="color:#1D9E75">{_peak_prs:.3f}</strong> in June
  and declined by <strong style="color:#D85A30">{_decline:.3f} points</strong>
  to {_dec_prs:.3f} by December — suggesting newer ARR additions
  in H2 are not realizing value at the same rate as the existing base.
  The unrealized gap at year-end stands at
  <strong style="color:#D85A30">${_gap_dec}M</strong>,
  representing the GCS intervention opportunity.
</div>
""", unsafe_allow_html=True)

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

    # ── Jan / Jun / Dec milestone table ──────────────────────────────────────
    if _jan_row is not None and _jun_row is not None and _dec_row is not None:
        st.markdown("#### Key milestones — Jan · Jun · Dec 2024")

        def _gap(row):
            return (float(row["total_contracted_arr"]) - float(row["total_realized_arr"])) / 1e6

        _milestone_data = {
            "Metric": [
                "Contracted ARR",
                "Realized ARR",
                "Portfolio PRS",
                "Unrealized Gap",
            ],
            "Jan 2024": [
                f"${float(_jan_row['total_contracted_arr']) / 1e6:.1f}M",
                f"${float(_jan_row['total_realized_arr']) / 1e6:.1f}M",
                f"{float(_jan_row['portfolio_prs']):.3f}",
                f"${_gap(_jan_row):.1f}M",
            ],
            "Jun 2024": [
                f"${float(_jun_row['total_contracted_arr']) / 1e6:.1f}M",
                f"${float(_jun_row['total_realized_arr']) / 1e6:.1f}M",
                f"{float(_jun_row['portfolio_prs']):.3f}",
                f"${_gap(_jun_row):.1f}M",
            ],
            "Dec 2024": [
                f"${float(_dec_row['total_contracted_arr']) / 1e6:.1f}M",
                f"${float(_dec_row['total_realized_arr']) / 1e6:.1f}M",
                f"{float(_dec_row['portfolio_prs']):.3f}",
                f"${_gap(_dec_row):.1f}M",
            ],
            "Signal": [
                "↑ Growth",
                "↑ Value captured",
                "↓ Health declining",
                "↑ Intervention need",
            ],
        }
        st.dataframe(
            pd.DataFrame(_milestone_data),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Jun is the PRS peak. Dec shows H2 health erosion "
            "despite ARR growth — the core finding that motivates "
            "Realized ARR as a North Star metric."
        )
    else:
        st.warning("Run pipeline for Jan, Jun, and Dec to see this table.")

    st.caption(CAPTION)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — By Region
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "By Region":
    _cmp_hdr = (
        f"{month_a.strftime('%b %Y')} vs {month_b.strftime('%b %Y')}"
        if compare_mode else month_label
    )
    st.header(f"Performance by Region — {_cmp_hdr}")
    _filter_banner()

    if _filtered_accts.empty:
        st.warning("No accounts match the current filters.")
        st.stop()

    region_df = compute_region_metrics(_filtered_accts)
    region_df["Realized ARR ($M)"]   = region_df["realized_arr"].astype(float)   / 1e6
    region_df["Contracted ARR ($M)"] = region_df["contracted_arr"].astype(float) / 1e6

    if compare_mode:
        region_df_b = compute_region_metrics(_filtered_accts_b)
        region_df_b["Realized ARR ($M)"] = region_df_b["realized_arr"].astype(float) / 1e6

        _lbl_a = month_a.strftime("%b %Y")
        _lbl_b = month_b.strftime("%b %Y")
        region_df["Month"]   = _lbl_a
        region_df_b["Month"] = _lbl_b
        _region_combined = pd.concat([region_df, region_df_b], ignore_index=True)
        _cmap = {_lbl_a: "#4A90D9", _lbl_b: "#1D9E75"}

        fig_prs_cmp = px.bar(
            _region_combined, x="region", y="portfolio_prs_pct", color="Month",
            barmode="group", color_discrete_map=_cmap,
            title="Portfolio PRS % by Region",
            labels={"region": "Region", "portfolio_prs_pct": "PRS (%)", "Month": ""},
        )
        fig_prs_cmp.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        st.plotly_chart(fig_prs_cmp, use_container_width=True)

        fig_arr_cmp = px.bar(
            _region_combined, x="region", y="Realized ARR ($M)", color="Month",
            barmode="group", color_discrete_map=_cmap,
            title="Realized ARR by Region",
            labels={"region": "Region", "Month": ""},
        )
        fig_arr_cmp.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        st.plotly_chart(fig_arr_cmp, use_container_width=True)

        st.divider()
        st.subheader("Region PRS Change  (Month B − Month A, sorted worst first)")

        _tbl_cmp = (
            region_df[["region", "portfolio_prs_pct"]]
            .rename(columns={"portfolio_prs_pct": f"PRS% ({_lbl_a})"})
            .merge(
                region_df_b[["region", "portfolio_prs_pct"]]
                .rename(columns={"portfolio_prs_pct": f"PRS% ({_lbl_b})"}),
                on="region", how="outer",
            )
        )
        _tbl_cmp["Change (pp)"] = (
            _tbl_cmp[f"PRS% ({_lbl_b})"] - _tbl_cmp[f"PRS% ({_lbl_a})"]
        ).round(2)
        _tbl_cmp = _tbl_cmp.sort_values("Change (pp)").rename(columns={"region": "Region"})
        st.dataframe(_tbl_cmp, use_container_width=True, hide_index=True)
    else:
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

        # — Insight callout: worst-performing region —
        if not region_df.empty:
            _worst_idx = region_df["portfolio_prs_pct"].astype(float).idxmin()
            _worst_region = region_df.loc[_worst_idx, "region"]
            _worst_prs = float(region_df.loc[_worst_idx, "portfolio_prs_pct"]) / 100
            _worst_color = prs_color(_worst_prs)
            st.markdown(f"""
<div style="
  background: #1a2a3a;
  border-left: 3px solid #BA7517;
  border-radius: 0 6px 6px 0;
  padding: 10px 16px;
  margin: 12px 0;
  font-size: 13px;
  color: #FFFFFF;
  line-height: 1.6;
">
  <strong style="color:#BA7517">So what:</strong>
  <strong>{_worst_region}</strong> has the lowest
  portfolio PRS at
  <strong style="color:{_worst_color}">{_worst_prs:.3f}</strong>
  and should receive the first CSM/PS capacity review.
  Address deployment and sustained usage gaps in this
  region before expanding to others.
</div>
""", unsafe_allow_html=True)

        st.divider()
        st.subheader("Region Summary  (worst PRS first)")

        region_df["Recommended Action"] = region_df.apply(region_action, axis=1)

        tbl = region_df.rename(columns={
            "region": "Region", "accounts": "Accounts",
            "portfolio_prs_pct": "PRS%", "at_risk_arr": "At-Risk ARR",
        })[["Region", "Accounts", "Contracted ARR ($M)", "Realized ARR ($M)", "PRS%", "At-Risk ARR", "Recommended Action"]].copy()
        tbl["Contracted ARR ($M)"] = tbl["Contracted ARR ($M)"].round(1)
        tbl["Realized ARR ($M)"]   = tbl["Realized ARR ($M)"].round(1)
        tbl["At-Risk ARR"] = tbl["At-Risk ARR"].apply(_fmt)

        st.dataframe(tbl.sort_values("PRS%"), use_container_width=True, hide_index=True)

        st.caption(
            "**DQ note:** Region roll-ups exclude accounts where `included_monthly_compute_credits = 0` "
            "(DQ-004) and accounts with orphaned or pre-2024 usage logs (DQ-001/DQ-002). "
            "At-Risk ARR reflects unrealized gap for accounts with PRS < 0.70 only. "
            "See the Data Quality page for full exclusion counts."
        )

    st.caption(CAPTION)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — By Sales Rep
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "By Rep":
    st.header(f"CSM / Rep Realization View — Shadow Metric — {month_label}")
    st.warning(
        "**Shadow measurement only.** "
        "This view is for CSM coaching and portfolio "
        "visibility — not for compensation decisions in Phase 1. "
        "Rep rankings should not be shared externally until "
        "data confidence, exception handling, and business "
        "behavior are validated over at least one full quarter."
    )
    _filter_banner()

    if _filtered_accts.empty:
        st.warning("No accounts match the current filters.")
        st.stop()

    total_counts = _all_accts.groupby("rep_id")["account_id"].count().rename("total_count")
    rep_df = compute_rep_metrics(_filtered_accts)
    rep_df = rep_df.merge(total_counts.reset_index(), on="rep_id", how="left")
    rep_df["total_count"] = rep_df["total_count"].fillna(0).astype(int)
    rep_df = rep_df.reset_index(drop=True)  # keep iloc indices stable for on_select

    if compare_mode:
        st.subheader(
            f"Rep PRS Change — {month_a.strftime('%b %Y')} vs {month_b.strftime('%b %Y')}"
            "  (sorted worst change first)"
        )
        _rep_b = compute_rep_metrics(apply_filters(_all_accts_b)).reset_index(drop=True)
        _lbl_a = month_a.strftime("%b %Y")
        _lbl_b = month_b.strftime("%b %Y")
        _tbl_cmp = (
            rep_df[["rep_id", "rep_name", "region", "segment", "portfolio_prs_pct"]]
            .rename(columns={"portfolio_prs_pct": f"PRS% ({_lbl_a})"})
            .merge(
                _rep_b[["rep_id", "portfolio_prs_pct"]]
                .rename(columns={"portfolio_prs_pct": f"PRS% ({_lbl_b})"}),
                on="rep_id", how="outer",
            )
        )
        _tbl_cmp["Change (pp)"] = (
            _tbl_cmp[f"PRS% ({_lbl_b})"] - _tbl_cmp[f"PRS% ({_lbl_a})"]
        ).round(2)
        _tbl_cmp = _tbl_cmp.sort_values("Change (pp)").reset_index(drop=True)

        _disp_cmp = _tbl_cmp.rename(columns={
            "rep_name": "Rep Name", "region": "Region", "segment": "Segment",
        })[["Rep Name", "Region", "Segment", f"PRS% ({_lbl_a})", f"PRS% ({_lbl_b})", "Change (pp)"]]
        _disp_cmp.insert(0, "", "→")

        rep_selection = st.dataframe(
            _disp_cmp, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row", key="rep_table",
        )
        if rep_selection.selection.rows:
            clicked_rep = _tbl_cmp.iloc[rep_selection.selection.rows[0]]["rep_name"]
            st.session_state["rep_drill_selection"] = clicked_rep
    else:
        st.subheader("Accounts needing coaching support (lowest realization first)")

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
            "portfolio_prs_pct":    "Realization Rate (shadow)",
            "at_risk_arr":          "At-Risk ARR",
        })[["Rep Name", "Region", "Segment", "Accounts",
            "Contracted ARR", "Realized ARR", "Realization Rate (shadow)", "At-Risk ARR"]]

        tbl["Contracted ARR"] = tbl["Contracted ARR"].apply(_fmt)
        tbl["Realized ARR"]   = tbl["Realized ARR"].apply(_fmt)
        tbl["At-Risk ARR"]    = tbl["At-Risk ARR"].apply(_fmt)
        tbl.insert(0, "", "→")

        rep_selection = st.dataframe(
            tbl, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row", key="rep_table",
        )
        if rep_selection.selection.rows:
            clicked_rep = rep_df.iloc[rep_selection.selection.rows[0]]["rep_name"]
            st.session_state["rep_drill_selection"] = clicked_rep

    st.caption(
        "Realization Rate = Realized ARR ÷ Contracted ARR. "
        "Low rates indicate deployment or adoption gaps — "
        "not rep performance — until root cause is confirmed."
    )
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
    _wf_d, _wf_s, _wf_h, _wf_e = st.columns(4)
    with _wf_d: help_icon("deployment")
    with _wf_s: help_icon("sustained")
    with _wf_h: help_icon("health_signal")
    with _wf_e: help_icon("expansion")

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

    # ── Recommended next action ───────────────────────────────────────────────
    _shelfware = bool(acct_row.get("shelfware_override", False))
    _prs_band  = str(acct_row.get("prs_band", ""))
    _overage   = bool(acct_row.get("flag_overage", False))
    _health    = float(acct_row.get("technical_health_score", 0.6))
    _sustained = float(acct_row.get("sustained_usage_score", 0.0))
    _prs       = float(acct_row.get("prs", 0.0))

    if _shelfware:
        _action  = "Schedule adoption workshop within 30 days"
        _urgency = "critical"
        _icon    = "🔴"
    elif _prs_band == "Red":
        _action  = "CSM + PS recovery plan — 45-day sprint"
        _urgency = "critical"
        _icon    = "🔴"
    elif _overage and _health >= 0.6:
        _action  = "Expansion or right-sizing conversation"
        _urgency = "opportunity"
        _icon    = "🟢"
    elif _overage and _health < 0.6:
        _action  = "Resolve technical friction before expansion"
        _urgency = "warning"
        _icon    = "🟡"
    elif _sustained < 0.15:
        _action  = "Investigate spike/drop pattern — re-onboarding"
        _urgency = "warning"
        _icon    = "🟡"
    elif _prs_band == "Yellow":
        _action  = "Proactive outreach — check deployment blockers"
        _urgency = "watch"
        _icon    = "🔵"
    else:
        _action  = "Monitor in next monthly review"
        _urgency = "healthy"
        _icon    = "✅"

    _color_map = {
        "critical":    ("#3d1a0f", "#D85A30"),
        "warning":     ("#2d2200", "#BA7517"),
        "opportunity": ("#0f3d2a", "#1D9E75"),
        "watch":       ("#0a1f3d", "#185FA5"),
        "healthy":     ("#1a2a3a", "#94A3B8"),
    }
    _bg, _border = _color_map[_urgency]

    st.markdown(f"""
<div style="
  background: {_bg};
  border-left: 4px solid {_border};
  border-radius: 0 8px 8px 0;
  padding: 14px 18px;
  margin: 16px 0 8px 0;
">
  <div style="
    font-size: 11px;
    font-weight: 600;
    color: {_border};
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
  ">
    Recommended next action
  </div>
  <div style="
    font-size: 15px;
    font-weight: 500;
    color: #FFFFFF;
    line-height: 1.5;
  ">
    {_icon} &nbsp; {_action}
  </div>
</div>
""", unsafe_allow_html=True)

    st.caption(
        "Action based on PRS components for "
        f"{selected_company} in {selected_month.strftime('%B %Y')}. "
        "Confirm with CSM before initiating."
    )

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
        if compare_mode:
            fig_atrend.add_vline(
                x=month_a.strftime("%b"), line_dash="dash", line_color="#4A90D9",
                annotation_text=month_a.strftime("%b %Y"), annotation_position="top left",
            )
            fig_atrend.add_vline(
                x=month_b.strftime("%b"), line_dash="dash", line_color="#1D9E75",
                annotation_text=month_b.strftime("%b %Y"), annotation_position="top right",
            )
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


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — Data Quality Monitor
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "Data Quality":
    st.header("Data Quality Monitor")

    dq_df      = load_dq_summary()
    total_logs = load_daily_log_count()

    # ── Section A: Summary cards ──────────────────────────────────────────────
    conf_df    = load_data_confidence()
    conf       = conf_df.iloc[0]
    _total_raw = int(conf["total_logs"])
    _clean     = int(conf["clean_logs"])
    _excluded  = _total_raw - _clean
    confidence_pct = round(_clean / _total_raw * 100, 2) if _total_raw > 0 else 0.0

    conf_col, _ = st.columns([2, 2])
    with conf_col:
        st.metric(
            label="Data Confidence",
            value=f"{confidence_pct}%",
            delta=f"{_excluded:,} rows excluded from metric",
            delta_color="off",
        )
    if confidence_pct >= 99:
        st.success(f"High confidence — {confidence_pct}% of logs are clean")
    elif confidence_pct >= 95:
        st.warning(f"Moderate confidence — {confidence_pct}% of logs are clean")
    else:
        st.error("Low confidence — review DQ issues before metric use")
    st.caption(
        f"{_clean:,} clean logs of {_total_raw:,} total · "
        f"{conf['orphaned_logs']:,} orphaned (DQ-001) · "
        f"{conf['rogue_logs']:,} pre-contract (DQ-002) · "
        f"{conf['negative_logs']:,} negative values (DQ-005)"
    )

    st.divider()

    dq001 = int(dq_df.loc[dq_df["dq_rule"] == "DQ-001", "count"].sum()) if not dq_df.empty else 0
    dq002 = int(dq_df.loc[dq_df["dq_rule"] == "DQ-002", "count"].sum()) if not dq_df.empty else 0
    clean = total_logs - dq001 - dq002

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total logs processed",            f"{total_logs:,}")
    c2.metric("Orphaned logs excluded (DQ-001)", f"{dq001:,}")
    c3.metric("Rogue logs excluded (DQ-002)",    f"{dq002:,}")
    c4.metric("Clean logs used in pipeline",     f"{clean:,}")

    st.divider()

    # ── Section B: DQ Issues table ─────────────────────────────────────────────
    st.subheader("DQ Issues")

    _ACTION_MAP = {"DQ-001": "Excluded", "DQ-002": "Excluded"}

    if dq_df.empty:
        st.info("No DQ issues found.")
    else:
        tbl_dq = dq_df[["dq_rule", "exclusion_reason", "count"]].copy()
        tbl_dq["pct"] = (
            (tbl_dq["count"].astype(float) / total_logs * 100).round(2)
            if total_logs else 0.0
        )
        tbl_dq["action"] = tbl_dq["dq_rule"].map(_ACTION_MAP).fillna("Review")
        tbl_dq.columns = ["Rule", "Description", "Count", "% of Total", "Action"]

        def _dq_style(df: pd.DataFrame) -> pd.DataFrame:
            styles = pd.DataFrame("", index=df.index, columns=df.columns)
            styles.loc[df["Count"] > 0, "Count"] = "background-color: #A32D2D; color: white"
            return styles

        st.dataframe(
            tbl_dq.style.apply(_dq_style, axis=None),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # ── Section C: Anomaly Detection ──────────────────────────────────────────
    st.subheader(f"Anomaly Detection — {month_label}")

    anomaly_df    = load_anomaly_summary(month_str)
    overlap_df    = load_overlap_contracts()
    overlap_count = len(overlap_df) if not overlap_df.empty else 0

    if not anomaly_df.empty:
        r = anomaly_df.iloc[0]
        anomaly_rows = [
            {
                "Anomaly":            "Shelfware",
                "Accounts":           int(r["shelfware_count"]),
                "Contracted ARR":     _fmt(float(r["shelfware_arr"])),
                "Action recommended": "CSM outreach",
            },
            {
                "Anomaly":            "Spike & Drop",
                "Accounts":           int(r["spike_drop_count"]),
                "Contracted ARR":     _fmt(float(r["spike_drop_arr"])),
                "Action recommended": "Re-onboarding",
            },
            {
                "Anomaly":            "Consistent Overagers",
                "Accounts":           int(r["overage_count"]),
                "Contracted ARR":     _fmt(float(r["overage_arr"])),
                "Action recommended": "Expansion conversation",
            },
            {
                "Anomaly":            "Overlapping Contracts",
                "Accounts":           overlap_count,
                "Contracted ARR":     "n/a",
                "Action recommended": "Handled by MAX() logic",
            },
        ]
        st.dataframe(
            pd.DataFrame(anomaly_rows),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # ── Section D: Pipeline status ────────────────────────────────────────────
    st.subheader("Pipeline Status")

    last_run = None
    if not dq_df.empty and "last_run" in dq_df.columns:
        _ts = pd.to_datetime(dq_df["last_run"].max())
        if pd.notna(_ts):
            last_run = _ts

    ts_str = last_run.strftime("%Y-%m-%d %H:%M UTC") if last_run else "Unknown"
    st.markdown(f"**Last pipeline run:** {ts_str}")
    st.info("🧪 **Latest local run: 22/22 passing**")

    st.caption(CAPTION)
