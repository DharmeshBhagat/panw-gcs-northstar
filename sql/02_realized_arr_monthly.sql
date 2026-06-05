-- Realized ARR monthly computation for @target_month (DATE parameter).
-- WRITE_TRUNCATE pattern: delete then insert so reruns are idempotent.

DELETE FROM `panw-gcs-northstar-498507.gcs_north_star.realized_arr_monthly`
WHERE month = @target_month;

INSERT INTO `panw-gcs-northstar-498507.gcs_north_star.realized_arr_monthly`
(
  account_id, month, contracted_arr, deployment_score, sustained_usage_score,
  technical_health_score, expansion_momentum, prs, realized_arr, prs_band,
  shelfware_override, flag_overage, months_in_window, rep_id, rep_name,
  region, segment, industry
)
WITH

-- Step 1: one row per account with an active contract in target month (INV-006)
active_contracts AS (
  SELECT
    account_id,
    MAX(annual_commit_dollars)            AS contracted_arr,
    MAX(included_monthly_compute_credits) AS included_monthly_credits,
    MIN(start_date)                       AS earliest_start
  FROM `panw-gcs-northstar-498507.gcs_north_star.contracts`
  WHERE start_date <= LAST_DAY(@target_month, MONTH)
    AND end_date   >= @target_month
  GROUP BY account_id
),

-- Consumption for the target month only
monthly_consumption AS (
  SELECT
    account_id,
    SUM(compute_credits_consumed) AS monthly_consumed
  FROM `panw-gcs-northstar-498507.gcs_north_star.clean_usage_logs`
  WHERE DATE_TRUNC(date, MONTH) = @target_month
  GROUP BY account_id
),

-- Step 2: deployment score (INV-001: LEAST caps at 1.0)
deployment AS (
  SELECT
    ac.account_id,
    ac.contracted_arr,
    ac.included_monthly_credits,
    ac.earliest_start,
    COALESCE(mc.monthly_consumed, 0)                                  AS monthly_consumed,
    ROUND(
      LEAST(1.0, COALESCE(mc.monthly_consumed, 0.0) / NULLIF(ac.included_monthly_credits, 0)),
      4
    )                                                                 AS deployment_score,
    COALESCE(mc.monthly_consumed, 0) > ac.included_monthly_credits    AS flag_overage
  FROM active_contracts ac
  LEFT JOIN monthly_consumption mc USING (account_id)
),

-- Monthly totals over trailing 12-month window for sustained score
trailing_usage AS (
  SELECT
    account_id,
    DATE_TRUNC(date, MONTH)           AS usage_month,
    SUM(compute_credits_consumed)     AS monthly_consumed
  FROM `panw-gcs-northstar-498507.gcs_north_star.clean_usage_logs`
  WHERE DATE_TRUNC(date, MONTH) BETWEEN DATE_TRUNC(DATE_SUB(@target_month, INTERVAL 11 MONTH), MONTH)
                                    AND @target_month
  GROUP BY account_id, DATE_TRUNC(date, MONTH)
),

-- Step 3: sustained usage score
sustained AS (
  SELECT
    d.account_id,
    LEAST(DATE_DIFF(@target_month, d.earliest_start, MONTH) + 1, 12) AS months_in_window,
    COUNTIF(tu.monthly_consumed >= 0.30 * d.included_monthly_credits) AS healthy_months,
    ROUND(
      SAFE_DIVIDE(
        COUNTIF(tu.monthly_consumed >= 0.30 * d.included_monthly_credits),
        LEAST(DATE_DIFF(@target_month, d.earliest_start, MONTH) + 1, 12)
      ),
      4
    )                                                                  AS sustained_usage_score
  FROM deployment d
  LEFT JOIN trailing_usage tu
    ON tu.account_id = d.account_id
  GROUP BY d.account_id, d.earliest_start, d.included_monthly_credits
),

-- Step 4: technical health score from account_health
health_scores AS (
  SELECT
    account_id,
    COALESCE(
      AVG(
        CASE health_color
          WHEN 'Green'  THEN 1.00
          WHEN 'Yellow' THEN 0.60
          WHEN 'Red'    THEN 0.20
          ELSE               0.60
        END
      ),
      0.60
    ) AS technical_health_score
  FROM `panw-gcs-northstar-498507.gcs_north_star.account_health`
  WHERE DATE_TRUNC(date, MONTH) = @target_month
  GROUP BY account_id
),

-- Monthly totals over trailing 6 months for expansion momentum
trailing_6 AS (
  SELECT
    account_id,
    DATE_TRUNC(date, MONTH)       AS usage_month,
    SUM(compute_credits_consumed) AS monthly_consumed
  FROM `panw-gcs-northstar-498507.gcs_north_star.clean_usage_logs`
  WHERE DATE_TRUNC(date, MONTH) BETWEEN DATE_TRUNC(DATE_SUB(@target_month, INTERVAL 5 MONTH), MONTH)
                                    AND @target_month
  GROUP BY account_id, DATE_TRUNC(date, MONTH)
),

