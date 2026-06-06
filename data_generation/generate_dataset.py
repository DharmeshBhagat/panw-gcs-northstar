#!/usr/bin/env python3
"""
PANW GCS North Star — Phase 1: Data Simulation & Storage
generate_dataset.py  |  v1.0

Generates a realistic B2B SaaS synthetic dataset with all 5 edge cases
and uploads directly to Google BigQuery Sandbox.

Usage:
    python generate_dataset.py --project YOUR_GCP_PROJECT_ID --dataset gcs_north_star
    python generate_dataset.py --no-upload   # local CSV only, no GCP needed

Prerequisites:
    pip install -r requirements.txt
    gcloud auth application-default login
    gcloud config set project YOUR_GCP_PROJECT_ID
"""

import argparse
import os
import random
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# ── Reproducibility ───────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

# ── Constants ─────────────────────────────────────────────────────────
START = date(2024, 1, 1)
END   = date(2024, 12, 31)

REGIONS    = ["North America", "EMEA", "APAC", "LATAM"]
REG_W      = [0.40, 0.30, 0.20, 0.10]
SEGMENTS   = ["Enterprise", "Mid-Market"]
SEG_W      = [0.40, 0.60]
INDUSTRIES = ["Technology", "Financial Services", "Healthcare", "Retail",
              "Manufacturing", "Media & Entertainment", "Energy", "Government"]
IND_W      = [0.25, 0.20, 0.15, 0.12, 0.10, 0.08, 0.06, 0.04]
HEALTH_COLORS = ["Green", "Yellow", "Red"]

# Edge case proportions
SPIKE_DROP_PCT = 0.05
SHELFWARE_PCT  = 0.10
OVERAGER_PCT   = 0.15


