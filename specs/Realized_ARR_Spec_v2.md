# Realized ARR — North Star Metric Specification
## Palo Alto Networks · Global Customer Services (GCS)

**Owner:** Principal PM, Centralized Data & AI / Analytics
**Version:** 2.0 · Status: Final — Ready for Claude Code
**Last updated:** 2025

---

## 1. One-line definition

> **Realized ARR** measures how much contracted ARR is actually being converted into healthy, sustained product usage.

---

## 2. Formula

```
Realized ARR = Contracted ARR × PRS

PRS (Platform Realization Score) =
    (Deployment Score       × 0.40)
  + (Sustained Usage Score  × 0.30)
  + (Technical Health Score × 0.20)
  + (Expansion Momentum     × 0.10)

OVERRIDE: IF Deployment Score = 0 AND Sustained Usage Score = 0
          THEN PRS = 0.00
          (shelfware hard floor — prevents phantom realized value)
```

**Output grain:** one row per `account_id × month`
**Output range:** `0 ≤ Realized ARR ≤ Contracted ARR`

---

## 3. Source tables

| Table | Key fields used |
|-------|----------------|
| `Contracts` | `account_id`, `annual_commit_dollars`, `included_monthly_compute_credits`, `start_date`, `end_date` |
| `Daily_Usage_Logs` | `log_id`, `account_id`, `date`, `compute_credits_consumed` |
| `Account_Health` | `account_id`, `date`, `health_color` |
| `Accounts` | `account_id` (used for DQ filter only) |
| `CSM_rep` | `csm_id`, `name`, `region`, `segment` (reporting / segmentation only) |

---

## 4. Step 0 — Data quality preprocessing (run before all metric logic)

Define a clean view `clean_usage_logs` that filters `Daily_Usage_Logs` using these two rules.
All downstream metric steps use `clean_usage_logs`, never the raw table.

### DQ-001 · Orphaned logs
```sql
-- Exclude rows where account_id does not exist in Accounts
WHERE account_id IN (SELECT account_id FROM Accounts)
```
**Why:** Orphaned logs inflate D numerator with usage that cannot be attributed to a real account.

### DQ-002 · Rogue usage (outside contract window)
```sql
-- Exclude rows where usage date falls outside the account's active contract window
WHERE date BETWEEN (SELECT MIN(start_date) FROM Contracts c WHERE c.account_id = log.account_id)
                AND (SELECT MAX(end_date)   FROM Contracts c WHERE c.account_id = log.account_id)
```
**Why:** Usage recorded before contract start or significantly after end date is a data pipeline error,
not real consumption. Flag excluded rows to a `dq_report` table for engineering review.

### DQ output
```
dq_report(log_id, account_id, date, compute_credits_consumed, dq_rule, excluded_at)
```

---

## 5. Component A — Contracted ARR

**Business question:** What did the customer commit to pay?

```sql
Contracted_ARR =
  MAX(annual_commit_dollars)
  FROM Contracts
  WHERE account_id = :account_id
    AND :month_start BETWEEN start_date AND end_date
```

**Rules:**
- Active contract = the target month falls between `start_date` and `end_date` (inclusive).
- For **overlapping contracts** (mid-year expansions): use `MAX(annual_commit_dollars)` per account-month to avoid double-counting.
- **Exclude:** one-time professional services fees, hardware, non-recurring charges.
- If no active contract exists for the account-month: `Contracted_ARR = 0`, skip metric computation for that row.

---

## 6. Component B — Deployment Score (weight: 40%)

**Business question:** Is the customer using what they purchased?

```
Deployment Score = MIN(1.0, monthly_credits_consumed / included_monthly_credits)
```

**Inputs:**
- `monthly_credits_consumed` = `SUM(compute_credits_consumed)` from `clean_usage_logs` for the account-month
- `included_monthly_credits` = `MAX(included_monthly_compute_credits)` from active `Contracts` for the account-month

**Lookup table:**

| Usage pattern | Deployment Score |
|---------------|-----------------|
| No usage (shelfware) | 0.00 |
| 50% of included credits | 0.50 |
| 90% of included credits | 0.90 |
| 100% of included credits | 1.00 |
| 120%+ (overage) | 1.00 (capped) |