-- Step 5: expansion momentum
expansion AS (
  SELECT
    d.account_id,
    DATE_DIFF(@target_month, d.earliest_start, MONTH) + 1 AS months_active,
    IF(
      DATE_DIFF(@target_month, d.earliest_start, MONTH) + 1 < 3,
      0.10,
      CASE
        WHEN COUNTIF(t6.monthly_consumed >= 1.20 * d.included_monthly_credits) >= 3 THEN 1.00
        WHEN COUNTIF(t6.monthly_consumed >= 0.70 * d.included_monthly_credits) >= 3 THEN 0.70
        WHEN COUNTIF(t6.monthly_consumed >= 0.30 * d.included_monthly_credits) >= 3 THEN 0.40
        ELSE 0.10
      END
    ) AS expansion_momentum
  FROM deployment d
  LEFT JOIN trailing_6 t6
    ON t6.account_id = d.account_id
  GROUP BY d.account_id, d.earliest_start, d.included_monthly_credits
)

-- Final assembly: apply weights, shelfware override (INV-003), and dimension joins
-- CAST to NUMERIC required: ROUND/LEAST/arithmetic on FLOAT64 literals returns FLOAT64
SELECT
  d.account_id,
  @target_month                                                                   AS month,
  d.contracted_arr,
  CAST(d.deployment_score AS NUMERIC)                                             AS deployment_score,
  CAST(s.sustained_usage_score AS NUMERIC)                                        AS sustained_usage_score,
  CAST(COALESCE(h.technical_health_score, 0.60) AS NUMERIC)                       AS technical_health_score,
  CAST(e.expansion_momentum AS NUMERIC)                                           AS expansion_momentum,

  -- PRS: hard cap at 1.0 (INV-001/INV-002), shelfware override forces 0.0 (INV-003)
  CAST(LEAST(1.0,
    CASE
      WHEN d.deployment_score = 0.0 AND s.sustained_usage_score = 0.0 THEN 0.0
      ELSE ROUND(
        d.deployment_score        * 0.40
        + s.sustained_usage_score * 0.30
        + COALESCE(h.technical_health_score, 0.60) * 0.20
        + e.expansion_momentum    * 0.10,
        4
      )
    END
  ) AS NUMERIC)                                                                   AS prs,

  -- Realized ARR: cap prs at 1.0 before multiplying so realized_arr never > contracted_arr
  CAST(ROUND(
    d.contracted_arr * LEAST(1.0,
      CASE
        WHEN d.deployment_score = 0.0 AND s.sustained_usage_score = 0.0 THEN 0.0
        ELSE ROUND(
          d.deployment_score        * 0.40
          + s.sustained_usage_score * 0.30
          + COALESCE(h.technical_health_score, 0.60) * 0.20
          + e.expansion_momentum    * 0.10,
          4
        )
      END
    ),
    2
  ) AS NUMERIC)                                                                   AS realized_arr,

  CASE
    WHEN d.deployment_score = 0.0 AND s.sustained_usage_score = 0.0 THEN 'Red'
    WHEN LEAST(1.0, ROUND(
           d.deployment_score * 0.40 + s.sustained_usage_score * 0.30
           + COALESCE(h.technical_health_score, 0.60) * 0.20
           + e.expansion_momentum * 0.10, 4
         )) >= 0.80 THEN 'Green'
    WHEN LEAST(1.0, ROUND(
           d.deployment_score * 0.40 + s.sustained_usage_score * 0.30
           + COALESCE(h.technical_health_score, 0.60) * 0.20
           + e.expansion_momentum * 0.10, 4
         )) >= 0.60 THEN 'Yellow'
    WHEN LEAST(1.0, ROUND(
           d.deployment_score * 0.40 + s.sustained_usage_score * 0.30
           + COALESCE(h.technical_health_score, 0.60) * 0.20
           + e.expansion_momentum * 0.10, 4
         )) >= 0.30 THEN 'Orange'
    ELSE 'Red'
  END                                                                             AS prs_band,

  (d.deployment_score = 0.0 AND s.sustained_usage_score = 0.0)                   AS shelfware_override,
  d.flag_overage,
  s.months_in_window,

  -- Dimension joins
  a.rep_id,
  c.name                                                                          AS rep_name,
  c.region,
  c.segment,
  a.industry

FROM deployment d
JOIN sustained   s ON s.account_id = d.account_id
JOIN expansion   e ON e.account_id = d.account_id
JOIN `panw-gcs-northstar-498507.gcs_north_star.accounts` a
  ON a.account_id = d.account_id
JOIN `panw-gcs-northstar-498507.gcs_north_star.csm_rep` c
  ON c.csm_id = a.rep_id
LEFT JOIN health_scores h ON h.account_id = d.account_id;