def _sep(title=""):
    print(f"\n{'─' * 62}")
    if title:
        print(f"  {title}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABLE 1: CSM_REP  (50 rows)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def gen_csm_rep(n: int = 50) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "csm_id":  f"REP{i:03d}",
            "name":    fake.name(),
            "region":  np.random.choice(REGIONS, p=REG_W),
            "segment": np.random.choice(SEGMENTS, p=SEG_W),
        })
    return pd.DataFrame(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABLE 2: ACCOUNTS  (1,000 rows)
# Assigns internal _type label to drive edge-case data generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def gen_accounts(csm_rep_df: pd.DataFrame, n: int = 1000) -> pd.DataFrame:
    indices = list(range(n))
    random.shuffle(indices)
    n_spike = int(n * SPIKE_DROP_PCT)
    n_shelf = int(n * SHELFWARE_PCT)
    n_over  = int(n * OVERAGER_PCT)

    acct_type: dict[int, str] = {}
    for i in indices[:n_spike]:                              acct_type[i] = "spike_drop"
    for i in indices[n_spike:n_spike + n_shelf]:             acct_type[i] = "shelfware"
    for i in indices[n_spike + n_shelf:n_spike + n_shelf + n_over]: acct_type[i] = "overager"
    for i in indices[n_spike + n_shelf + n_over:]:           acct_type[i] = "healthy"

    seen: dict[str, int] = {}
    rows = []
    for i in range(n):
        base = fake.company()
        if base in seen:
            seen[base] += 1
            name = f"{base} {seen[base]}"
        else:
            seen[base] = 1
            name = base

        rows.append({
            "account_id":   f"ACC{i + 1:04d}",
            "company_name": name,
            "industry":     np.random.choice(INDUSTRIES, p=IND_W),
            "rep_id":       np.random.choice(csm_rep_df["csm_id"].values),
            "_type":        acct_type[i],   # internal — stripped before upload
        })
    return pd.DataFrame(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABLE 3: CONTRACTS  (~1,200 rows)
# Edge case 4: ~50 mid-year expansion contracts (overlapping dates)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def gen_contracts(accounts_df: pd.DataFrame,
                  csm_rep_df:  pd.DataFrame,
                  n: int = 1200):
    rep_seg = dict(zip(csm_rep_df["csm_id"], csm_rep_df["segment"]))
    rows = []
    cid  = 1

    for _, acc in accounts_df.iterrows():
        seg = rep_seg.get(acc["rep_id"], "Mid-Market")

        if seg == "Enterprise":
            arr = int(np.random.choice(
                [50, 75, 100, 150, 200, 300, 500],
                p=[.10, .15, .25, .25, .15, .07, .03]) * 1000)
        else:
            arr = int(np.random.choice(
                [5, 10, 15, 25, 35, 50],
                p=[.15, .25, .25, .20, .10, .05]) * 1000)

        # Shelfware: inflate ARR (high commit, no usage)
        if acc["_type"] == "shelfware":
            arr = int(arr * random.uniform(1.5, 2.5))

        offset  = random.randint(0, 300)
        s_date  = START + timedelta(days=offset)
        e_date  = s_date + timedelta(days=364)
        monthly = max(100, int(arr / 12 * random.uniform(0.8, 1.2)))

        rows.append({
            "contract_id":                       f"CTR{cid:05d}",
            "account_id":                        acc["account_id"],
            "start_date":                        s_date,
            "end_date":                          e_date,
            "annual_commit_dollars":             arr,
            "included_monthly_compute_credits":  monthly,
        })
        cid += 1

    # ── Mid-year expansion contracts (edge case 4) ────────────────────
    expansion_pool = accounts_df[
        accounts_df["_type"].isin(["healthy", "overager"])
    ]["account_id"].tolist()
    expansion_ids = set(random.sample(expansion_pool, min(50, len(expansion_pool))))

    for eid in expansion_ids:
        orig = next((r for r in rows if r["account_id"] == eid), None)
        if not orig:
            continue
        exp_start = orig["start_date"] + timedelta(days=random.randint(120, 240))
        if exp_start > END:
            continue
        exp_arr    = int(orig["annual_commit_dollars"] * random.uniform(1.5, 3.0))
        exp_credit = max(100, int(exp_arr / 12 * random.uniform(0.8, 1.2)))
        rows.append({
            "contract_id":                       f"CTR{cid:05d}",
            "account_id":                        eid,
            "start_date":                        exp_start,
            "end_date":                          exp_start + timedelta(days=364),
            "annual_commit_dollars":             exp_arr,
            "included_monthly_compute_credits":  exp_credit,
        })
        cid += 1

    # Pad to target row count
    while len(rows) < n:
        acc  = accounts_df.sample(1).iloc[0]
        s    = START + timedelta(days=random.randint(0, 330))
        arr  = random.randint(10_000, 200_000)
        rows.append({
            "contract_id":                       f"CTR{cid:05d}",
            "account_id":                        acc["account_id"],
            "start_date":                        s,
            "end_date":                          s + timedelta(days=364),
            "annual_commit_dollars":             arr,
            "included_monthly_compute_credits":  max(100, int(arr / 12)),
        })
        cid += 1

    df = pd.DataFrame(rows[:n])
    df["start_date"] = pd.to_datetime(df["start_date"]).dt.date
    df["end_date"]   = pd.to_datetime(df["end_date"]).dt.date
    return df, expansion_ids


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABLE 4: DAILY_USAGE_LOGS  (~200,000 rows)
# Edge case 1: spike_drop   — 90% in Month 1, then near-zero
# Edge case 2: shelfware    — zero logs
# Edge case 3: overager     — 120%+ consumption monthly
# Edge case 5: orphaned     — 200 rows with non-existent account_ids
#              rogue usage  — 150 rows dated before contract start (2023)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def gen_daily_usage_logs(accounts_df: pd.DataFrame,
                          contracts_df: pd.DataFrame) -> pd.DataFrame:
    primary = (
        contracts_df.sort_values("start_date")
        .drop_duplicates("account_id", keep="first")
        .set_index("account_id")
    )
    months = pd.period_range("2024-01", "2024-12", freq="M")
    rows = []
    lid  = 1

    for _, acc in accounts_df.iterrows():
        aid   = acc["account_id"]
        atype = acc["_type"]

        if atype == "shelfware":          # edge case 2: zero logs
            continue
        if aid not in primary.index:
            continue

        mc = int(primary.loc[aid, "included_monthly_compute_credits"])

        for mo_idx, mo in enumerate(months):
            mo_s  = date(mo.year, mo.month, 1)
            mo_e  = (date(mo.year, mo.month % 12 + 1, 1) - timedelta(days=1)
                     if mo.month < 12 else date(mo.year, 12, 31))
            n_days = (mo_e - mo_s).days + 1

            # Monthly consumption by account type
            if atype == "spike_drop":       # edge case 1
                monthly = mc * 0.9 * 12 if mo_idx == 0 else mc * random.uniform(0.005, 0.02)
            elif atype == "overager":       # edge case 3
                monthly = mc * random.uniform(1.20, 1.60)
            else:                           # healthy
                monthly = mc * random.uniform(0.55, 0.95)

            if monthly < 1:
                continue

            n_active   = max(1, int(n_days * random.uniform(0.45, 0.90)))
            active_days = sorted(random.sample(
                [mo_s + timedelta(i) for i in range(n_days)],
                min(n_active, n_days)
            ))

            # Distribute monthly total across active days using Dirichlet
            shares = np.random.dirichlet(np.ones(len(active_days)))
            daily  = (shares * monthly).astype(int)
            daily[-1] += int(monthly) - daily.sum()   # fix rounding

            for d, amt in zip(active_days, daily):
                if amt <= 0:
                    continue
                rows.append({
                    "log_id":                   f"LOG{lid:07d}",
                    "account_id":               aid,
                    "date":                     d,
                    "compute_credits_consumed": int(amt),
                })
                lid += 1

    # Edge case 5a: ~200 orphaned logs (fake account IDs, not in Accounts)
    for _ in range(200):
        rows.append({
            "log_id":                   f"LOG{lid:07d}",
            "account_id":               f"ACC{random.randint(9001, 9999):04d}",
            "date":                     START + timedelta(days=random.randint(0, 364)),
            "compute_credits_consumed": random.randint(10, 500),
        })
        lid += 1

    # Edge case 5b: ~150 rogue logs (valid account, dated before 2024 contract start)
    healthy_aids = accounts_df[accounts_df["_type"] == "healthy"]["account_id"].tolist()
    for aid in random.choices(healthy_aids, k=150):
        rows.append({
            "log_id":                   f"LOG{lid:07d}",
            "account_id":               aid,
            "date":                     date(2023, random.randint(1, 12), random.randint(1, 28)),
            "compute_credits_consumed": random.randint(10, 400),
        })
        lid += 1

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABLE 5: ACCOUNT_HEALTH  (~50,000 rows — weekly health checks)
# Health color distribution reflects account type
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def gen_account_health(accounts_df: pd.DataFrame,
                        contracts_df:  pd.DataFrame) -> pd.DataFrame:
    primary = (
        contracts_df.sort_values("start_date")
        .drop_duplicates("account_id", keep="first")
        .set_index("account_id")
    )
    rows = []

    for _, acc in accounts_df.iterrows():
        aid   = acc["account_id"]
        atype = acc["_type"]

        if   atype == "shelfware":  cp = [0.10, 0.30, 0.60]
        elif atype == "spike_drop": cp = [0.15, 0.40, 0.45]
        elif atype == "overager":   cp = [0.70, 0.25, 0.05]
        else:                       cp = [0.65, 0.25, 0.10]

        n_checks    = random.randint(46, 54)
        check_dates = pd.date_range(START, END, periods=n_checks)
        color       = np.random.choice(HEALTH_COLORS, p=cp)
        mc          = int(primary.loc[aid, "included_monthly_compute_credits"]) \
                      if aid in primary.index else 1000

        for d in check_dates:
            if random.random() < 0.15:
                color = np.random.choice(HEALTH_COLORS, p=cp)
            daily_est = max(0, int(mc / 30 * random.uniform(0.5, 1.5)))
            rows.append({
                "health_color":             color,
                "account_id":               aid,
                "date":                     d.date(),
                "compute_credits_consumed": daily_est,
            })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIGQUERY UPLOAD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BQ_SCHEMAS: dict = {}