**Edge case guards:**
- `included_monthly_credits = 0` → set `Deployment Score = NULL`; exclude row from portfolio averages; log to `dq_report`.
- `monthly_credits_consumed < 0` → treat as 0; log to `dq_report`.
- Overages are capped at 1.00 here so Realized ARR never exceeds Contracted ARR. Overages are separately captured in Expansion Momentum.

---

## 7. Component C — Sustained Usage Score (weight: 30%)

**Business question:** Is usage consistent, or was it a one-time spike?

```
Sustained Usage Score = healthy_months_in_window / window_size

window_size = MIN(months_since_contract_start, 12)

healthy_month = 1  IF monthly_credits_consumed >= 0.30 × included_monthly_credits
              = 0  otherwise
```

**Key change from v1:** Window is capped at 12 months.
Reason: For accounts older than 12 months, bad historical quarters would permanently drag the score
if the window were all-time. The trailing 12-month window makes this a live signal of current health.

**Lookup table:**

| Usage pattern | Sustained Usage Score |
|---------------|-----------------------|
| No usage (shelfware) | 0.00 |
| Spike in Month 1, near zero after | 0.08 |
| Usage in 10 of last 12 months | 0.83 |
| Consistent usage every month | 1.00 |
| Consistent overages | 1.00 |

**Implementation note:**
For accounts where `months_since_contract_start < 12`, compute over available months only.
For Month 1 of a new account: `window_size = 1`, score is either 0.00 or 1.00.
This is correct behavior — a new account with no usage in its first month scores 0.00 on this component.

---

## 8. Component D — Technical Health Score (weight: 20%)

**Business question:** Is the account technically healthy?

```
Technical Health Score = AVG(health_score)
                         for all Account_Health records in the account-month

health_score mapping:
  Green   → 1.00
  Yellow  → 0.60
  Missing → 0.60   ← neutral default (same as Yellow)
  Red     → 0.20
```

**Key change from v1:** `Missing` changed from 0.40 to 0.60.
Reason: A missing health record means the account has not been checked recently — it is not
evidence of degraded health. Setting it equal to Yellow treats it as neutral rather than
penalizing data gaps as if they were real problems.

**Implementation:**
1. Group `Account_Health` by `account_id` and the target month.
2. Map each `health_color` to its numeric score.
3. Take the arithmetic average across all records in that month.
4. If no records exist for the account-month: return 0.60 (the Missing default).

---

## 9. Component E — Expansion Momentum Score (weight: 10%)

**Business question:** Is this account showing expansion potential?

```
-- Guard: accounts with fewer than 3 months of contract history default to 0.10
IF months_since_contract_start < 3 THEN Expansion_Momentum = 0.10

-- Otherwise: evaluate usage in the trailing 6-month window
ELSE:
  qualifying_months = COUNT(months in trailing 6 where usage meets threshold)

  Expansion_Momentum =
    CASE
      WHEN qualifying_months >= 3 AND avg_usage >= 1.20 × included THEN 1.00
      WHEN qualifying_months >= 3 AND avg_usage >= 0.70 × included THEN 0.70
      WHEN qualifying_months >= 3 AND avg_usage >= 0.30 × included THEN 0.40
      ELSE 0.10
    END
```

**Key changes from v1:**
1. **New account guard:** accounts with `months_since_contract_start < 3` default to 0.10. This prevents Month 1 and Month 2 accounts from always falling to ELSE.
2. **Window definition:** "3+ months" now explicitly means **3 or more months within the trailing 6-month window** — not 3 consecutive months, not all contract history. This makes the signal responsive to recent behavior.

**Interpretation:**

| Score | Meaning |
|-------|---------|
| 1.00 | Consistent heavy overager — strong upsell signal |
| 0.70 | Healthy and growing — expansion ready |
| 0.40 | Moderate usage — stable, not yet an expansion candidate |
| 0.10 | Low or early-stage usage — no expansion signal yet |

---

## 10. PRS computation

