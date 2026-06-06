-- Portfolio-level monthly summary for @target_month.
-- DQ counts are sourced from the most recent dq_report run (MAX run_timestamp).

DELETE FROM `panw-gcs-northstar-498507.gcs_north_star.portfolio_summary`
WHERE month = @target_month;

INSERT INTO `panw-gcs-northstar-498507.gcs_north_star.portfolio_summary`
(
  month, total_contracted_arr, total_realized_arr, unrealized_gap,
  portfolio_prs, realization_rate_pct,
  green_accounts, green_arr, yellow_accounts, yellow_arr,
  orange_accounts, orange_arr, red_accounts, red_arr,
  shelfware_accounts, shelfware_arr, overage_accounts, overage_arr,
  dq_001_orphaned_count, dq_002_rogue_count
)
WITH

arr AS (
  SELECT
    SUM(contracted_arr)                                                             AS total_contracted_arr,
    SUM(realized_arr)                                                               AS total_realized_arr,
    ROUND(SAFE_DIVIDE(SUM(prs * contracted_arr), SUM(contracted_arr)), 4)           AS portfolio_prs,
    ROUND(SAFE_DIVIDE(SUM(realized_arr), SUM(contracted_arr)) * 100, 2)            AS realization_rate_pct,
    COUNTIF(prs_band = 'Green')                                                     AS green_accounts,
    SUM(CASE WHEN prs_band = 'Green'  THEN contracted_arr ELSE 0 END)              AS green_arr,
    COUNTIF(prs_band = 'Yellow')                                                    AS yellow_accounts,
    SUM(CASE WHEN prs_band = 'Yellow' THEN contracted_arr ELSE 0 END)              AS yellow_arr,
    COUNTIF(prs_band = 'Orange')                                                    AS orange_accounts,
    SUM(CASE WHEN prs_band = 'Orange' THEN contracted_arr ELSE 0 END)              AS orange_arr,
    COUNTIF(prs_band = 'Red')                                                       AS red_accounts,
    SUM(CASE WHEN prs_band = 'Red'    THEN contracted_arr ELSE 0 END)              AS red_arr,
    COUNTIF(shelfware_override = TRUE)                                              AS shelfware_accounts,
    SUM(CASE WHEN shelfware_override  THEN contracted_arr ELSE 0 END)              AS shelfware_arr,
    COUNTIF(flag_overage = TRUE)                                                    AS overage_accounts,
    SUM(CASE WHEN flag_overage        THEN contracted_arr ELSE 0 END)              AS overage_arr
  FROM `panw-gcs-northstar-498507.gcs_north_star.realized_arr_monthly`
  WHERE month = @target_month
),

dq AS (
  SELECT
    COUNTIF(dq_rule = 'DQ-001') AS dq_001_orphaned_count,
    COUNTIF(dq_rule = 'DQ-002') AS dq_002_rogue_count
  FROM `panw-gcs-northstar-498507.gcs_north_star.dq_report`
  WHERE run_timestamp = (
    SELECT MAX(run_timestamp)
    FROM `panw-gcs-northstar-498507.gcs_north_star.dq_report`
  )
)

SELECT
  @target_month                                                                    AS month,
  arr.total_contracted_arr,
  arr.total_realized_arr,
  arr.total_contracted_arr - arr.total_realized_arr                                AS unrealized_gap,
  arr.portfolio_prs,
  arr.realization_rate_pct,
  arr.green_accounts,
  arr.green_arr,
  arr.yellow_accounts,
  arr.yellow_arr,
  arr.orange_accounts,
  arr.orange_arr,
  arr.red_accounts,
  arr.red_arr,
  arr.shelfware_accounts,
  arr.shelfware_arr,
  arr.overage_accounts,
  arr.overage_arr,
  dq.dq_001_orphaned_count,
  dq.dq_002_rogue_count
FROM arr
CROSS JOIN dq;
