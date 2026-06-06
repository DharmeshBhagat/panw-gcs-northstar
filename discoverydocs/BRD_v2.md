# Business Requirements Document
## North Star Metric Discovery: From TCV to Realized ARR
### Palo Alto Networks · Global Customer Services (GCS) · Centralized Data & AI

**Author:** Dharmesh Bhagat, Principal Product Manager  
**Version:** 2.0 · Status: Final  
**Audience:** VP Customer Success · Head of Customer Analytics · GCS Leadership

---

## Table of Contents

1. [Executive Context](#1-executive-context)
2. [Discovery Methodology](#2-discovery-methodology)
3. [Phase 1 — Data Collection, Signal Mapping & BU Owner Pain Points](#3-phase-1--data-collection-signal-mapping--bu-owner-pain-points)
4. [Phase 2 — First Principles Deconstruction](#4-phase-2--first-principles-deconstruction)
5. [Phase 3 — System Thinking Framework](#5-phase-3--system-thinking-framework)
6. [Metric Options Evaluated](#6-metric-options-evaluated)
7. [PANW-Specific: TCV vs. New Metric Analysis](#7-panw-specific-tcv-vs-new-metric-analysis)
8. [North Star Selection: Why Realized ARR Wins](#8-north-star-selection-why-realized-arr-wins)
9. [Final Metric Specification Summary](#9-final-metric-specification-summary)
10. [AI-Assisted Early Warning Layer & Signal Library](#10-ai-assisted-early-warning-layer--signal-library)
11. [Data Quality Trap Analysis & Prioritized Test Roadmap](#11-data-quality-trap-analysis--prioritized-test-roadmap)
12. [Implementation & Governance](#12-implementation--governance)

---

## 1. Executive Context

### The Problem in One Sentence

GCS is measuring success by the size of contracts signed, while the business is
actually won or lost in the 180 days after signing.

### The Business Inflection Point

Palo Alto Networks is executing the most ambitious pricing transition in its history
— moving from a Total Contract Value (TCV) / Bookings model to Annual Recurring Revenue
(ARR) with hybrid consumption-based pricing. This transition creates a fundamental
measurement gap:

- **The old model** rewarded signatures. A $3M TCV deal booked on Day 1 looked like
  a win regardless of whether the customer ever deployed the product.
- **The new model** requires a metric that rewards deployment, consumption, sustained
  usage, and technical health — not just the legal commitment on paper.

GCS leadership is currently debating how to measure success, incentivize the right
behaviors, and compensate account representatives under this new paradigm. This
document captures the full discovery process that led to the recommended North Star
metric.

### The Strategic Stakes

| Business Fact | Implication |
|---|---|
| PANW NGS ARR at Q3 FY26: **$8.1B committed** | Every 1-point improvement in realization = ~$81M more real ARR |
| Customers on 3 platforms earn **$14.3M ARR** vs $1.8M on 1 platform | Path to $15B NGS ARR goal runs through deepening, not just signing |
| Platformization bridge financing from FY2024 | Discounted/free products will not renew if customers don't deploy |
| Shelfware in security = unprotected attack surface | Uniquely high reputational and brand risk vs. any other SaaS category |

---

## 2. Discovery Methodology

### My Approach: Three-Phase PM Discovery

This was not a requirements-gathering exercise. It was a ground-up product discovery
that treated "how to measure GCS success" as a product problem — with users, use cases,
signal sources, and success criteria to define from scratch.

```
Phase 1               Phase 2                    Phase 3
─────────             ─────────────────          ─────────────────────
DATA                  FIRST PRINCIPLES           SYSTEM THINKING
COLLECTION            DECONSTRUCTION             FRAMEWORK

What signals          Strip away all             How do the signals,
exist? What do        SaaS assumptions.          components, and
we know? What         What are the               incentives connect
is the data           absolute truths            into a coherent
quality? What         of PANW's business?        operating system?
do BU owners
actually feel?
```

### Why I Did Not Start With the Formula

The instinct in any metric initiative is to jump to formula design. I deliberately
avoided this. The formula is the output of discovery, not the input. Starting with
the formula inverts the process and produces metrics that are easy to calculate but
misaligned with actual business reality.

Instead, I started with three questions:

1. **What does a PANW customer actually pay for?**
2. **What does GCS have to deliver to earn that payment every year?**
3. **What data do we actually have, and how clean is it?**

---

## 3. Phase 1 — Data Collection, Signal Mapping & BU Owner Pain Points

### 3.1 Data Sources Inventoried

| Data Source | System | Signals Available | Quality | Business Question Answered |
|---|---|---|---|---|
| **Contract data** | CRM / SFDC | annual_commit_dollars, start_date, end_date, included_credits | High | What did the customer commit to pay? |
| **Product usage / consumption** | Cortex XSIAM, Strata Panorama, Prisma Cloud credits | Daily compute credits, log sources, assets scanned | Medium — orphaned + rogue logs present | Is the customer using what they bought? |
| **Technical health signals** | Customer Support Platform | P1/P2 volume, MTTR, SLA breach, health_color | Medium — lagging indicator | Is the platform technically stable? |
| **Deployment milestones** | Professional Services | Go-live dates, % modules deployed | Medium — manual entry risk | Has the customer turned the product on? |
| **Customer 360** | Unified CS view | QBR outcomes, CSM health notes, EBR results | Low-Medium — qualitative | What does the CSM think about this account? |
| **Renewal signals** | CRM | Renewal date, renewal stage, churn/expansion outcome | High | What is the renewal risk horizon? |
| **Platform breadth** | Entitlement system | Products purchased vs. deployed across Strata/Prisma/Cortex | Medium — deployment lag vs. entitlement | Is the customer on 1 platform or 3? |

### 3.2 BU Owner Pain Points — The Baseline Problems

During stakeholder discovery, I identified three immediate, surface-level pain points
that every GCS BU owner articulates within the first 10 minutes of a conversation.
These formed the initial brief but required deeper deconstruction to reach the
nuanced reality of PANW's business.

---

**Pain Point 1: The Bookings vs. Burn Disconnect**

Sales closes a massive Enterprise License Agreement (ELA) upfront. The business
celebrates the TCV. But if the customer isn't actively consuming compute credits
(Prisma/Cortex) or deploying firewalls (Strata), that revenue is dead on arrival
at renewal.

> **Dashboard Signal: Credit Burn Velocity (CBV)**  
> Actual compute credits consumed over a 30-day trailing window against the idealized
> straight-line burn rate. An account on a $1M annual contract should be consuming
> ~$83K/month at steady state. CBV = actual_monthly_burn / (annual_commit / 12).
> CBV < 0.5 for two consecutive months triggers a deployment risk flag.

*How this maps to the data model:* CBV is computed directly from
`daily_usage_logs.compute_credits_consumed` aggregated monthly and divided by
`contracts.included_monthly_compute_credits`. This is the deployment component of
Realized ARR, surfaced as a standalone velocity signal.

---

**Pain Point 2: The Shelfware Margin Drain**

Accounts with high annual commits but empty usage logs. The BU owner is paying for
infrastructure capacity and CSM overhead for accounts that are getting zero value
and are guaranteed to churn.

> **Dashboard Signal: Provisioned vs. Active Entitlement Ratio**  
> Accounts above the 80% threshold for provisioned licenses but below 10% for daily
> usage logs. These accounts consume CSM time and infrastructure cost while generating
> zero security value and near-certain churn probability.

*How this maps to the data model:* The shelfware hard-floor override in the Realized
ARR formula (PRS = 0.00 when Deployment = 0 AND Sustained Usage = 0) directly
encodes this signal. The Provisioned vs. Active ratio adds nuance: an account can
be "deployed" in name only (licenses provisioned, software installed) while still
shelfwaring operationally (zero active usage logs). Both conditions must be detectable.

---

**Pain Point 3: Support Cost Eclipsing ARR**

High ARR accounts that generate massive, sustained support ticket volumes. The revenue
is high, but the cost to serve makes the account unprofitable.

> **Dashboard Signal: Cost-to-Serve Index (CSI)**  
> Support ticket volume and severity weighted against Annual Recurring Revenue.
> Formula: `CSI = (P1_tickets × 5 + P2_tickets × 2 + P3_tickets × 1) / (ARR / 100K)`
> Accounts with CSI > 10 are flagged as unprofitable — they cost more to support
> than their ARR justifies.

*How this maps to the data model:* The Technical Health Score in Realized ARR captures
health_color as a proxy. CSI is the more granular version — it connects support cost
directly to ARR profitability, which health_color alone cannot express. Recommended
as a secondary dashboard metric alongside the North Star.

---

### 3.3 Nuanced, High-Impact Pain Points — The PANW Reality

Beyond the obvious pain points, four nuanced problems emerged from deeper discovery.
These are the issues that distinguish PANW's measurement challenge from a generic
SaaS analytics problem.

---

**Nuanced Pain Point 1: The Deployment vs. Efficacy Illusion**

A customer deploys Cortex XDR agents across 10,000 endpoints. Usage metrics look
strong. But policies are left in "alert-only" mode. The customer is consuming credits
and generating telemetry — but getting zero actual prevention value. When a breach
occurs, they will blame PANW and churn. High consumption does not equal security health.

> **Dashboard Signal: Protection Mode Enablement %**  
> Ratio of agents actively blocking threats versus passively logging.
> In the synthetic dataset: maps to health_color correlation with
> compute_credits_consumed. High consumption + Red/Yellow health = efficacy illusion flag.

*First principles implication:* This is Truth 2 inverted. Security usage being
spike-driven is expected and benign. Security usage being consistently high but
producing zero prevention outcomes is dangerous and invisible to any consumption
metric alone. The Technical Health Score in the PRS is the only component that
catches this — which is why it carries 20% weight despite being a lagging indicator.

---

**Nuanced Pain Point 2: Silent Churn Misinterpreted as Health**

A customer generates zero support tickets and has flatline credit consumption. A
legacy CSM dashboard flags this account as "Green" because there are no escalations.
The BU owner knows silence is a false positive — the customer's security architect
left, the platform has been abandoned, and no one at the customer is generating
tickets because no one is using the product.

> **Dashboard Signal: Zero-Telemetry Days (ZTD)**  
> Triggers a critical risk alert when an account hits 14+ consecutive days of zero
> `daily_usage_logs` entries despite active contract dates. Silence is not health.
> Silence is a missing security program.

*How this maps to the data model:* The Sustained Usage Score in the Realized ARR
formula catches chronic zero usage over months. ZTD adds a shorter-window,
higher-sensitivity version: 14 days of zero telemetry within an active contract
is an immediate alert regardless of prior-month history. This is the "silent churn"
early warning that no snapshot metric can detect.

---

**Nuanced Pain Point 3: Overage Shock and Bait-and-Switch Resentment**

A customer turns on a massive cloud workload and burns 90% of their annual credits
in Month 1. Sales applauds the usage numbers. The BU owner knows the customer is
about to receive an unexpected overage invoice, feel extorted, and aggressively
downgrade at renewal. The spike looked like success. It was the beginning of churn.

> **Dashboard Signal: Overage Trajectory Alert**  
> Predictive flag for accounts consuming >120% of monthly allocation early in the
> contract lifecycle. Formula: if cumulative_consumption / (months_elapsed × included_monthly)
> > 1.4 before month 6, trigger CSM intervention to renegotiate credits before invoice shock.

*How this maps to the data model:* The Spike & Drop edge case in the pipeline handles
the outcome. The Overage Trajectory Alert is the intervention — it fires during the
spike, before the drop, when CSM action can still change the trajectory. In Realized
ARR, consistent overages are capped at 1.0 for efficiency and flagged separately
for expansion. This alert is the mechanism that converts an overage from a churn
risk into an upsell conversation.

---

**Nuanced Pain Point 4: Cross-Platform Land and Stall**

The entire PANW value proposition is the interconnected security operating system
(Network + Cloud + SecOps). A customer buys a bundled ELA but only ever activates
the firewall credits. Prisma and Cortex remain orphaned. They are not sticky. Any
competitor can rip and replace the unused modules at renewal.

> **Dashboard Signal: Multi-Module Active Ratio**  
> Tracks whether consumption spans across different product lines within the same
> account_id or is isolated to a single silo. Formula: active_product_lines /
> purchased_product_lines. An account with 3 purchased modules and only 1 active
> scores 0.33 — the lowest health multiplier on platform breadth.

*How this maps to the data model:* This is the Platform Breadth component of the
Option 2 PRS framework (25% weight). It is not yet implementable with current data
because cross-platform entitlement data is not unified. Multi-Module Active Ratio
is the simplified proxy — detectable from account_id patterns in usage logs across
product line classifications. Designated as a Phase 2 metric addition.

---

### 3.4 Key Data Quality Findings (Pre-Discovery Audit)

Before any metric design, I ran a systematic data quality audit. These findings
shaped the metric architecture before a single formula component was written.

**Finding 1 — Orphaned usage logs inflate deployment metrics.**  
`daily_usage_logs` contains records where `account_id` does not match any row in
the `accounts` table. These must be excluded upstream. Left unaddressed, they make
shelfware accounts appear to have usage activity.

**Finding 2 — Rogue usage outside contract windows distorts consumption scores.**  
Usage logs exist with dates that fall before contract start or after contract end.
These are data pipeline errors, not real consumption. A metric built on raw data
without this filter would reward phantom activity.

**Finding 3 — Overlapping contracts double-count committed credits.**  
~8 accounts in the dataset have two active contracts with overlapping date ranges
(mid-year expansions). A naive SUM of committed credits double-counts their
commitment. `MAX(annual_commit_dollars)` per account-month is the correct approach.

**Finding 4 — Missing Account Health records should default to Yellow, not Red.**  
Missing health_color records reflect *unchecked* accounts, not *unhealthy* accounts.
Setting the default to 0.60 (Yellow) rather than penalizing at 0.20 (Red) prevents
the metric from punishing data gaps as operational failures.

**Finding 5 — Security spike-and-drop is expected behavior, not a churn signal.**  
Cortex XSIAM consumption spikes naturally during incident response and major
migrations. A metric that treats any spike followed by a drop as a warning signal
would generate constant false alarms on healthy, well-deployed security accounts.

> **See Section 11 for five additional advanced data quality traps discovered during
> pipeline construction, including Cartesian explosions on mid-year expansions,
> late-arriving telemetry, silent schema drift, and POC-to-Prod orphaned tenant
> problems — with a prioritized automated testing roadmap.**

### 3.5 Signal-to-Metric Mapping

```
SIGNALS AVAILABLE                   BUSINESS QUESTION                 COMPONENT
──────────────────                  ─────────────────                 ─────────
Monthly credits consumed      →     Using what they bought?           Deployment (40%)
Days with any usage           →     Consistent or episodic?           Sustained Usage (30%)
health_color records          →     Platform technically stable?      Tech Health (20%)
Consumption MoM trend         →     Growing or declining?             Expansion Momentum (10%)
CBV (burn velocity)           →     On track to exhaust credits?      Commitment Exhaustion Alert
ZTD (zero telemetry days)     →     Silent churn or silent health?    Early Warning Alert
Overage trajectory            →     Heading toward invoice shock?     Overage Alert
Multi-module ratio            →     Land and stall or deepening?      Phase 2: Platform Breadth
Protection mode %             →     Consuming but not protecting?     Phase 2: Efficacy Signal
Orphaned / rogue usage        →     Is our data trustworthy?          DQ Gate (not a metric)
Contract committed ARR        →     Full financial opportunity?        Contracted ARR (base)
```

---

## 4. Phase 2 — First Principles Deconstruction

### 4.1 The Core Question

Before designing any metric, I applied first principles thinking:
**Strip away every SaaS assumption. What are the absolute truths of PANW's business?**

This step is non-negotiable. Importing a standard SaaS framework (NRR, DAU/MAU, NPS)
into a cybersecurity platform company produces metrics that look familiar but measure
the wrong things.

### 4.2 The Five Absolute Truths of PANW's Business

**Truth 1: Security cannot be "Shelfware" without catastrophic risk.**

In standard productivity SaaS, unutilized software is wasted budget. At Palo Alto
Networks, unutilized software represents an *unprotected attack surface*. A customer
that purchased Prisma Cloud modules and never turned them on — but believes they are
protected — is in a worse security posture than before they bought the product. One
breach on an undeployed asset is not a renewal risk. It is brand destruction and
potential litigation.

> **Metric implication:** Deployment is a hard floor. Zero deployment = zero PRS,
> regardless of health or momentum scores. The shelfware override directly encodes this.

**Truth 2: Security usage is inherently spike-and-volume driven — this is not churn.**

Cortex XSIAM and Strata consumption will naturally spike during active incidents,
DDoS attacks, and major migrations, then return to baseline. A simple spike-and-drop
alert would trigger constant false alarms on healthy security accounts. But this
truth has a dangerous inversion: an account with high, consistent consumption but
policies in alert-only mode is the deployment vs. efficacy illusion. Both patterns
look identical in raw consumption data.

> **Metric implication:** Sustained Usage measures architectural coverage over time
> (months with meaningful usage), not peak consumption. The Technical Health Score
> is the only component that can distinguish real security operation from credit
> consumption without prevention value.

**Truth 3: Data ingestion is the engine of security value.**

The more telemetry a customer feeds into the PANW ecosystem, the stronger the
AI/ML threat detection performs. Low ingestion means the customer is paying for
an AI-powered security platform and starving it of the data it needs to work.

> **Metric implication:** Deployment Score carries the highest weight (40%) because
> data pipeline activation is the primary value driver.

**Truth 4: Platform depth multiplies ARR 8×.**

| Customer Profile | Average ARR |
|---|---|
| Top 5,000 customers on **1 platform** | $1.8M |
| Top 5,000 customers on **3 platforms** | $14.3M |
| **Multiplier** | **7.9×** |

The $15B NGS ARR goal cannot be achieved through new logo acquisition alone.

> **Metric implication:** Platform breadth and Expansion Momentum must be explicit
> metric components — not secondary KPIs. The cross-platform "land and stall" pattern
> is a structural churn signal disguised as healthy deployment.

**Truth 5: GCS Analytics is the only team with a cross-functional vantage point.**

Support tickets, PS milestones, CS health signals, and Customer 360 telemetry are
siloed in different systems. No individual GCS team sees all four simultaneously.
Analytics is the only function that can build a unified view at the account level.

> **Metric implication:** The North Star metric must be owned by Analytics — not CS,
> not Support, not PS — because it requires joining data no single operational team
> possesses.

### 4.3 The First Principles Derivation

```
IF customers buy risk reduction (not products)
AND risk reduction requires active platform operation (not just signatures)
AND platform depth multiplies ARR 8×
AND shelfware carries unique security risk (not just revenue risk)
AND high consumption without prevention = deployment vs. efficacy illusion
AND silence (zero tickets, zero telemetry) = silent churn risk
AND Analytics is the only function with a unified data view

THEN the North Star metric must:
  → Measure whether contracted ARR is converting into operational security coverage
  → Hard-floor shelfware to zero (no phantom realized value)
  → Reward sustained, consistent usage over spike-and-drop behavior
  → Detect silent churn via zero-telemetry signals, not just ticket volume
  → Capture platform breadth as an explicit multiplier, not a footnote
  → Be calculated by Analytics from a joined, clean, DQ-gated data view

THEREFORE: Realized ARR = Contracted ARR × Platform Realization Score (PRS)
```

This is not a formula I started with. It is the formula that first principles
reasoning produced.

---

## 5. Phase 3 — System Thinking Framework

### 5.1 The GCS Operating System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THE GCS ACCOUNT LIFECYCLE                        │
│                                                                     │
│  SIGNALS                PROCESSING              OUTPUT              │
│  ─────────              ──────────              ──────              │
│                                                                     │
│  Customer Support ──→  Technical Health   ─→   PRS Score           │
│  Platform             Score (THS) 20%           ↓                  │
│  P1/P2 tickets        + Cost-to-Serve Index  Realized ARR           │
│  MTTR trend           (secondary)               ↓                  │
│                                             Health Band             │
│  Account Health ────→  Tech Health + ZTD  ─→  (Green/Yellow/       │
│  health_color          Early Warning Alert      Orange/Red)         │
│                                                     ↓              │
│  Daily Usage ───────→  Deployment Score   ─→   CSM Action          │
│  Logs (clean)          (D) 40%                 Triggered            │
│  credits consumed      + CBV Velocity               ↓              │
│                         + Overage Trajectory    Rep Comp            │
│                                                 Milestone           │
│  Contract Data ─────→  Contracted ARR     ─→   Exec QBR            │
│  Entitlements          (base)                  Dashboard            │
│                                                     ↓              │
│  PS Milestones ─────→  Expansion          ─→   Upsell Signal       │
│  Customer 360          Momentum (M) 10%             ↓              │
│                        + Multi-Module Ratio     Renewal Alert       │
│                        + TTFV Decay Factor      90d before end      │
│                                                                     │
│  DQ Gate ───────────→  Orphaned/Rogue     ─→   dq_report           │
│  (runs first)          Cartesian blast         Engineering alert    │
│                        Schema drift             (not a metric)      │
│                        Late telemetry                               │
│                                                                     │
│                    ┌──── FEEDBACK LOOP ─────┐                      │
│                    │  CSM acts on Red/Orange  │                     │
│                    │  accounts → deployment   │                     │
│                    │  improves → PRS rises →  │                     │
│                    │  Realized ARR grows →    │                     │
│                    │  comp milestone released │                     │
│                    └──────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 The Three System Design Principles

**Design Principle 1: Every component must answer a distinct business question.**

| Component | Business Question | Weight | What Removing It Would Hide |
|---|---|---|---|
| Deployment Score | Is the customer using what they purchased? | 40% | Shelfware and data pipeline failures |
| Sustained Usage Score | Is usage consistent or episodic? | 30% | Spike-and-drop accounts and silent churn |
| Technical Health Score | Is the platform technically stable? | 20% | Deployment vs. efficacy illusion |
| Expansion Momentum | Is this account growing? | 10% | Upsell signals and land-and-stall risk |

**Design Principle 2: The metric must encode business consequences, not just behavior.**

Standard metrics measure activity (logins, sessions, feature usage). The PRS measures
*consequence* — whether the platform is delivering security value. An account can log
in daily and still be shelfwaring. Consumption and health signals cut through surface
activity to measure real operational security coverage.

**Design Principle 3: Build data quality in as infrastructure, not as cleanup.**

All downstream metric computation uses `clean_usage_logs`, never raw tables. This is
the same discipline applied to the Product Feedback Program at Microsoft FastTrack —
3,179 feedback submissions required PII masking and taxonomy validation before entering
the product prioritization workflow. Bad input produces bad metric regardless of formula
quality. The five advanced DQ traps in Section 11 extend this principle.

---

## 6. Metric Options Evaluated

### 6.1 Full Brainstorm — All Options Considered

| # | Option | Formula / Signal | Pros | Cons | PANW Fit |
|---|---|---|---|---|---|
| **1** | **Net Revenue Retention (NRR)** | (Beginning ARR + Expansion − Churn) / Beginning ARR | Investor-facing, benchmarkable | 12-month lag, no early warning | ❌ Too lagging |
| **2** | **Customer Health Score** | Weighted composite of usage, support, NPS | Flexible | No ARR tie-in, CSM can inflate | ❌ Too qualitative for comp |
| **3** | **Credit Burn Velocity (CBV)** | Actual burn / straight-line burn rate | Direct deployment proxy, fast signal | Single dimension, no health component | ⚠️ Strong secondary metric |
| **4** | **Provisioned vs. Active Entitlement Ratio** | Provisioned licenses / actively used licenses | Catches provisioned-not-deployed | Not tied to ARR | ⚠️ Supporting diagnostic |
| **5** | **Cost-to-Serve Index (CSI)** | Weighted ticket volume / (ARR / 100K) | Surfaces unprofitable accounts | Requires support cost data not always clean | ⚠️ Secondary metric |
| **6** | **eARR (Earned ARR) — Option 1** | cARR × Deployment% × PHI | Direct ARR tie-in, PANW-specific | PHI definition ambiguous, no sustained usage | ⚠️ Strong but incomplete |
| **7** | **PRS (Option 2) — Platformization** | Coverage Depth (35%) + Platform Breadth (25%) + Security Outcome (25%) + Momentum (15%) | Most complete, captures 8× multiplier | Needs cross-platform entitlement data not yet clean | ⚠️ Phase 2 target |
| **8** | **eARR Velocity (Time-to-Earned-ARR)** | Days from sign to 90% eARR efficiency | Aligns all GCS functions, measurable | Single-point measure, ignores post-deployment health | ⚠️ Excellent secondary KPI |
| **9** | **Zero-Telemetry Days (ZTD)** | Consecutive days with zero usage logs | Catches silent churn | Not a composite metric, needs to be part of a score | ⚠️ Early warning signal only |
| **10** | **Value Realization Index (VRI)** | Reward consistent burn + penalize zero-days + penalize >150% spike | Directly maps to BU pain points | Complex to weight, similar to PRS but less defensible | ⚠️ Conceptually valid, superseded by Realized ARR |
| **11** | **Realized ARR (Final Choice)** | Contracted ARR × PRS (D 40% + SUS 30% + THS 20% + EM 10%) | All-in-one, ARR-tied, shelfware hard-floor, expansion signal | Platform breadth deferred to Phase 2 | ✅ **Selected as North Star** |

### 6.2 Five Additional Signals Discovered — Extended Signal Library

These five metrics emerged during the nuanced discovery phase. Each captures a
specific PANW risk pattern that the composite PRS score cannot fully surface alone.
They are recommended as supplementary dashboard signals alongside the North Star.

---

**Signal 1: Time-to-First-Value (TTFV) Decay Factor**

*The pain:* Sales books the deal, but deployment stalls in the customer's
change-control process. The longer the delay, the higher the churn probability.
A customer who gets to first value in 15 days has a fundamentally different
success trajectory than one who takes 90 days.

> **Formula:** Delta in days between `contracts.start_date` and the first
> `daily_usage_logs` row where `compute_credits_consumed > 0`.
> If TTFV > 45 days, apply a health penalty to that account's PRS in the current
> calculation month: multiply PRS by 0.90 to reflect the deployment risk.

*Data model impact:* Requires a MIN(date) lookup on `daily_usage_logs` per
`account_id`, joined to the `contracts.start_date`. Clean data is critical —
a POC-to-Prod orphaned tenant (see Section 11) will create a false TTFV by
attributing the first real production log to the wrong tenant, making a
fast-deploying customer appear to have stalled.

---

**Signal 2: Consumption Volatility Index (CVI)**

*The pain:* Spiky consumption is not success — it is chaos. High variance usually
means the customer is using the platform purely for reactive incident response
rather than steady-state, proactive security operations. It also catches automated
script errors that spin up phantom workloads.

> **Formula:** Standard deviation of a 30-day rolling window of
> `compute_credits_consumed` per `account_id`.
> CVI > 2.5 standard deviations above the account's own 90-day baseline triggers
> a spike-and-drop investigation flag — distinguishing genuine incident response
> from runaway automation errors.

*Why this matters beyond the PRS:* The Sustained Usage Score in PRS measures
month-level consistency. CVI measures day-level volatility. An account can
pass the Sustained Usage test (usage in 10 of 12 months) while still showing
extremely erratic daily patterns that signal operational immaturity.

---

**Signal 3: Expansion Cannibalization Rate**

*The pain:* Sales claims a massive mid-year upsell. The telemetry shows completely
flat usage after the new contract activates. The customer shifted existing workloads
to a new contract SKU rather than genuinely expanding their security footprint.
The expansion is phantom revenue.

> **Formula:** When overlapping active contract dates occur, track the gradient
> of the `daily_usage_logs` curve before and after `contract_B.start_date`.
> If the 30-day post-activation baseline does not show a statistically meaningful
> lift versus the 30-day pre-activation baseline, flag the expansion as
> "Ghost Revenue" — cannibalization rather than true expansion.

*Data model impact:* This requires the mid-year expansion edge case to be handled
correctly upstream (no Cartesian join doubling — see Section 11). If the SQL JOIN
on overlapping contracts duplicates usage rows, every mid-year expansion will
show a false 2× usage lift, making all expansions look genuine.

---

**Signal 4: Orphaned Telemetry Ratio**

*The pain:* Customers are actively consuming resources, but broken API keys,
botched tenant migrations, or pipeline failures mean usage isn't tied to a
billable account_id. The business is providing compute value without capturing
the corresponding revenue attribution.

> **Formula:** `orphaned_volume / total_volume` where orphaned rows are those
> failing a LEFT JOIN to an active `contracts` row.
> Target: Orphaned Telemetry Ratio < 0.5%. Anything above 1% is a revenue
> attribution failure requiring engineering escalation.

*Data model impact:* The DQ-001 and DQ-002 rules in the pipeline exclude orphaned
logs from metric calculations. This signal does not affect PRS scores — it is a
separate alert to engineering and Finance that billable consumption is escaping
attribution. It does not belong in the health score; it belongs on a data operations
dashboard as a pipeline integrity metric.

---

**Signal 5: Commitment Exhaustion Trajectory**

*The pain:* Discovering a customer burned 100% of their annual commitment by Month 8.
The account goes dark because they refuse to pay overages, and the CSM finds out 60
days too late — after the customer has already made the internal decision not to renew.

> **Formula:** A rolling linear regression on daily `compute_credits_consumed`
> per `account_id`, forecasting the date when cumulative consumption will hit
> `contracts.annual_commit_dollars × 1.0`.
> Trigger an alert when the projected exhaustion date falls more than 30 days
> before `contracts.end_date`.
>
> **Implementation (BigQuery):**
> ```sql
> WITH daily_cumulative AS (
>   SELECT account_id, date,
>     SUM(compute_credits_consumed)
>       OVER (PARTITION BY account_id ORDER BY date) AS cumulative_consumed
>   FROM clean_usage_logs
> ),
> regression AS (
>   SELECT account_id,
>     REGR_SLOPE(cumulative_consumed, DATE_DIFF(date, MIN(date) OVER
>       (PARTITION BY account_id), DAY)) AS daily_burn_rate
>   FROM daily_cumulative
>   GROUP BY account_id
> )
> SELECT r.account_id,
>   DATE_ADD(CURRENT_DATE(),
>     INTERVAL CAST((c.annual_commit_dollars - last_cumulative)
>     / r.daily_burn_rate AS INT64) DAY) AS projected_exhaustion_date
> FROM regression r JOIN contracts c USING (account_id)
> WHERE projected_exhaustion_date < DATE_SUB(c.end_date, INTERVAL 30 DAY);
> ```

---

### 6.3 Why Each Major Option Was Eliminated or Deferred

**NRR:** 12-month lagging measure. By the time NRR deteriorates, the churn decision
is already made. Retained as a downstream success metric that Realized ARR should predict.

**Customer Health Score:** No ARR tie-in, CSM inflation risk, NPS bias. Deferred as
supporting context only.

**eARR Option 1:** Directionally correct. Two gaps: PHI is ambiguous across 3 platforms;
no sustained usage component misses spike-and-drop patterns. Realized ARR is eARR with
these gaps closed.

**PRS Option 2:** The right long-term architecture. Requires clean cross-platform
entitlement data not yet available. Designated as Phase 2 evolution.

**eARR Velocity:** Excellent secondary KPI. Single-point measure — cannot track ongoing
health after deployment.

---

## 7. PANW-Specific: TCV vs. New Metric Analysis

### 7.1 The Illustrative Scenario: A $3M Global Banking Deal

**The deal:** A 3-year, $3M TCV Next-Gen SASE and SecOps deal with a Global 2000 bank.
Annual commit: $1M ($600K Prisma SASE seats + $400K Cortex XSIAM credits).

**Month 6 reality:** SASE seats are 100% deployed. Cortex XSIAM is 10% deployed —
the bank's security operations team is struggling to configure data pipelines.
Configuration errors are causing high API latency. Technical health is Yellow.

### 7.2 The Contrast Ledger: TCV vs. Realized ARR

| Dimension | Traditional TCV / Bookings | Realized ARR Model |
|---|---|---|
| **Day 1 executive view** | $3M TCV booked. Massive enterprise win. Sales has moved on. | $0 Realized ARR. Deployment clock starts. TTFV timer running. |
| **Month 6 view** | $3M TCV still shows as a win. Account appears healthy in QBR. | Realized ARR = $335K against $1M contracted. $665K Unearned Revenue Gap visible. |
| **The blind spot** | Completely invisible: 90% of Cortex XSIAM undeployed. Customer believes they are protected. They are not. | No blind spot: gap is surfaced. Cortex XSIAM onboarding friction is the named bottleneck. |
| **Silent churn risk** | Not detectable until the customer calls to cancel. | ZTD alert fires if Cortex log pipelines go dark for 14 days. CSM receives auto-notification. |
| **Overage risk** | Not visible until the invoice generates. | CBV tracking shows Prisma consumption is on pace. Cortex is far below pace. Neither overage nor shelfware — partial deployment pattern. |
| **Security risk** | High. The customer is paying for AI threat detection running on 10% of their log data. | Mitigated. Engineering resources dispatched to clear the XSIAM pipeline. |
| **GCS alignment** | Siloed. Support tickets. CS check-ins. PS billing hours independently. | Unified: CS, PS, and Support focused on one goal — recover the $665K gap by getting Cortex pipelines live. |
| **Sales behavior** | Rep signed deal, handed off, moved to next logo. | Rep's 35% commission milestone tied to 80% Realized ARR efficiency in 180 days. Rep unblocks the customer's CISO relationship. |
| **Renewal signal** | Visible 90 days before renewal. 3 months of warning. | Visible from Month 1. 11 months of warning if the account stays below 0.60 PRS. |

### 7.3 The Realized ARR Calculation for This Account

```
Contracted ARR = $1,000,000

Deployment Score:
  Prisma SASE: 100% deployed ($600K value realized)
  Cortex XSIAM: 10% deployed ($40K value realized)
  Blended: MIN(1.0, $40K / $400K Cortex commitment) = 0.10
  (Cortex is the binding constraint — the weakest link in the formula)

Sustained Usage Score:
  SASE: 6 healthy months / 6 month window = 1.0 (fully healthy)
  Cortex: 1 healthy month / 6 month window = 0.17 (barely used)
  Blended (ARR-weighted): 0.55

Technical Health Score:
  Yellow health = 0.60

Expansion Momentum:
  < 3 months threshold not yet met on Cortex = 0.10

PRS = (0.10 × 0.40) + (0.55 × 0.30) + (0.60 × 0.20) + (0.10 × 0.10)
    = 0.040 + 0.165 + 0.120 + 0.010
    = 0.335

Realized ARR = $1,000,000 × 0.335 = $335,000
Realization Gap = $665,000

Health Band: Red (PRS 0.335 < 0.30 threshold)
Flags: No shelfware (SASE is deployed), no spike_drop, no overage
Recommended CSM action: Emergency Cortex XSIAM deployment sprint
```

### 7.4 Portfolio Implications at PANW Scale

| Metric | Value |
|---|---|
| PANW NGS ARR committed (Q3 FY26) | $8.1B |
| Estimated average realization rate at current baseline | ~82% |
| Unrealized ARR | ~$1.46B |
| 1-point PRS improvement across portfolio | ~$81M additional realized ARR |
| Path to 90% realization | ~$654M incremental realized ARR |

---

## 8. North Star Selection: Why Realized ARR Wins

### 8.1 The Decision Matrix

| Criterion | NRR | Health Score | eARR | PRS Opt.2 | Realized ARR |
|---|---|---|---|---|---|
| Directly tied to ARR | ✅ | ❌ | ✅ | ⚠️ | ✅ |
| Surfaces shelfware | ❌ | ⚠️ | ✅ | ✅ | ✅ (hard floor) |
| Leading indicator | ❌ | ✅ | ✅ | ✅ | ✅ |
| Catches spike-and-drop | ❌ | ⚠️ | ❌ | ✅ | ✅ |
| Detects silent churn | ❌ | ❌ | ❌ | ⚠️ | ✅ (ZTD + SUS) |
| Catches deployment vs. efficacy illusion | ❌ | ❌ | ❌ | ✅ | ✅ (THS) |
| Detects overage shock trajectory | ❌ | ❌ | ⚠️ | ⚠️ | ✅ (CBV alert) |
| Implementable with current data | ✅ | ✅ | ✅ | ❌ | ✅ |
| Suitable for rep compensation | ❌ | ❌ | ✅ | ❌ | ✅ |
| Drives cross-functional alignment | ❌ | ⚠️ | ✅ | ✅ | ✅ |

### 8.2 The Three Reasons Realized ARR Was Selected

**Reason 1:** It is the only metric that answers all three executive questions simultaneously
(*what is the health at a point in time, what is purchased vs. consumed, what does good
look like*) in a single number tied directly to ARR.

**Reason 2:** The shelfware hard-floor is non-negotiable for a security company.
Every other framework allows a shelfware account to score above zero. Realized ARR
with the override hard-floors true shelfware to $0 Realized ARR. This is the only
mathematically correct answer for a platform where undeployed software means
unprotected attack surface.

**Reason 3:** It is implementable today on the data infrastructure that exists.
The PRS Option 2 framework is the right long-term answer but requires cross-platform
entitlement data not yet reliable. A metric that leadership trusts and acts on is
worth more than a comprehensive metric that leadership questions.

---

## 9. Final Metric Specification Summary

### 9.1 The Formula

```
Realized ARR = Contracted ARR × PRS

PRS (Platform Realization Score) =
    (Deployment Score       × 0.40)
  + (Sustained Usage Score  × 0.30)
  + (Technical Health Score × 0.20)
  + (Expansion Momentum     × 0.10)

OVERRIDE: IF Deployment Score = 0 AND Sustained Usage Score = 0
          THEN PRS = 0.00
          (shelfware hard floor — no phantom realized value)
```

### 9.2 Component Design Rationale

| Component | Weight | Key Design Decision |
|---|---|---|
| **Deployment Score** | 40% | `MIN(1.0, consumed/committed)` — capped at 1.0 so overages don't inflate beyond contracted value. Overages flagged separately for expansion signal. |
| **Sustained Usage Score** | 30% | Trailing 12-month window (capped) — prevents old bad quarters from permanently dragging healthy accounts. 30% threshold for "healthy month" allows for legitimate low-usage periods without false shelfware classification. |
| **Technical Health Score** | 20% | Missing records default to 0.60 (Yellow), not penalized at 0.20 (Red). Deployment vs. efficacy illusion is detected here — high consumption + Red health = efficacy concern. |
| **Expansion Momentum** | 10% | New account guard: accounts with < 3 months of contract history default to 0.10. Prevents Month 1 and Month 2 accounts from permanent ELSE clause assignment. |

### 9.3 Health Bands and CSM Actions

| PRS Range | Band | Color | Triggered Actions |
|---|---|---|---|
| 0.80 – 1.00 | Healthy | 🟢 Green | QBR maintenance, expansion play, upsell conversation |
| 0.60 – 0.79 | Watch | 🟡 Yellow | Proactive outreach, identify friction, check CBV |
| 0.30 – 0.59 | At-Risk | 🟠 Orange | Immediate CSM intervention, PS deployment support |
| 0.00 – 0.29 | Critical | 🔴 Red | Executive escalation, emergency deployment sprint, TTFV review |

### 9.4 Compensation Model Recommendation

- **40% Base Commission:** On contract execution based on committed cARR.
- **35% eARR Milestone Release:** Account reaching 80% Realized ARR efficiency
  within first 180 days post-signature.
- **25% Expansion Revenue:** Overage conversion to new committed ARR — when the
  customer upsells based on demonstrated value. Expansion Cannibalization Rate
  (Signal 3 above) is the control that prevents ghost revenue from triggering
  unearned commission.

---

## 10. AI-Assisted Early Warning Layer & Signal Library

### 10.1 The Gap That the Formula Cannot See

Realized ARR quantifies *what is happening*. It cannot explain *why* or predict
*what will happen next*. The formula tells you an account is at PRS 0.34. It does
not tell you whether the risk is a configuration issue (fixable in 2 weeks), an
internal politics problem (requires executive sponsorship), or a product gap
(requires engineering involvement). This is where AI adds a layer of intelligence
that structured metrics alone cannot provide.

### 10.2 LLM-Powered Account Narratives

Building on the Iridias architecture from Microsoft Azure CXP (Copilot-powered
LLM outage summarization that recovered 4,000+ engineering hours annually), the
AI layer generates account-level narratives from structured signals:

```
INPUT SIGNALS:
  Account: {company_name} | Industry: {industry} | Tier: {tier}
  Realized ARR: ${realized_arr} | PRS: {prs} | Band: {health_band}
  Deployment Score: {D} | Sustained Usage: {SUS}
  Technical Health: {THS} | Expansion Momentum: {EM}
  CBV Velocity: {cbv} | ZTD last 30 days: {ztd_days}
  TTFV at contract start: {ttfv_days}
  Flags: shelfware={bool}, spike_drop={bool}, overage={bool}

OUTPUT FORMAT:
  RISK SUMMARY: [2 sentences on what is happening and why]
  RECOMMENDED ACTION: [1 specific CSM action this week, time-bound]
  RENEWAL IMPACT: [1 sentence on renewal risk if no action taken]
```

The AI does not replace the metric. It translates the metric into a human action.
A CSM reading a PRS of 0.34 may not know what to do. A CSM reading "Cortex XSIAM
log pipelines have been inactive for 23 days despite full Prisma SASE deployment.
Recommend escalating to PS this week for an emergency pipeline configuration
session before the renewal window opens in 34 days" knows exactly what to do.

### 10.3 Portfolio-Level Pattern Detection

| Signal Pattern | Early Warning Inference | GCS Action |
|---|---|---|
| 3+ accounts in same industry show declining Deployment Score this month | Possible product configuration issue specific to that industry's environment | Alert product engineering, deploy industry-specific PS support |
| CVI > 2.5 SD above baseline with no open P1/P2 tickets | Likely automated script errors spinning phantom workloads, not real consumption | Engineering investigation before false overage invoice generated |
| TTFV > 45 days across 20%+ of new accounts in a region | Onboarding process failure — systemic change-control barrier in that market | Regional PS capacity review, possible onboarding playbook update |
| Accounts with expansion flags showing flat CBV post-contract-B | Expansion Cannibalization — ghost revenue alert | Finance notification, CSM executive conversation to unblock genuine expansion |
| ZTD > 14 days on accounts with CSM last-touch > 21 days | Silent churn in progress — account abandoned, no one noticing | Automated CSM escalation with account narrative generated |
| Commitment Exhaustion Trajectory projects exhaustion > 30 days before contract end | Customer will go dark before renewal — invoice shock imminent | Immediate credit renegotiation conversation, expansion offer |

---

## 11. Data Quality Trap Analysis & Prioritized Test Roadmap

### 11.1 Five Advanced Data Quality Traps

During pipeline construction, five structural data quality problems emerged that
go significantly beyond the basic orphaned-log and rogue-usage issues identified
in the initial audit. Each represents a failure mode that corrupts the metric
in ways that are invisible to standard row-count checks.

---

**Trap 1: Cartesian Explosions on Mid-Year Expansions**

*The problem:* When an account upgrades mid-year, order management systems rarely
cleanly terminate Contract A before initiating Contract B. Both contracts have
overlapping active dates. If the SQL JOIN evaluates:
```sql
WHERE usage_date BETWEEN contract.start_date AND contract.end_date
```
a single 100-credit usage log duplicates across both active contracts in BigQuery,
artificially doubling `compute_credits_consumed` and completely invalidating
every consumption metric for the account.

*Why it is particularly dangerous:* It creates a false positive. The account appears
to be an enthusiastic high-consumer. Every growth metric flags it as healthy.
In reality, it is a JOIN fan-out — the account may be using 100 credits while the
metric reports 200.

*Prevention:* Deduplicate by selecting MAX(annual_commit_dollars) per account-month
and using the active contract at point in time, not all active contracts. Add a
Cartesian explosion test: assert that for any account-month, the total attributed
credits consumed does not exceed 1.5× the raw sum of `daily_usage_logs` for that period.

---

**Trap 2: Late-Arriving Telemetry and Idempotency Failures**

*The problem:* Global network appliances and disconnected endpoints do not stream
logs in real time. A firewall offline for 72 hours will batch-upload logs with older
timestamps after reconnection. If the incremental pipeline runs strictly on:
```sql
WHERE date = CURRENT_DATE() - 1
```
the delayed payload is dropped. Without robust idempotent windowing:
```sql
QUALIFY ROW_NUMBER() OVER (PARTITION BY log_id ORDER BY ingestion_timestamp DESC) = 1
```
late data is either missed entirely or — worse — creates duplicate records when the
pipeline re-runs. This directly triggers false Zero-Telemetry Day alerts: a CSM
receives an urgent notification that an Enterprise account has gone dark, when the
account is fully operational and the pipeline simply missed a batch.

*Why it is particularly dangerous:* It erodes CSM trust in the dashboard. After two
or three false ZTD alerts on healthy accounts, CSMs stop acting on any alerts —
including genuine ones.

*Prevention:* Use event-time processing with a 72-hour late-arrival window. Implement
log_id-based deduplication. Add a pipeline test that verifies no `log_id` appears
more than once per `account_id` per `date` in the clean table.

---

**Trap 3: Silent Schema Drift in Upstream Telemetry**

*The problem:* Upstream product engineering teams update microservices and alter
JSON telemetry payloads without notifying data engineering. For example, a field
changes from `compute_units: INT` to `compute_credits: FLOAT`. BigQuery's
`JSON_EXTRACT_SCALAR` does not throw a fatal error — it silently evaluates to NULL.
The dashboard suddenly shows an Enterprise account dropping to zero usage for the
affected days. The BU owner assumes churn risk. The CSM schedules an emergency call.
The reality: a pipeline extraction failure with no error log, no alert, no indication
anything changed.

*Why it is particularly dangerous:* The failure is invisible. No pipeline errors.
No BigQuery exceptions. Just accounts that appear to shelfware overnight, and no
one knows why until someone manually investigates.

*Prevention:* Implement schema validation tests that run before ingestion:
```sql
-- Assert that the percentage of NULL compute_credits_consumed is not increasing
SELECT
  DATE_TRUNC(ingestion_date, WEEK) AS week,
  COUNTIF(compute_credits_consumed IS NULL) / COUNT(*) AS null_rate
FROM daily_usage_logs_raw
GROUP BY 1
ORDER BY 1 DESC;
```
Alert if null_rate for any week exceeds 2× the trailing 4-week average.
This catches schema drift within 24 hours rather than after a CSM escalation.

---

**Trap 4: POC-to-Prod Orphaned Tenant Problem**

*The problem:* Sales engineers spin up a Proof of Concept environment to close a deal.
Once the deal closes, a `contract_id` is generated and mapped to the official production
`account_id`. However, the customer's technical team continues building in the POC
tenant rather than migrating to the production tenant.

Real, heavy compute consumption occurs in the POC tenant. The `account_id` emitting
the `daily_usage_logs` is the POC tenant ID — which is not linked to the finalized
`account_id` in the `contracts` table. Result: massive volumes of "orphaned" usage rows,
while the official paid contract appears to be 100% shelfware. The BU owner escalates
a churn risk. The CS team schedules emergency calls. The account is actually healthy —
it is consuming at full rate in the wrong tenant.

*Why it is particularly dangerous:* It inverts the signal. A healthy, highly-engaged
customer looks like the highest churn risk in the portfolio.

*Prevention:* Maintain a `tenant_alias_map` table that links known POC tenant IDs
to their parent production `account_id`. Run a DQ test:
```sql
-- Flag accounts where contracted ARR > $50K but zero usage in production tenant
-- AND non-zero usage in any aliased tenant for same account
SELECT c.account_id, SUM(dul.compute_credits_consumed) AS poc_usage
FROM contracts c
JOIN tenant_alias_map tam ON tam.production_account_id = c.account_id
JOIN daily_usage_logs dul ON dul.account_id = tam.poc_tenant_id
WHERE c.annual_commit_dollars > 50000
GROUP BY c.account_id
HAVING poc_usage > 0;
```

---

**Trap 5: Cross-BU Identity Resolution (Acquisition Silo Trap)**

*The problem:* PANW grew through major acquisitions (Evident.io, RedLock, Demisto,
Expanse). Each acquired product tracks accounts differently:
- Strata: hardware serial numbers
- Prisma Cloud: AWS/GCP tenant IDs  
- Cortex: endpoint domain names

When aggregating `daily_usage_logs` to a single CRM `account_id`, the mapping logic
is brittle. A highly active Prisma Cloud customer appears to have zero Cortex adoption
simply because the Master Data Management (MDM) table is stale or the Cortex tenant
was registered under a subsidiary domain.

*Why it is particularly dangerous:* It undermines the Multi-Module Active Ratio
signal entirely. Every cross-platform analysis — the Platform Breadth component of
Option 2 PRS, the land-and-stall detection, the 8× ARR multiplier analysis — depends
on reliable account identity resolution across three acquisition lineages.

*Prevention:* This is primarily an MDM/data governance problem, not a pipeline
problem. The pipeline can only detect the symptom: flag any account where usage
exists in exactly one product line despite contracts spanning all three. Cross-reference
against the known acquisition tenant-mapping tables.

---

### 11.2 Prioritized Automated Test Roadmap

**The question from discovery:** *Which of these data quality traps should we
prioritize writing the automated BigQuery SQL testing logic for first?*

**Answer: Priority order based on two criteria — (1) how severely it corrupts the
North Star metric, and (2) how detectable it is without custom infrastructure.**

| Priority | Trap | Why First | Test Type | Estimated Build Time |
|---|---|---|---|---|
| **P1 — Build this week** | **Cartesian Explosions (Trap 1)** | Directly doubles consumption metrics on 8+ known expansion accounts. Corrupts the deployment score, which carries 40% weight. Every mid-year expansion account produces wrong PRS today. | SQL assertion: `COUNT(usage_rows_attributed) / COUNT(raw_usage_rows) < 1.1 per account-month` | 2–3 hours |
| **P2 — Build this week** | **Late-Arriving Telemetry (Trap 2)** | Generates false ZTD alerts that erode CSM trust. Once trust in the alert system is broken, genuine alerts are ignored. Idempotency is also a correctness requirement, not just a quality requirement. | SQL dedup test: `ASSERT COUNT(DISTINCT log_id) = COUNT(*) in clean_usage_logs` + null-rate trend check | 2–3 hours |
| **P3 — Build next sprint** | **POC-to-Prod Orphaned Tenant (Trap 4)** | Inverts the signal for healthy accounts — makes them look like the highest churn risk. Prioritized over schema drift because it creates wrong CSM actions, not just wrong metrics. Requires `tenant_alias_map` table to exist first. | SQL join test on alias table once MDM provides the mapping | 4–6 hours (dependent on MDM) |
| **P4 — Build next sprint** | **Silent Schema Drift (Trap 3)** | The most insidious trap but the detection test is simple once written. The null_rate trend check is a 30-line SQL that catches it within 24 hours. Prioritized after Cartesian because it is easier to detect when it fires. | Weekly null_rate trend assertion with 2× baseline alert threshold | 1–2 hours |
| **P5 — Phase 2 roadmap** | **Cross-BU Identity Resolution (Trap 5)** | Requires MDM investment outside the pipeline team's control. The test logic is straightforward but the fix requires organizational coordination across three product engineering teams and a data governance initiative. Flag for leadership alignment — this is a data strategy problem, not a SQL problem. | Flag accounts with single-platform usage despite multi-platform contracts | 2 hours for detection; months for resolution |

### 11.3 Test Implementation Templates

**P1 — Cartesian Explosion Test:**
```sql
-- Assert: no account-month has attributed usage > 105% of raw usage
WITH raw_usage AS (
  SELECT account_id,
    DATE_TRUNC(date, MONTH) AS month,
    SUM(compute_credits_consumed) AS raw_total
  FROM daily_usage_logs
  WHERE NOT STARTS_WITH(account_id, 'GHOST_')
  GROUP BY 1, 2
),
attributed_usage AS (
  SELECT account_id, calculation_month,
    actual_credits_consumed
  FROM account_health_index
)
SELECT r.account_id, r.month,
  r.raw_total,
  a.actual_credits_consumed,
  ROUND(a.actual_credits_consumed / NULLIF(r.raw_total, 0), 4) AS attribution_ratio
FROM raw_usage r
JOIN attributed_usage a
  ON a.account_id = r.account_id AND a.calculation_month = r.month
WHERE a.actual_credits_consumed > r.raw_total * 1.05;
-- Expected result: zero rows
```

**P2 — Idempotency Test:**
```sql
-- Assert: no log_id appears more than once in clean_usage_logs
SELECT log_id, COUNT(*) AS appearances
FROM daily_usage_logs
WHERE NOT STARTS_WITH(account_id, 'GHOST_')
GROUP BY log_id
HAVING appearances > 1;
-- Expected result: zero rows
```

**P3 — Schema Drift Detection:**
```sql
-- Monitor null rate trend week-over-week
-- Alert if current week null rate > 2x trailing 4-week average
WITH weekly_null_rate AS (
  SELECT DATE_TRUNC(date, WEEK) AS week,
    COUNTIF(compute_credits_consumed IS NULL) / COUNT(*) AS null_rate
  FROM daily_usage_logs
  GROUP BY 1
),
trailing_avg AS (
  SELECT week,
    null_rate,
    AVG(null_rate) OVER (
      ORDER BY week
      ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
    ) AS trailing_4wk_avg
  FROM weekly_null_rate
)
SELECT week, null_rate, trailing_4wk_avg,
  ROUND(null_rate / NULLIF(trailing_4wk_avg, 0), 2) AS ratio_vs_baseline
FROM trailing_avg
WHERE week = DATE_TRUNC(CURRENT_DATE(), WEEK)
  AND null_rate > trailing_4wk_avg * 2.0;
-- Expected result: zero rows; any row = schema drift alert
```

---

## 12. Implementation & Governance

### 12.1 Data Pipeline Architecture

```
Source Systems            DQ Gate (run first)           Outputs
──────────────            ────────────────────          ───────
Contracts DB    ──────→  P1: Cartesian blast test  ─→  account_health_index
Daily_Usage_Logs ─────→  P2: Idempotency test          (PRS + Realized ARR)
Account_Health   ─────→  P3: POC tenant alias           
CSM_rep         ──────→  P4: Schema drift test     ─→  csm_rep_summary
                         P5: Identity resolution        (avg PRS + ARR)
                         DQ-001: Orphan filter      ─→  dq_report
                         DQ-002: Rogue usage filter      (flagged records)
                                  ↓                       
                         Component CTEs             ─→  Supplementary signals:
                         D, SUS, THS, EM                 CBV, ZTD, CVI, TTFV,
                                  ↓                       Commitment Exhaustion,
                         Shelfware override              Orphaned Telemetry Ratio
                                  ↓
                         AI narrative layer         ─→  Executive dashboard
                         (LLM per Red/Orange            (3 views: portfolio,
                         account, weekly)               by rep, drill-down)
```

### 12.2 Phase Roadmap

| Phase | Timeline | Deliverable | Success Criteria |
|---|---|---|---|
| **Phase 1** | Weeks 1–6 | Realized ARR pipeline live, Looker Studio + React dashboard, P1–P4 DQ tests passing | Leadership reviews Realized ARR in first GCS QBR |
| **Phase 2** | Months 2–4 | Validated against historical renewal outcomes; TTFV and ZTD alerts in production | PRS ≥ 0.80 predicts renewal at ≥85% accuracy |
| **Phase 3** | Months 4–8 | PRS Option 2 with platform breadth; POC-to-Prod tenant mapping; Cross-BU identity resolution initiative launched | Multi-module ratio trackable per account |
| **Phase 4** | Months 6–12 | AI narrative layer in production; compensation model live; Commitment Exhaustion Trajectory alert operational | CSM intervention rate increases; Red account recovery improves MoM |
| **Phase 5** | Year 2 | Streaming pipeline for ZTD and CVI real-time alerts; eARR Velocity as secondary KPI | Time-to-90%-eARR measured and tracked by segment |

---

## Appendix A: Retrospective — What I Would Do Differently

**1. Start with PRS (Option 2) and clean the cross-platform data in parallel.**  
Rather than sequencing — build Realized ARR now, upgrade to PRS Option 2 later — I
would invest the first 6 weeks cleaning cross-platform entitlement data simultaneously.
Phase 2 becomes a formula configuration change rather than a data project.

**2. Add the Commitment Exhaustion Trajectory alert from Day 1.**  
The linear regression on credit burn rate is a 30-line SQL query. The alert fires
30+ days before the customer goes dark. The cost of building it is 2 hours. The cost
of not building it is an unexpected renewal conversation with no warning.

**3. Instrument the metric itself.**  
Build a `csm_action_log` event table that records when a CSM takes an action on a
flagged account, then measure whether that action improved PRS in the subsequent
60 days. Without this, the feedback loop is conceptually present but not operationally
measured. Version 2 closes this gap.

**4. Prioritize the POC-to-Prod orphaned tenant issue earlier.**  
This trap was discovered late. In retrospect, the signal that something was wrong
was visible early: several high-value accounts showed zero usage in production despite
sales team confidence they were highly engaged. Investigating that discrepancy sooner
would have surfaced the tenant mapping problem in week 2 rather than week 6.

---

## Appendix B: Connection to Prior Work

**Quality Hub (Microsoft Azure CXP):** Same multi-signal consolidation architecture
— support cases, outage events, product quality signals, and NDO/R2D data joined
into a single executive decision surface. Reduced VP/EVP reporting prep from 5 days
to 4 hours. The DQ gate approach in this pipeline mirrors the Quality Hub ingestion
validation — every signal source required a quality check before entering the
composite score.

**FastTrack Product Feedback Intelligence:** Applied Azure AI Cognitive Services to
convert 3,179+ customer feedback submissions and 600+ verbatims into sentiment-scored,
ranked requirements with 74% product acceptance rate. The AI narrative layer in
Section 10 uses the same LLM-over-structured-signals architecture, applied to account
health signals instead of product feedback.

**Iridias (Microsoft Azure CXP):** Copilot-powered LLM outage triage tool that reduced
manual incident classification effort by 60%, recovering 4,000+ engineering hours
annually. The AI narrative generation in the dashboard's "Generate Analysis" feature
is a direct application of the Iridias design principle: structured signals in,
human-readable action out.

The core discipline is identical across all three: **convert fragmented signals into a
single trusted number that enables a specific decision. Do not build another report.**

---

*Document prepared by Dharmesh Bhagat, Principal PM, Centralized Data & AI*  
*Version 2.0 — built using a spec-driven AI development methodology.*  
*All requirements defined in Markdown before any code was written.*