```python
# Step 1: compute components
deployment  = min(1.0, monthly_consumed / included_monthly)
sustained   = healthy_months_in_window / window_size
health      = avg_health_score_for_month           # uses 0.60 for Missing
expansion   = expansion_momentum_score(...)         # uses guard for < 3 months

# Step 2: shelfware override (applied BEFORE weighted sum)
if deployment == 0 and sustained == 0:
    prs = 0.00
else:
    prs = (deployment  * 0.40
         + sustained   * 0.30
         + health      * 0.20
         + expansion   * 0.10)

# Step 3: final Realized ARR
realized_arr = contracted_arr * prs
```

**Why the override matters:**
Without it, a shelfware account with Red health and default expansion still computes:
`PRS = 0 + 0 + (0.20 × 0.20) + (0.10 × 0.10) = 0.05`
A $2M ARR account that has never been deployed would show $100K "realized" — misleading.
The override hard-floors true shelfware to zero.

---

## 11. Portfolio roll-up

```
Portfolio_PRS = Σ(account_PRS × account_Contracted_ARR) / Σ(account_Contracted_ARR)

Portfolio_Realized_ARR = Σ(account_Realized_ARR)

Portfolio_Realization_Rate = Portfolio_Realized_ARR / Σ(account_Contracted_ARR)
```

**Why ARR-weighted:** A simple average of PRS scores treats a $10K account the same as a $2M account.
ARR-weighting ensures large contracts drive the portfolio signal proportionally.

---

## 12. Health bands

| PRS | Status | Color | Meaning |
|-----|--------|-------|---------|
| 0.80 – 1.00 | Healthy | Green | Strong deployment, consistent usage, technically stable |
| 0.60 – 0.79 | Watch | Yellow | Partially realized — monitor, consider proactive outreach |
| 0.30 – 0.59 | At-Risk | Orange | High adoption or health risk — CSM intervention needed |
| 0.00 – 0.29 | Critical | Red | Shelfware, broken deployment, or active churn risk |

---

## 13. Edge case handling

| Edge case | How the metric handles it |
|-----------|--------------------------|
| **Spike & Drop** | Month 1 may show high Deployment, but Sustained Usage Score collapses (e.g. 1/12 = 0.08). PRS correctly reflects the account is not sustained. |
| **Shelfware** | Deployment = 0, Sustained = 0 → shelfware override fires → PRS = 0.00 → Realized ARR = $0. No phantom value. |
| **Consistent Overages** | Deployment capped at 1.00. Expansion Momentum Score = 1.00. Account flagged as expansion candidate. Realized ARR = Contracted ARR (full realization). |
| **Mid-Year Expansion** | Contracted ARR updates monthly using `MAX(annual_commit_dollars)` across active contracts. No double-counting. |
| **Orphaned Logs** | Excluded in Step 0 (DQ-001). Not included in Deployment Score numerator. |
| **Rogue Usage** | Excluded in Step 0 (DQ-002). Usage outside contract window does not inflate any component. |

---

## 14. Worked example

**Account setup:**

| Field | Value |
|-------|-------|
| Contracted ARR | $500,000 |
| Included monthly credits | 100,000 |
| Monthly credits consumed | 80,000 |
| Healthy usage months (last 12) | 9 of 12 |
| Account_Health.health_color | Green |
| Months since contract start | 8 |
| Usage trend | Stable, no overage |

**Computation:**

```
Deployment Score    = MIN(1.0, 80,000 / 100,000) = 0.80
Sustained Usage     = 9 / 12 = 0.75              (window = MIN(8, 12) = 8 → 9 healthy / 8 active, capped: use actual 9/12 = 0.75)
Technical Health    = 1.00                         (Green → 1.00)
Expansion Momentum  = 0.70                         (8 months > 3 month guard; usage >= 70% in 6+ of trailing 6 months)

Shelfware override  → Deployment > 0, skip override

PRS = (0.80 × 0.40) + (0.75 × 0.30) + (1.00 × 0.20) + (0.70 × 0.10)
    = 0.320 + 0.225 + 0.200 + 0.070
    = 0.815

Realized ARR = $500,000 × 0.815 = $407,500
```

**Interpretation:**
$500K contracted. $407.5K realized — healthy account with strong deployment and sustained usage.
The $92.5K gap is moderate risk, driven by 9/12 sustained usage (3 months below the 30% threshold).
CSM action: identify what caused the 3 off-months and whether a usage pattern intervention is warranted.

