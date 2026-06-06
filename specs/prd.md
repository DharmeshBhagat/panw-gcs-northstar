# prd.md — Product Context & Rules
## PANW GCS · Realized ARR North Star Metric
**Version:** 2.0  
**Owner:** Principal PM, Centralized Data & AI / Analytics  
**Status:** Final — ready for AI-assisted implementation  
**Companion files:** `sys_arch.md`, `test_spec.md`

---

## 1. Core Objective

Palo Alto Networks Global Customer Services (GCS) is transitioning from a
traditional Bookings / TCV revenue model to an **Annual Recurring Revenue (ARR)
+ hybrid Consumption** model.

The existing TCV model records the full contract value at signing and has no
mechanism to detect whether customers deploy, adopt, or derive security value
from the platform. This produces **phantom ARR**: committed revenue at high
churn risk that is invisible until the renewal window.

**Target state:** Replace TCV as the primary success metric with **Realized ARR**
— a per-account, per-month score that measures how much contracted ARR is
actively being converted into healthy, sustained product usage.

---

## 2. North Star Metric — Exact Definition

```
Realized ARR = Contracted ARR × PRS

PRS (Platform Realization Score, 0.0–1.0) =
    (Deployment Score       × 0.40)
  + (Sustained Usage Score  × 0.30)
  + (Technical Health Score × 0.20)
  + (Expansion Momentum     × 0.10)

SHELFWARE OVERRIDE (evaluated BEFORE weighted sum):
  IF Deployment Score = 0.0 AND Sustained Usage Score = 0.0
  THEN PRS = 0.0
```

### Component formulas

**A. Deployment Score (D) — weight 0.40**
```
D = MIN(1.0, monthly_credits_consumed / included_monthly_credits)
```
- Catches: shelfware (D → 0), consistent overages (D capped at 1.0)
- Source: `daily_usage_logs.compute_credits_consumed` / `contracts.included_monthly_compute_credits`

**B. Sustained Usage Score (S) — weight 0.30**
```
S = healthy_months_in_window / window_size
window_size = MIN(months_since_contract_start, 12)
healthy_month = 1 IF monthly_consumption >= 0.30 × included_monthly_credits
               0 OTHERWISE
```
- Catches: spike-and-drop (S → 0.08 for 1/12 healthy month)
- Lookback: trailing 12-month cap prevents stale history dragging score

**C. Technical Health Score (H) — weight 0.20**
```
H = AVG(health_score) across all Account_Health records for account-month

health_color mapping:
  Green   → 1.00
  Yellow  → 0.60
  Missing → 0.60  (neutral default — not evidence of bad health)
  Red     → 0.20
```
- Source: `account_health.health_color`

**D. Expansion Momentum (E) — weight 0.10**
```
IF months_since_contract_start < 3:
    E = 0.10  (new account default — insufficient history)

ELSE (evaluate trailing 6-month window):
    q_120 = COUNT(months where consumption >= 1.20 × included)
    q_070 = COUNT(months where consumption >= 0.70 × included)
    q_030 = COUNT(months where consumption >= 0.30 × included)

    E = CASE
          WHEN q_120 >= 3 THEN 1.00
          WHEN q_070 >= 3 THEN 0.70
          WHEN q_030 >= 3 THEN 0.40
          ELSE 0.10
        END
```
- Catches: consistent overagers correctly identified as expansion signal (E → 1.00)
- New accounts with < 3 months of data receive neutral score 0.10

---

## 3. PRS Health Bands

| PRS range | Band | Label | CSM action |
|-----------|------|-------|------------|
| 0.80 – 1.00 | Green | Healthy | Identify expansion opportunity |
| 0.60 – 0.79 | Yellow | Watch | Proactive outreach; check H score |
| 0.30 – 0.59 | Orange | At-Risk | CSM intervention + PS engagement |
| 0.00 – 0.29 | Red | Critical | Executive engagement; 45-day recovery plan |

---

## 4. User Personas

### P1 — VP of Customer Success (executive)
- Needs: Portfolio-level Realized ARR by month, region, tier
- Key view: Total cARR vs Realized ARR; unrealized gap; trend over 12 months
- Decision: Resource allocation, CSM quota design, rep compensation changes

### P2 — CSM Account Rep
- Needs: Account-level PRS breakdown by component (D, S, H, E)
- Key view: Which component is dragging PRS? What action to take?
- Decision: Which accounts to prioritize this week; which to flag for PS

### P3 — Solutions Consultant
- Needs: Technical validation that the metric formula is correctly implemented
- Key view: Edge case test results; DQ report; formula audit trail
- Decision: Sign off on prototype for VP presentation

### P4 — Analytics / Data PM (spec owner)
- Needs: Metric governance; DQ pass/fail status; spec change log
- Key view: Full pipeline run logs; test results; version history

---

## 5. User Workflows

