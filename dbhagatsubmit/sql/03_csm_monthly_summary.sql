-- CSM monthly summary: aggregates realized_arr_monthly to rep level for @target_month.
-- portfolio_prs is ARR-weighted (INV-010): SUM(prs * contracted_arr) / SUM(contracted_arr).

DELETE FROM `panw-gcs-northstar-498507.gcs_north_star.csm_monthly_summary`
WHERE month = @target_month;

INSERT INTO `panw-gcs-northstar-498507.gcs_north_star.csm_monthly_summary`
(
  month, csm_id, rep_name, region, segment,
  account_count, total_contracted_arr, total_realized_arr,
  portfolio_prs, realization_rate_pct,
  green_accounts, yellow_accounts, orange_accounts, red_accounts,
  shelfware_accounts, overage_accounts, at_risk_arr
)
SELECT
  @target_month                                                                    AS month,
  rep_id                                                                           AS csm_id,
  MAX(rep_name)                                                                    AS rep_name,
  MAX(region)                                                                      AS region,
  MAX(segment)                                                                     AS segment,
  COUNT(DISTINCT account_id)                                                       AS account_count,
  SUM(contracted_arr)                                                              AS total_contracted_arr,
  SUM(realized_arr)                                                                AS total_realized_arr,
  ROUND(SAFE_DIVIDE(SUM(prs * contracted_arr), SUM(contracted_arr)), 4)            AS portfolio_prs,
  ROUND(SAFE_DIVIDE(SUM(realized_arr), SUM(contracted_arr)) * 100, 2)             AS realization_rate_pct,
  COUNTIF(prs_band = 'Green')                                                      AS green_accounts,
  COUNTIF(prs_band = 'Yellow')                                                     AS yellow_accounts,
  COUNTIF(prs_band = 'Orange')                                                     AS orange_accounts,
  COUNTIF(prs_band = 'Red')                                                        AS red_accounts,
  COUNTIF(shelfware_override = TRUE)                                               AS shelfware_accounts,
  COUNTIF(flag_overage = TRUE)                                                     AS overage_accounts,
  SUM(CASE WHEN prs_band IN ('Red', 'Orange') THEN contracted_arr ELSE 0 END)     AS at_risk_arr
FROM `panw-gcs-northstar-498507.gcs_north_star.realized_arr_monthly`
WHERE month = @target_month
GROUP BY rep_id;
