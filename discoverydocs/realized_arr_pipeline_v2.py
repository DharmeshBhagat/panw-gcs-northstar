#!/usr/bin/env python3
"""
Realized ARR Pipeline — v2.0
Palo Alto Networks · Global Customer Services
Spec: Realized_ARR_Spec_v2.md

Changes from v1:
  1. Sustained Usage window capped at MIN(months_active, 12)
  2. Missing health_color → 0.60 (was 0.40)
  3. Expansion Momentum new-account guard (< 3 months → 0.10)
  4. Expansion Momentum window = trailing 6 months (was ambiguous)
  5. Shelfware override: D=0 AND S=0 → PRS = 0.00
  6. Portfolio PRS = ARR-weighted average (not simple mean)
  7. DQ preprocessing = Step 0, separate from metric logic
"""

import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta
import json, warnings
warnings.filterwarnings("ignore")

DATA = "/home/claude"
OUT  = "/home/claude"

print("=" * 70)
print("  REALIZED ARR PIPELINE v2.0  |  Palo Alto Networks GCS")
print("=" * 70)

# ── Load tables ───────────────────────────────────────────────────────
accounts   = pd.read_csv(f"{DATA}/accounts.csv")
contracts  = pd.read_csv(f"{DATA}/contracts.csv",   parse_dates=["start_date","end_date"])
usage_logs = pd.read_csv(f"{DATA}/daily_usage_logs.csv", parse_dates=["date"])
health_df  = pd.read_csv(f"{DATA}/account_health.csv",   parse_dates=["date"])
csm_rep    = pd.read_csv(f"{DATA}/csm_rep.csv")

print(f"\n  Loaded: {len(accounts):,} accounts · {len(contracts):,} contracts · "
      f"{len(usage_logs):,} usage rows · {len(health_df):,} health rows")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 0 — Data Quality Preprocessing (runs before ALL metric logic)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "─" * 70)
print("  STEP 0 · Data Quality")
print("─" * 70)

valid_ids = set(accounts["account_id"])
dq_rows = []

# DQ-001: Orphaned logs
mask_orphan = ~usage_logs["account_id"].isin(valid_ids)
dq_orphans  = usage_logs[mask_orphan].copy()
dq_orphans["dq_rule"] = "DQ-001"
dq_rows.append(dq_orphans[["log_id","account_id","date","compute_credits_consumed","dq_rule"]])
print(f"  DQ-001 Orphaned logs:        {len(dq_orphans):>5,} rows excluded")

# DQ-002: Rogue usage — outside 2024 contract window
clean1      = usage_logs[~mask_orphan].copy()
mask_rogue  = clean1["date"] < pd.Timestamp("2024-01-01")
dq_rogue    = clean1[mask_rogue].copy()
dq_rogue["dq_rule"] = "DQ-002"
dq_rows.append(dq_rogue[["log_id","account_id","date","compute_credits_consumed","dq_rule"]])
print(f"  DQ-002 Rogue usage:          {len(dq_rogue):>5,} rows excluded")

clean_logs  = clean1[~mask_rogue].copy()
dq_report   = pd.concat(dq_rows, ignore_index=True)
dq_report.to_csv(f"{OUT}/dq_report_v2.csv", index=False)
print(f"  Clean usage logs remaining:  {len(clean_logs):>5,}")
print(f"  DQ report saved → dq_report_v2.csv")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# METRIC COMPUTATION — account × month grain
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MONTHS_2024 = pd.date_range("2024-01-01", "2024-12-01", freq="MS")

COLOR_MAP = {"Green": 1.00, "Yellow": 0.60, "Red": 0.20}   # Missing → 0.60 (v2 fix)

def prs_band(prs):
    if prs >= 0.80: return "Green"
    if prs >= 0.60: return "Yellow"
    if prs >= 0.30: return "Orange"
    return "Red"

# Pre-compute monthly consumption per account (for efficiency)
clean_logs["month"] = clean_logs["date"].dt.to_period("M")
monthly_all = (clean_logs.groupby(["account_id","month"])["compute_credits_consumed"]
               .sum().reset_index())

results = []