### Workflow 1 — Monthly metric refresh (primary)
```
1. Pipeline triggers on 1st of each month (batch)
2. Step 0: DQ preprocessing — filter orphaned + rogue logs
3. Steps 1–5: Compute cARR, D, S, H, E per account for target month
4. Step 6: Assemble PRS, apply shelfware override, compute Realized ARR
5. Write output to BigQuery: gcs_north_star.realized_arr_monthly (WRITE_TRUNCATE)
6. Write DQ report to: gcs_north_star.dq_report (WRITE_APPEND)
7. Dashboard cache invalidates; VP/CSM views refresh
```

### Workflow 2 — CSM account drill-down
```
1. CSM opens dashboard, filters to their rep_id
2. Sees ranked list of accounts by PRS (ascending = worst first)
3. Clicks account → sees PRS waterfall (D × 0.40, S × 0.30, H × 0.20, E × 0.10)
4. Sees which component is lowest → maps to intervention (deploy, re-onboard, support ticket)
5. Optional: flags account for escalation → writes to escalation table (Phase 2)
```

### Workflow 3 — Executive portfolio review (monthly)
```
1. VP opens dashboard → sees Portfolio PRS (ARR-weighted) and total Realized ARR
2. Drills into tier distribution (Green / Yellow / Orange / Red by ARR)
3. Filters by region → identifies underperforming geographies
4. Views top-10 at-risk accounts by unrealized ARR ($)
5. Exports summary for QBR slide (PDF / CSV download)
```

---

## 6. Invariants — Non-Negotiable Business Rules

The following rules MUST be enforced in every pipeline execution.
Any violation is a critical bug.

```
INV-001: Deployment Score MUST NOT exceed 1.0
         Rationale: Overages are expansion signals, not extra realization.
         Realized ARR must never exceed Contracted ARR.

INV-002: Realized ARR MUST NOT exceed Contracted ARR
         Assertion: realized_arr <= contracted_arr FOR ALL rows

INV-003: Shelfware override MUST fire when D=0.0 AND S=0.0
         Assertion: IF deployment_score=0 AND sustained_usage_score=0
                    THEN prs=0.0 AND realized_arr=0.0

INV-004: Orphaned logs MUST be excluded before computing D
         Definition: log.account_id NOT IN (SELECT account_id FROM accounts)
         Action: Write to dq_report; never include in D numerator

INV-005: Rogue usage MUST be excluded before computing D
         Definition: log.date < contract.start_date (or pre-2024)
         Action: Write to dq_report; never include in D numerator

INV-006: Overlapping contracts MUST use MAX(annual_commit_dollars)
         Rationale: Prevents double-counting ARR on expansion accounts
         Implementation: MAX() per account per month on active contracts

INV-007: Missing health_color MUST default to 0.60
         Rationale: Absence of health data ≠ bad health
         Never penalize a missing record below Yellow level

INV-008: PRS component weights MUST sum to exactly 1.0
         Assertion: 0.40 + 0.30 + 0.20 + 0.10 = 1.00

INV-009: New accounts (< 3 months active) MUST use E = 0.10
         Rationale: Insufficient history for expansion pattern scoring

INV-010: Portfolio PRS MUST be ARR-weighted, not simple average
         Formula: Σ(account_PRS × account_cARR) / Σ(account_cARR)
```

---

## 7. Data Quality Rules

| Rule ID | Description | Severity | Action |
|---------|-------------|----------|--------|
| DQ-001 | Usage log: account_id NOT IN accounts | HIGH | Exclude from D; write to dq_report |
| DQ-002 | Usage log: date before 2024-01-01 | MEDIUM | Exclude from D; write to dq_report |
| DQ-003 | Multiple active contracts same account-month | LOW | Use MAX(annual_commit_dollars) |
| DQ-004 | Contract: included_monthly_compute_credits = 0 | HIGH | Set D = NULL; exclude from portfolio |
| DQ-005 | Negative compute_credits_consumed value | CRITICAL | Exclude; alert engineering |

---

## 8. Out of Scope (Phase 1 Prototype)

```
OUT-001: Real-time / streaming data ingestion (batch processing only)
OUT-002: Multi-currency conversion (all values in USD)
OUT-003: User authentication or IAM layer (admin context assumed)
OUT-004: Product-level breakdown (Strata / Prisma Cloud / Cortex pillar split)
         → This requires product entitlement data not in current schema
         → Tracked as Phase 3 enhancement
OUT-005: Support ticket integration for H score (health_color proxy only)
         → Full MTTR / P1/P2 signal requires Customer Support Platform join
         → Tracked as Phase 3 enhancement
OUT-006: Predictive churn modeling (descriptive metric only)
OUT-007: Historical data before 2024-01-01
OUT-008: Automated CSM task creation from Red accounts
```

---

## 9. Acceptance Criteria Summary

The prototype is considered complete when:

1. `realized_arr_monthly` table exists in BigQuery with correct schema
2. All 10 invariants (INV-001 through INV-010) pass programmatic assertion
3. All 5 edge case scenarios in `test_spec.md` produce expected outputs
4. All 5 DQ rules in `dq_report` correctly flag injected anomalies
5. Streamlit dashboard loads Portfolio Summary, By Region, and By Rep views
6. Full 12-month pipeline run completes in < 60 seconds on 1,000 accounts