def _build_bq_schemas():
    from google.cloud import bigquery as bq
    global BQ_SCHEMAS
    BQ_SCHEMAS = {
        "csm_rep": [
            bq.SchemaField("csm_id",  "STRING"),
            bq.SchemaField("name",    "STRING"),
            bq.SchemaField("region",  "STRING"),
            bq.SchemaField("segment", "STRING"),
        ],
        "accounts": [
            bq.SchemaField("account_id",   "STRING"),
            bq.SchemaField("company_name", "STRING"),
            bq.SchemaField("industry",     "STRING"),
            bq.SchemaField("rep_id",       "STRING"),
        ],
        "contracts": [
            bq.SchemaField("contract_id",                       "STRING"),
            bq.SchemaField("account_id",                        "STRING"),
            bq.SchemaField("start_date",                        "DATE"),
            bq.SchemaField("end_date",                          "DATE"),
            bq.SchemaField("annual_commit_dollars",             "INTEGER"),
            bq.SchemaField("included_monthly_compute_credits",  "INTEGER"),
        ],
        "account_health": [
            bq.SchemaField("health_color",             "STRING"),
            bq.SchemaField("account_id",               "STRING"),
            bq.SchemaField("date",                     "DATE"),
            bq.SchemaField("compute_credits_consumed", "INTEGER"),
        ],
        "daily_usage_logs": [
            bq.SchemaField("log_id",                   "STRING"),
            bq.SchemaField("account_id",               "STRING"),
            bq.SchemaField("date",                     "DATE"),
            bq.SchemaField("compute_credits_consumed", "INTEGER"),
        ],
    }