for mo in MONTHS_2024:
    mo_period = mo.to_period("M")
    mo_end    = mo + pd.offsets.MonthEnd(0)

    # ── Contracted ARR: active contracts this month ───────────────────
    active_ctrs = contracts[
        (contracts["start_date"] <= mo_end) &
        (contracts["end_date"]   >= mo)
    ]
    # MAX annual_commit_dollars per account (handles overlapping contracts)
    contracted = (active_ctrs.groupby("account_id")
                  .agg(cARR=("annual_commit_dollars","max"),
                       included_monthly=("included_monthly_compute_credits","max"),
                       contract_start=("start_date","min"))
                  .reset_index())

    # ── Monthly consumption this month ───────────────────────────────
    mo_consumed = (monthly_all[monthly_all["month"] == mo_period]
                   .set_index("account_id")["compute_credits_consumed"])

    # ── Technical Health this month ───────────────────────────────────
    mo_health = health_df[health_df["date"].dt.to_period("M") == mo_period].copy()
    mo_health["score"] = mo_health["health_color"].map(COLOR_MAP).fillna(0.60)  # v2: Missing→0.60
    health_score = mo_health.groupby("account_id")["score"].mean()

    for _, row in contracted.iterrows():
        aid      = row["account_id"]
        cARR     = row["cARR"]
        inc      = max(row["included_monthly"], 1)
        cs       = row["contract_start"]
        months_active = max(1, (mo - pd.Timestamp(cs)).days // 30)

        # ── Component B: Deployment Score ────────────────────────────
        consumed  = mo_consumed.get(aid, 0)
        D         = min(1.0, consumed / inc)

        # ── Component C: Sustained Usage Score ───────────────────────
        # v2 fix: window capped at MIN(months_active, 12)
        win_size   = min(months_active, 12)
        win_start  = mo_period - win_size + 1
        win_data   = monthly_all[
            (monthly_all["account_id"] == aid) &
            (monthly_all["month"] >= win_start) &
            (monthly_all["month"] <= mo_period)
        ]
        healthy_months = (win_data["compute_credits_consumed"] >= 0.30 * inc).sum()
        actual_win     = max(win_data["month"].nunique(), 1)
        S = healthy_months / actual_win

        # ── Component D: Technical Health Score ──────────────────────
        H = health_score.get(aid, 0.60)  # v2: Missing default = 0.60

        # ── Component E: Expansion Momentum Score ────────────────────
        # v2 fix 1: new account guard (< 3 months → 0.10)
        # v2 fix 2: window = trailing 6 months
        if months_active < 3:
            E = 0.10
        else:
            t6_start = mo_period - 5
            t6_data  = monthly_all[
                (monthly_all["account_id"] == aid) &
                (monthly_all["month"] >= t6_start) &
                (monthly_all["month"] <= mo_period)
            ]
            q_120 = (t6_data["compute_credits_consumed"] >= 1.20 * inc).sum()
            q_070 = (t6_data["compute_credits_consumed"] >= 0.70 * inc).sum()
            q_030 = (t6_data["compute_credits_consumed"] >= 0.30 * inc).sum()
            if   q_120 >= 3: E = 1.00
            elif q_070 >= 3: E = 0.70
            elif q_030 >= 3: E = 0.40
            else:            E = 0.10

        # ── PRS with shelfware override ───────────────────────────────
        # v2 fix 5: D=0 AND S=0 → PRS = 0.00 (no phantom realized value)
        shelfware_override = (D == 0.0 and S == 0.0)
        if shelfware_override:
            PRS = 0.0
        else:
            PRS = D*0.40 + S*0.30 + H*0.20 + E*0.10

        realized_arr = round(cARR * PRS, 2)

        results.append({
            "account_id":             aid,
            "month":                  mo.strftime("%Y-%m"),
            "contracted_arr":         cARR,
            "deployment_score":       round(D, 4),
            "sustained_usage_score":  round(S, 4),
            "technical_health_score": round(H, 4),
            "expansion_momentum":     round(E, 4),
            "prs":                    round(PRS, 4),
            "realized_arr":           realized_arr,
            "prs_band":               prs_band(PRS),
            "shelfware_override":     shelfware_override,
            "flag_overage":           consumed > inc,
            "months_in_window":       int(actual_win),
            "months_active":          months_active,
        })

results_df = pd.DataFrame(results)
results_df.to_csv(f"{OUT}/realized_arr_v2.csv", index=False)
print(f"\n  Account-month rows computed: {len(results_df):,}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PORTFOLIO ROLL-UP (ARR-weighted PRS — v2 fix 6)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Use December snapshot as the "current" portfolio view
dec = results_df[results_df["month"] == "2024-12"].copy()

total_cARR  = dec["contracted_arr"].sum()
total_rARR  = dec["realized_arr"].sum()
total_gap   = total_cARR - total_rARR

# ARR-weighted portfolio PRS (v2 fix 6)
portfolio_prs = (dec["prs"] * dec["contracted_arr"]).sum() / dec["contracted_arr"].sum()
realization_rate = round(total_rARR / total_cARR * 100, 1)

# Tier breakdown
def tier_stats(label, mask):
    s = dec[mask]
    return {"tier": label, "accounts": len(s),
            "cARR": int(s["contracted_arr"].sum()),
            "rARR": int(s["realized_arr"].sum()),
            "pct_portfolio": round(s["contracted_arr"].sum() / total_cARR * 100, 1),
            "avg_prs": round(s["prs"].mean(), 3)}

tiers = [
    tier_stats("Green  (PRS ≥ 0.80)", dec["prs"] >= 0.80),
    tier_stats("Yellow (0.60–0.79)",  (dec["prs"] >= 0.60) & (dec["prs"] < 0.80)),
    tier_stats("Orange (0.30–0.59)",  (dec["prs"] >= 0.30) & (dec["prs"] < 0.60)),
    tier_stats("Red    (< 0.30)",      dec["prs"] < 0.30),
]

shelfware_override_count = int(dec["shelfware_override"].sum())
shelfware_arr  = int(dec[dec["shelfware_override"]]["contracted_arr"].sum())
overage_count  = int(dec["flag_overage"].sum())
overage_arr    = int(dec[dec["flag_overage"]]["contracted_arr"].sum())

# Monthly portfolio trend (ARR-weighted)
monthly_portfolio = (results_df
    .groupby("month")
    .apply(lambda g: pd.Series({
        "total_cARR":  g["contracted_arr"].sum(),
        "total_rARR":  g["realized_arr"].sum(),
        "portfolio_prs": round(
            (g["prs"] * g["contracted_arr"]).sum() / g["contracted_arr"].sum(), 4),
    }))
    .reset_index()
    .to_dict("records"))

# Industry breakdown
dec2 = dec.merge(accounts[["account_id","industry"]], on="account_id", how="left")
industry_br = (dec2.groupby("industry").agg(
    accounts=("account_id","count"),
    cARR=("contracted_arr","sum"),
    rARR=("realized_arr","sum"),
    avg_prs=("prs","mean"),
).reset_index().round(3).to_dict("records"))

summary = {
    "snapshot_month":     "2024-12",
    "total_cARR":         int(total_cARR),
    "total_rARR":         int(total_rARR),
    "total_gap":          int(total_gap),
    "portfolio_prs":      round(portfolio_prs, 4),
    "realization_rate_pct": realization_rate,
    "tiers":              tiers,
    "shelfware":          {"accounts": shelfware_override_count, "cARR": shelfware_arr},
    "overages":           {"accounts": overage_count, "cARR": overage_arr},
    "monthly_trend":      monthly_portfolio,
    "industry_breakdown": industry_br,
    "spec_version":       "v2.0",
    "changes_applied":    [
        "Sustained Usage window capped at MIN(months_active, 12)",
        "Missing health_color mapped to 0.60 (was 0.40)",
        "Expansion Momentum guard: < 3 months active → 0.10",
        "Expansion Momentum window: trailing 6 months",
        "Shelfware override: D=0 AND S=0 → PRS=0.00",
        "Portfolio PRS: ARR-weighted average",
        "DQ Step 0: orphaned + rogue logs excluded before computation",
    ]
}
with open(f"{OUT}/realized_arr_portfolio_v2.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)

print("\n" + "─" * 70)
print("  PORTFOLIO RESULTS (December 2024 snapshot)")
print("─" * 70)
print(f"""
  Total Contracted ARR:    ${total_cARR:>14,.0f}
  Total Realized ARR:      ${total_rARR:>14,.0f}
  Unrealized Gap:          ${total_gap:>14,.0f}
  Portfolio PRS (wtd):             {portfolio_prs:>6.3f}
  Realization Rate:               {realization_rate:>5.1f}%

  TIER BREAKDOWN""")
for t in tiers:
    print(f"  {t['tier']:28s}  {t['accounts']:>4} accts  "
          f"${t['cARR']:>11,.0f} cARR  avg PRS {t['avg_prs']:.3f}")

print(f"""
  EDGE CASE FLAGS
  Shelfware (override fired):  {shelfware_override_count:>4} accounts  ${shelfware_arr:>12,.0f} cARR
  Consistent overagers:        {overage_count:>4} accounts  ${overage_arr:>12,.0f} cARR

  Saved: realized_arr_v2.csv, realized_arr_portfolio_v2.json, dq_report_v2.csv
""")
