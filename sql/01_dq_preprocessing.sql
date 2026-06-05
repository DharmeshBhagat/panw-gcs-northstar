-- DQ pre-processing: clean view + audit log
-- Statement 1: clean view (excludes DQ-001 / DQ-002 / DQ-005 rows)
CREATE OR REPLACE VIEW `panw-gcs-northstar-498507.gcs_north_star.clean_usage_logs` AS
SELECT
  log_id,
  account_id,
  date,
  compute_credits_consumed
FROM `panw-gcs-northstar-498507.gcs_north_star.daily_usage_logs`
WHERE
  account_id IN (SELECT account_id FROM `panw-gcs-northstar-498507.gcs_north_star.accounts`)
  AND date >= DATE('2024-01-01')
  AND compute_credits_consumed >= 0;

-- Statement 2: write failing rows to dq_report (one rule per row, priority: 001 > 002 > 005)
INSERT INTO `panw-gcs-northstar-498507.gcs_north_star.dq_report`
  (run_timestamp, log_id, account_id, date, compute_credits_consumed, dq_rule, exclusion_reason)
SELECT
  CURRENT_TIMESTAMP()         AS run_timestamp,
  log_id,
  account_id,
  date,
  compute_credits_consumed,
  CASE
    WHEN account_id NOT IN (
      SELECT account_id FROM `panw-gcs-northstar-498507.gcs_north_star.accounts`
    )                          THEN 'DQ-001'
    WHEN date < DATE('2024-01-01') THEN 'DQ-002'
    ELSE                            'DQ-005'
  END                         AS dq_rule,
  CASE
    WHEN account_id NOT IN (
      SELECT account_id FROM `panw-gcs-northstar-498507.gcs_north_star.accounts`
    )                          THEN 'Orphaned log: account_id not found in accounts table'
    WHEN date < DATE('2024-01-01') THEN 'Rogue date: log predates 2024-01-01 analysis window'
    ELSE                            'Negative usage: compute_credits_consumed is below zero'
  END                         AS exclusion_reason
FROM `panw-gcs-northstar-498507.gcs_north_star.daily_usage_logs`
WHERE
  account_id NOT IN (SELECT account_id FROM `panw-gcs-northstar-498507.gcs_north_star.accounts`)
  OR date < DATE('2024-01-01')
  OR compute_credits_consumed < 0;