---

## 15. Output schema

```sql
-- Primary output: account_month_realized_arr
account_id              VARCHAR
month                   DATE          -- first day of month (e.g. 2024-01-01)
contracted_arr          DECIMAL(15,2)
deployment_score        DECIMAL(5,4)  -- 0.0000 to 1.0000
sustained_usage_score   DECIMAL(5,4)
technical_health_score  DECIMAL(5,4)
expansion_momentum      DECIMAL(5,4)
prs                     DECIMAL(5,4)
realized_arr            DECIMAL(15,2)
prs_band                VARCHAR       -- Green / Yellow / Orange / Red
shelfware_override      BOOLEAN       -- TRUE if override fired
flag_overage            BOOLEAN       -- TRUE if raw consumption > 1.0 × included
months_in_window        INTEGER       -- actual window used for sustained usage

-- Secondary output: portfolio_monthly_summary
month                   DATE
total_contracted_arr    DECIMAL(15,2)
total_realized_arr      DECIMAL(15,2)
portfolio_prs           DECIMAL(5,4)  -- ARR-weighted
realization_rate_pct    DECIMAL(5,2)  -- 0.00 to 100.00
green_arr               DECIMAL(15,2)
yellow_arr              DECIMAL(15,2)
orange_arr              DECIMAL(15,2)
red_arr                 DECIMAL(15,2)
shelfware_arr           DECIMAL(15,2)
expansion_signal_arr    DECIMAL(15,2)

-- Tertiary output: dq_report
log_id                  VARCHAR
account_id              VARCHAR
date                    DATE
compute_credits_consumed DECIMAL(15,2)
dq_rule                 VARCHAR       -- DQ-001 or DQ-002
excluded_at             TIMESTAMP
```

---

## 16. Implementation pseudocode (for Claude Code)

