-- PANW GCS North Star: output table definitions
-- Run via: python -m pipeline.setup_tables

CREATE TABLE IF NOT EXISTS `panw-gcs-northstar-498507.gcs_north_star.realized_arr_monthly`
(
  account_id               STRING  NOT NULL,
  month                    DATE    NOT NULL,
  contracted_arr           INT64   NOT NULL,
  deployment_score         NUMERIC NOT NULL,
  sustained_usage_score    NUMERIC NOT NULL,
  technical_health_score   NUMERIC NOT NULL,
  expansion_momentum       NUMERIC NOT NULL,
  prs                      NUMERIC NOT NULL,
  realized_arr             NUMERIC NOT NULL,
  prs_band                 STRING  NOT NULL,
  shelfware_override       BOOL    NOT NULL,
  flag_overage             BOOL    NOT NULL,
  months_in_window         INT64   NOT NULL,
  rep_id                   STRING  NOT NULL,
  rep_name                 STRING  NOT NULL,
  region                   STRING  NOT NULL,
  segment                  STRING  NOT NULL,
  industry                 STRING
)
PARTITION BY month
CLUSTER BY region, segment, prs_band;

CREATE TABLE IF NOT EXISTS `panw-gcs-northstar-498507.gcs_north_star.csm_monthly_summary`
(
  month                    DATE    NOT NULL,
  csm_id                   STRING  NOT NULL,
  rep_name                 STRING  NOT NULL,
  region                   STRING  NOT NULL,
  segment                  STRING  NOT NULL,
  account_count            INT64,
  total_contracted_arr     INT64,
  total_realized_arr       NUMERIC,
  portfolio_prs            NUMERIC,
  realization_rate_pct     NUMERIC,
  green_accounts           INT64,
  yellow_accounts          INT64,
  orange_accounts          INT64,
  red_accounts             INT64,
  shelfware_accounts       INT64,
  overage_accounts         INT64,
  at_risk_arr              NUMERIC
)
PARTITION BY month
CLUSTER BY region, segment;

CREATE TABLE IF NOT EXISTS `panw-gcs-northstar-498507.gcs_north_star.portfolio_summary`
(
  month                    DATE    NOT NULL,
  total_contracted_arr     INT64   NOT NULL,
  total_realized_arr       NUMERIC NOT NULL,
  unrealized_gap           NUMERIC NOT NULL,
  portfolio_prs            NUMERIC NOT NULL,
  realization_rate_pct     NUMERIC NOT NULL,
  green_accounts           INT64,
  green_arr                NUMERIC,
  yellow_accounts          INT64,
  yellow_arr               NUMERIC,
  orange_accounts          INT64,
  orange_arr               NUMERIC,
  red_accounts             INT64,
  red_arr                  NUMERIC,
  shelfware_accounts       INT64,
  shelfware_arr            NUMERIC,
  overage_accounts         INT64,
  overage_arr              NUMERIC,
  dq_001_orphaned_count    INT64,
  dq_002_rogue_count       INT64
)
PARTITION BY month;

CREATE TABLE IF NOT EXISTS `panw-gcs-northstar-498507.gcs_north_star.dq_report`
(
  run_timestamp            TIMESTAMP NOT NULL,
  log_id                   STRING,
  account_id               STRING,
  date                     DATE,
  compute_credits_consumed INT64,
  dq_rule                  STRING    NOT NULL,
  exclusion_reason         STRING
);