def upload_table(df: pd.DataFrame, project_id: str, dataset_id: str,
                 table_name: str) -> None:
    from google.cloud import bigquery as bq
    client    = bq.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_name}"
    job_cfg   = bq.LoadJobConfig(
        schema=BQ_SCHEMAS[table_name],
        write_disposition="WRITE_TRUNCATE",
    )
    print(f"  Uploading {len(df):>7,} rows  →  {table_ref} ... ", end="", flush=True)
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_cfg)
    job.result()
    print("✓")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    parser = argparse.ArgumentParser(
        description="PANW GCS North Star — Phase 1 Data Generator"
    )
    parser.add_argument("--project",    default=None,          help="GCP Project ID")
    parser.add_argument("--dataset",    default="gcs_north_star", help="BigQuery dataset ID")
    parser.add_argument("--no-upload",  action="store_true",   help="Local CSV only — skip BigQuery")
    parser.add_argument("--output-dir", default="./data",      help="Local CSV output folder")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("\n" + "═" * 62)
    print("  PANW GCS North Star  |  Phase 1: Data Generation")
    print("═" * 62)

    # ── Generate tables ───────────────────────────────────────────────
    _sep("Step 1 / 5  CSM_rep")
    csm_rep = gen_csm_rep()
    print(f"  ✓ {len(csm_rep):,} rows")

    _sep("Step 2 / 5  Accounts")
    accounts = gen_accounts(csm_rep)
    tc = accounts["_type"].value_counts().to_dict()
    print(f"  ✓ {len(accounts):,} rows  spike_drop={tc.get('spike_drop',0)} "
          f"shelfware={tc.get('shelfware',0)} overager={tc.get('overager',0)} "
          f"healthy={tc.get('healthy',0)}")

    _sep("Step 3 / 5  Contracts")
    contracts, expansion_ids = gen_contracts(accounts, csm_rep)
    print(f"  ✓ {len(contracts):,} rows  "
          f"(includes {len(expansion_ids)} mid-year expansions)")

    _sep("Step 4 / 5  Daily_Usage_Logs")
    usage_logs = gen_daily_usage_logs(accounts, contracts)
    print(f"  ✓ {len(usage_logs):,} rows  "
          f"(incl. 200 orphaned + 150 rogue usage rows)")

    _sep("Step 5 / 5  Account_Health")
    account_health = gen_account_health(accounts, contracts)
    print(f"  ✓ {len(account_health):,} rows")

    # ── Strip internal _type column before saving ─────────────────────
    accounts_clean = accounts.drop(columns=["_type"])

    tables = {
        "csm_rep":          csm_rep,
        "accounts":         accounts_clean,
        "contracts":        contracts,
        "daily_usage_logs": usage_logs,
        "account_health":   account_health,
    }

    # ── Save CSV backups ──────────────────────────────────────────────
    _sep("Saving CSV backups")
    for name, df in tables.items():
        path = os.path.join(args.output_dir, f"{name}.csv")
        df.to_csv(path, index=False)
        print(f"  ✓ {path}  ({len(df):,} rows)")

    # ── BigQuery upload ───────────────────────────────────────────────
    if not args.no_upload:
        if not args.project:
            print("\n  ERROR: --project YOUR_GCP_PROJECT_ID is required.")
            print("  Use --no-upload to skip BigQuery and save CSVs only.")
            sys.exit(1)

        _build_bq_schemas()
        _sep(f"Uploading to BigQuery  {args.project}.{args.dataset}")
        try:
            for name, df in tables.items():
                upload_table(df, args.project, args.dataset, name)
        except Exception as exc:
            print(f"\n  Upload failed: {exc}")
            print("  Check: gcloud auth application-default login")
            sys.exit(1)

        print(f"\n  All 5 tables loaded into {args.project}.{args.dataset}")
        print(f"""
  Verify with this query in BigQuery console:
  ─────────────────────────────────────────────────────
  SELECT table_id, row_count
  FROM   `{args.project}.{args.dataset}.__TABLES__`
  ORDER  BY table_id;
""")
    else:
        print(f"\n  Skipped BigQuery upload (--no-upload). CSVs in: {args.output_dir}/")

    print("═" * 62)
    print("  Phase 1 complete — data ready for Phase 2")
    print("═" * 62 + "\n")


if __name__ == "__main__":
    main()