```python
def compute_realized_arr(accounts_df, contracts_df, usage_logs_df, health_df, target_month):

    # ── Step 0: Data quality ───────────────────────────────────────────
    valid_accounts = set(accounts_df['account_id'])
    
    clean_logs = usage_logs_df[
        usage_logs_df['account_id'].isin(valid_accounts)          # DQ-001
        & (usage_logs_df['date'] >= month_start)                  # DQ-002
        & (usage_logs_df['date'] <= month_end)
    ]
    
    # ── Step 1: Contracted ARR ─────────────────────────────────────────
    active_contracts = contracts_df[
        (contracts_df['start_date'] <= month_end)
        & (contracts_df['end_date']   >= month_start)
    ]
    contracted_arr = (active_contracts
                      .groupby('account_id')['annual_commit_dollars']
                      .max())

    # ── Step 2: Deployment Score ───────────────────────────────────────
    monthly_consumed = (clean_logs
                        .groupby('account_id')['compute_credits_consumed']
                        .sum())
    included_monthly = (active_contracts
                        .groupby('account_id')['included_monthly_compute_credits']
                        .max())
    deployment = (monthly_consumed / included_monthly).clip(0, 1.0).fillna(0)

    # ── Step 3: Sustained Usage Score (trailing 12-month window) ──────
    window_start = month_start - relativedelta(months=11)
    trailing_logs = clean_logs[clean_logs['date'] >= window_start]
    
    monthly_trailing = (trailing_logs
                        .groupby(['account_id', pd.Grouper(key='date', freq='MS')])
                        ['compute_credits_consumed'].sum().reset_index())
    
    def sustained_score(account_id):
        acct_data = monthly_trailing[monthly_trailing['account_id'] == account_id]
        inc = included_monthly.get(account_id, 1)
        months_in_window = min(len(acct_data), 12)
        if months_in_window == 0:
            return 0.0
        healthy = (acct_data['compute_credits_consumed'] >= 0.30 * inc).sum()
        return healthy / months_in_window
    
    sustained = {aid: sustained_score(aid) for aid in contracted_arr.index}

    # ── Step 4: Technical Health Score ────────────────────────────────
    color_map = {'Green': 1.00, 'Yellow': 0.60, 'Red': 0.20}
    month_health = health_df[
        (health_df['date'] >= month_start) & (health_df['date'] <= month_end)
    ].copy()
    month_health['score'] = month_health['health_color'].map(color_map).fillna(0.60)
    health_score = month_health.groupby('account_id')['score'].mean()

    # ── Step 5: Expansion Momentum Score ──────────────────────────────
    def expansion_score(account_id, contract_start):
        months_active = (month_end - contract_start).days // 30
        if months_active < 3:
            return 0.10                                    # new account guard
        
        trailing_6 = clean_logs[
            (clean_logs['account_id'] == account_id)
            & (clean_logs['date'] >= month_start - relativedelta(months=5))
        ]
        inc = included_monthly.get(account_id, 1)
        monthly_totals = (trailing_6
                          .groupby(pd.Grouper(key='date', freq='MS'))
                          ['compute_credits_consumed'].sum())
        
        q_120 = (monthly_totals >= 1.20 * inc).sum()
        q_070 = (monthly_totals >= 0.70 * inc).sum()
        q_030 = (monthly_totals >= 0.30 * inc).sum()
        
        if q_120 >= 3: return 1.00
        if q_070 >= 3: return 0.70
        if q_030 >= 3: return 0.40
        return 0.10

    # ── Step 6: PRS with shelfware override ───────────────────────────
    results = []
    for account_id in contracted_arr.index:
        d  = deployment.get(account_id, 0)
        s  = sustained.get(account_id, 0)
        h  = health_score.get(account_id, 0.60)
        e  = expansion_score(account_id, ...)
        c  = contracted_arr[account_id]
        
        override = (d == 0 and s == 0)
        prs = 0.0 if override else (d*0.40 + s*0.30 + h*0.20 + e*0.10)
        
        results.append({
            'account_id':           account_id,
            'month':                month_start,
            'contracted_arr':       c,
            'deployment_score':     round(d, 4),
            'sustained_usage_score':round(s, 4),
            'technical_health_score':round(h, 4),
            'expansion_momentum':   round(e, 4),
            'prs':                  round(prs, 4),
            'realized_arr':         round(c * prs, 2),
            'prs_band':             prs_band(prs),
            'shelfware_override':   override,
            'flag_overage':         (monthly_consumed.get(account_id, 0) > included_monthly.get(account_id, 1)),
        })
    
    return pd.DataFrame(results)

def prs_band(prs):
    if prs >= 0.80: return 'Green'
    if prs >= 0.60: return 'Yellow'
    if prs >= 0.30: return 'Orange'
    return 'Red'
```

---

## 17. Testing criteria

| Test | Expected result |
|------|----------------|
| Shelfware account (zero usage, Red health) | PRS = 0.00, Realized ARR = $0, shelfware_override = True |
| Full deployment, all Green, consistent overages | PRS ≥ 0.90, Expansion Momentum = 1.00, flag_overage = True |
| Spike & Drop (90% in Month 1, zero after) | Sustained Usage ≈ 0.08, PRS penalized significantly |
| Mid-year expansion (2 overlapping contracts) | Contracted ARR = MAX(annual_commit_dollars), no double-count |
| Orphaned log (fake account_id) | Excluded in Step 0, appears in dq_report with DQ-001 |
| Rogue usage (pre-contract date) | Excluded in Step 0, appears in dq_report with DQ-002 |
| New account Month 1 | Expansion Momentum = 0.10 (new account guard fires) |
| Account with all Missing health records | Technical Health = 0.60 (neutral default) |
| PRS sum check | Weights 0.40 + 0.30 + 0.20 + 0.10 = 1.00 exactly |
| Portfolio PRS | ARR-weighted average, not simple mean |

---

## 18. Change log

| Version | Change |
|---------|--------|
| v1.0 | Initial draft — 4-component PRS with eARR formula |
| v2.0 | Six changes accepted: (1) Sustained Usage window capped at 12 months; (2) Missing health_color → 0.60 (was 0.40); (3) Expansion Momentum new-account guard (< 3 months → 0.10); (4) Expansion Momentum window defined as trailing 6 months; (5) Shelfware override added (D=0 AND S=0 → PRS=0); (6) Portfolio roll-up defined as ARR-weighted PRS; (7) DQ preprocessing defined as Step 0 |
