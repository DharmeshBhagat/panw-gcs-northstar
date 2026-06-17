# Realized ARR — North Star Metric for GCS

**Author:** Dharmesh Bhagat, Principal PM
**Project:** GCS transition from TCV to ARR + Consumption model
**Stack:** Python · Google BigQuery · Streamlit · Claude Code (spec-driven development)
**Data:** Synthetic dataset — 1,000 accounts · 12 months · ~250K rows

> **Note:** All data in this repository is synthetically generated for demonstration purposes.
> No real customer, financial, or operational data is included.

> **Note:** Realized ARR is an operating metric for customer value realization. It is not
> intended to represent GAAP revenue recognition or official financial reporting.

---

## Live dashboard

🔗 **[https://dbhagatnsdemo.streamlit.app/](https://dbhagatnsdemo.streamlit.app/)**

Deployed on Streamlit Cloud — no setup required. Open in any browser.
Connected to BigQuery dataset: `gcs_north_star`

---

## GitHub repository

🔗 **[https://github.com/DharmeshBhagat/panw-gcs-northstar](https://github.com/DharmeshBhagat/panw-gcs-northstar)**

---

## What this project does

GCS currently measures success through Total Contract Value (TCV) — a model
that treats a contract signature as an immediate win. This can create a material
blind spot: a $500K shelfware account and a $500K fully-deployed account look
identical until renewal.

This project defines, implements, and validates **Realized ARR** — a metric that
measures how much contracted ARR is actively being converted into healthy, sustained
product usage.

```
Realized ARR = Contracted ARR × PRS

PRS (Platform Realization Score) =
    (Deployment Score       × 0.40)
  + (Sustained Usage Score  × 0.30)
  + (Technical Health Score × 0.20)
  + (Expansion Momentum     × 0.10)

Override: IF Deployment = 0 AND Sustained = 0 → PRS = 0.00
```

**Key finding (Synthetic December 2024 portfolio):**
$86.3M contracted · $56.3M realized · **$30M unrealized gap** identified at account level.
Portfolio PRS peaked at 0.706 in June and declined to 0.652 by December.

---

## Product judgment: why an explainable score first?

For the MVP, I intentionally used a transparent weighted score instead of a
black-box ML model.

Reason:
- The metric may influence executive decisions and future compensation design.
- CS, Sales, and Finance leaders need to understand why an account is marked
  healthy, at-risk, or expansion-ready.
- Data quality and lifecycle-stage exceptions must be visible before automation.
- Predictive churn and expansion propensity models are better suited for Phase 2
  after the baseline metric is trusted.

---

## Recommended rollout

This prototype should not directly replace compensation metrics on day one.

Recommended path:
1. Run Realized ARR as a shadow North Star metric for one quarter.
2. Compare against current ARR, TCV, renewal, support, and account-health outcomes.
3. Tune PRS weights with Customer Success, Solutions Consulting, Finance, and Data/AI.
4. Establish data-confidence and exception-handling thresholds.
5. Introduce into compensation only after behavior impact is validated.

---

## How to navigate this repository

| If you want to... | Go to... |
|-------------------|----------|
| Understand why this metric was designed this way | `specs/BRD_v2.md` or `specs/BRD_v3_Roundtable_Validated.md` |
| Read the metric formula and edge case definitions | `specs/Realized_ARR_Spec_v2.md` |
| Read the product rules and business invariants | `specs/prd.md` |
| Read the technical architecture and SQL logic | `specs/sys_arch.md` |
| See how the pipeline was built step by step | `specs/phase2_execution_guide.md` |
| Run the data generation | `data_generation/generate_dataset.py` |
| Run the metric pipeline | `pipeline_and_tests/pipeline/run_pipeline.py` |
| Run the test suite | `pipeline_and_tests/tests/` |
| Launch the dashboard locally | `dashboard/dashboard.py` |
| View the dashboard live | https://dbhagatnsdemo.streamlit.app/ |
| See the executive presentation | `presentation/` |

---

## Repository structure

```
panw-gcs-northstar/
│
├── data_generation/
│   ├── generate_dataset.py            # Generates all 5 BigQuery tables using Faker
│   └── requirements.txt               # Python dependencies
│
├── specs/
│   ├── BRD_v1_Discovery.docx          # Original discovery document — problem framing,
│   │                                  #   data schema mapping, AI early warning design
│   ├── BRD_v2.md                      # Full discovery methodology — first principles
│   │                                  #   derivation, metric options evaluated,
│   │                                  #   retrospective (Appendix A)
│   ├── BRD_v3_Roundtable_Validated.md # CS Leaders Roundtable validation (June 2025) —
│   │                                  #   external signal map, compensation design,
│   │                                  #   outcome-based pricing context
│   ├── Realized_ARR_Spec_v2.md        # Complete metric definition: formula, component
│   │                                  #   sub-formulas, edge cases, output schema,
│   │                                  #   pseudocode, worked example
│   ├── prd.md                         # Product requirements: 10 invariants, 5 DQ rules,
│   │                                  #   4 user personas, 3 workflows, 8 out-of-scope
│   ├── sys_arch.md                    # Technical architecture: BigQuery DDL, SQL for
│   │                                  #   all 6 pipeline steps, 10 engineering conventions
│   ├── test_spec.md                   # Verification spec: 22 assertions with exact
│   │                                  #   inputs and expected outputs
│   ├── claude_code_prompts.md         # Exact prompts used with Claude Code for each
│   │                                  #   of the 13 build steps
│   └── phase2_execution_guide.md      # Step-by-step execution guide used to build
│                                      #   the pipeline, tests, and dashboard
│
├── pipeline_and_tests/
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── config.py                  # Reads PROJECT_ID / DATASET_ID from environment
│   │   ├── dq.py                      # Step 0: DQ preprocessing functions
│   │   ├── setup_tables.py            # Creates 4 output tables in BigQuery
│   │   └── run_pipeline.py            # Orchestrates all SQL steps across 12 months
│   ├── sql/
│   │   ├── 00_setup_tables.sql        # DDL for all 4 output tables
│   │   ├── 01_dq_preprocessing.sql    # clean_usage_logs view + dq_report insert
│   │   ├── 02_realized_arr_monthly.sql # Core metric: Steps 1–6, account × month grain
│   │   ├── 03_csm_monthly_summary.sql  # Aggregated to CSM rep level
│   │   └── 04_portfolio_summary.sql    # Single-row monthly portfolio rollup
│   ├── tests/
│   │   ├── conftest.py                # run_query() helper, BigQuery fixture, constants
│   │   ├── test_dq.py                 # 5 DQ assertions (orphaned, rogue, negative)
│   │   ├── test_invariants.py         # 5 business rule invariants (caps, overrides)
│   │   ├── test_edge_cases.py         # 5 edge case scenarios (shelfware, spike-drop…)
│   │   └── test_integration.py        # 7 end-to-end pipeline tests
│   └── test_results.txt               # Latest local test run output (22/22 passing)
│
├── dashboard/
│   └── dashboard.py                   # Streamlit app — 6 pages with sidebar filters,
│                                      #   row-click navigation, help tooltips
│                                      #   Live: https://dbhagatnsdemo.streamlit.app/
│
├── presentation/
│   ├── GCS_Realized_ARR_Presentation.pptx
│   └── GCS_Realized_ARR_Presentation.pdf
│
├── requirements.txt                   # Root requirements for Streamlit Cloud deployment
├── .env.example                       # Environment variable template
├── .gitignore
└── README.md
```

---

## Prerequisites

- Python 3.11+
- Google Cloud account with BigQuery enabled (billing required — DML needs it)
- `gcloud` CLI installed and authenticated

---

## Setup

**1. Clone and create environment**
```bash
git clone https://github.com/DharmeshBhagat/panw-gcs-northstar.git
cd panw-gcs-northstar
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Authenticate with Google Cloud**
```bash
gcloud auth application-default login
gcloud config set project YOUR_GCP_PROJECT_ID
```

**3. Configure environment**
```bash
cp .env.example .env
# Edit .env — set BIGQUERY_PROJECT_ID=your-gcp-project-id
export BIGQUERY_PROJECT_ID=your-gcp-project-id
```

**4. Create BigQuery dataset**

Go to [console.cloud.google.com/bigquery](https://console.cloud.google.com/bigquery),
create a dataset named `gcs_north_star` in US (multi-region).

---

## Running the project

### Step 1 — Generate synthetic data and upload to BigQuery

```bash
python data_generation/generate_dataset.py \
  --project YOUR_GCP_PROJECT_ID \
  --dataset gcs_north_star
```

Generates and uploads 5 tables:

| Table | Rows | Notes |
|-------|------|-------|
| `csm_rep` | 50 | 4 regions, 2 segments |
| `accounts` | 1,000 | 8 industries, Faker company names |
| `contracts` | ~1,200 | Includes 50 mid-year expansion contracts |
| `daily_usage_logs` | ~200K | Includes 350 injected orphaned/rogue rows |
| `account_health` | ~50K | Weekly health checks per account |

All 5 edge cases are injected: shelfware (10%), spike-and-drop (5%),
consistent overagers (15%), mid-year expansions, orphaned and rogue usage logs.

### Step 2 — Create output tables

```bash
python pipeline_and_tests/pipeline/setup_tables.py
```

### Step 3 — Run the pipeline (all 12 months)

```bash
python pipeline_and_tests/pipeline/run_pipeline.py
```

Single month (faster for testing):
```bash
python pipeline_and_tests/pipeline/run_pipeline.py --month 2024-12-01
```

### Step 4 — Run the test suite

```bash
BIGQUERY_PROJECT_ID=your-gcp-project-id \
  .venv/bin/pytest pipeline_and_tests/tests/ -v
```

Expected: **22/22 passed** · See `pipeline_and_tests/test_results.txt`

### Step 5 — Launch the dashboard locally

```bash
BIGQUERY_PROJECT_ID=your-gcp-project-id \
  streamlit run dashboard/dashboard.py
```

Opens at [http://localhost:8501](http://localhost:8501)

Or use the live deployed version — no setup needed:
**[https://dbhagatnsdemo.streamlit.app/](https://dbhagatnsdemo.streamlit.app/)**

---

## Dashboard pages

| Page | Title | What it shows |
|------|-------|---------------|
| **Home** | Realized ARR Scorecard | Recommendation banner · $30M gap · PRS components · Recover ARR / Expand ARR · Decision ask |
| **Portfolio** | Portfolio View | Monthly trend Jan–Dec · Dynamic insight · Jan/Jun/Dec milestone table |
| **By Region** | By Region | Realized ARR + PRS% per region · So-what line · Recommended Action column |
| **By Rep** | CSM / Rep Realization View — Shadow Metric | Rep leaderboard · Shadow disclaimer · Coaching framing · Drill-down to accounts |
| **By Account** | By Account | Company search · Row-click drill-down · PRS waterfall · Recommended Next Action · 12-month trend |
| **Data Quality** | Data Quality Monitor | Data Confidence % · DQ rule breakdown · Anomaly counts · Pipeline status |

All pages share sidebar filters: Month · Region · Segment · Health Band · Industry · Company search.
All help icons (?) show formula definitions from the spec documents on hover.

---

## Synthetic portfolio results (December 2024 snapshot)

| Metric | Value |
|--------|-------|
| Contracted ARR | $86.3M |
| Realized ARR | $56.3M |
| Unrealized gap | **$30.0M** |
| Portfolio PRS | 0.652 |
| Realization rate | 65.2% |
| Green accounts (PRS ≥ 0.80) | 727 |
| Red accounts (PRS < 0.30) | 182 |
| Shelfware accounts | 100 |

Portfolio PRS peaked at 0.706 in June and declined to 0.652 by December.
H2 ARR additions were less healthy than the existing base — the core finding
that motivates Realized ARR as a North Star metric.

---

## Architecture

```
BigQuery (5 source tables)
  ↓
Step 0: DQ Preprocessing
  → clean_usage_logs view (DQ-001: orphaned, DQ-002: rogue excluded)
  → dq_report (audit log with exclusion reasons)
  ↓
Steps 1–6: Metric computation (per account × month)
  → contracted_arr     MAX(annual_commit_dollars) — handles overlapping contracts
  → deployment_score   D = MIN(1.0, consumed / included)
  → sustained_score    S = healthy_months / MIN(months_active, 12)
  → health_score       H = AVG(Green=1.0, Yellow=0.60, Missing=0.60, Red=0.20)
  → expansion_momentum E = trailing 6-month pattern (new account guard < 3 months)
  → PRS                D×0.40 + S×0.30 + H×0.20 + E×0.10
  → shelfware_override D=0 AND S=0 → PRS=0.00 (no phantom realized value)
  ↓
4 output tables
  → realized_arr_monthly    account × month grain
  → csm_monthly_summary     rep × month grain (ARR-weighted PRS)
  → portfolio_summary       single row per month
  → dq_report               append-only audit log
  ↓
Streamlit dashboard — 6 pages
  → Live: https://dbhagatnsdemo.streamlit.app/
```

---

## Document lineage

The project follows a spec-driven AI development methodology.
Documents were produced in this order — each layer feeds the next:

```
Discovery (why)                  BRD_v1, BRD_v2, BRD_v3
    ↓
Product rules (what)             prd.md — invariants, DQ rules, workflows
    ↓
Technical design (how)           sys_arch.md — DDL, SQL steps, conventions
    ↓
Verification criteria (done when) test_spec.md — 22 assertions
    ↓
Build execution                  claude_code_prompts.md + phase2_execution_guide.md
    ↓
Code                             pipeline_and_tests/ + dashboard/
    ↓
Validation                       22/22 tests passing against live BigQuery
```

The BRD documents are particularly important for context:

- **BRD_v2.md** — Appendix A contains the full retrospective: what would be done
  differently with today's tech stack, including dbt, empirical weight validation,
  and agentic workflows.

- **BRD_v3_Roundtable_Validated.md** — Includes a CS Leaders Roundtable (June 2025)
  signal map that validated the importance of balancing deployment, sustained usage,
  technical health, and expansion signals. That feedback supported the 40/30/20/10
  MVP weighting used in this prototype.

---

## Data quality rules

| Rule | Description | Rows in dataset |
|------|-------------|-----------------|
| DQ-001 | Orphaned logs — account_id not in accounts table | 200 |
| DQ-002 | Rogue usage — date before 2024-01-01 | 150 |
| DQ-003 | Overlapping contracts — resolved via MAX() | ~50 accounts |
| DQ-004 | Zero included credits — deployment set to NULL | 0 (clean) |
| DQ-005 | Negative consumption values | 0 (clean) |

---

## Edge cases handled

| Edge case | Injected at | Detection | PRS behavior |
|-----------|------------|-----------|-------------|
| Shelfware | 10% of accounts | D=0, S=0 | Override → PRS=0.00 |
| Spike & Drop | 5% of accounts | S < 0.15 with D > 0 | S collapses score to Red |
| Consistent Overager | 15% of accounts | flag_overage=True | D capped at 1.0, E=1.00 |
| Mid-year Expansion | ~50 accounts | 2+ active contracts | MAX(ARR) prevents double-count |
| Orphaned/Rogue logs | 350 rows | DQ-001, DQ-002 | Excluded before any computation |

---

## Cost

- Dataset size: ~250K rows
- Query cost on BigQuery: effectively $0 (well within 1 TB/month free tier)
- Storage: < 10 MB
- BigQuery billing must be enabled for DML (INSERT/DELETE) operations

---

## License

This project uses synthetic data generated for demonstration purposes only.
No real customer, financial, or operational data is included.
