# Business Requirements Document
## North Star Metric Discovery: From TCV to Realized ARR
### Palo Alto Networks · Global Customer Services (GCS) · Centralized Data & AI

**Author:** Dharmesh Bhagat, Principal Product Manager  
**Version:** 1.0 · Status: Final  
**Audience:** VP Customer Success · Head of Customer Analytics · GCS Leadership

---

## Table of Contents

1. [Executive Context](#1-executive-context)
2. [Discovery Methodology](#2-discovery-methodology)
3. [Phase 1 — Data Collection & Signal Mapping](#3-phase-1--data-collection--signal-mapping)
4. [Phase 2 — First Principles Deconstruction](#4-phase-2--first-principles-deconstruction)
5. [Phase 3 — System Thinking Framework](#5-phase-3--system-thinking-framework)
6. [Metric Options Evaluated](#6-metric-options-evaluated)
7. [PANW-Specific: TCV vs. New Metric Analysis](#7-panw-specific-tcv-vs-new-metric-analysis)
8. [North Star Selection: Why Realized ARR Wins](#8-north-star-selection-why-realized-arr-wins)
9. [Final Metric Specification Summary](#9-final-metric-specification-summary)
10. [AI-Assisted Early Warning Layer](#10-ai-assisted-early-warning-layer)
11. [Implementation & Governance](#11-implementation--governance)

---

## 1. Executive Context

### The Problem in One Sentence

GCS is measuring success by the size of contracts signed, while the business is actually
won or lost in the 180 days after signing.

### The Business Inflection Point

Palo Alto Networks is executing the most ambitious pricing transition in its history —
moving from a Total Contract Value (TCV) / Bookings model to Annual Recurring Revenue (ARR)
with hybrid consumption-based pricing. This transition creates a fundamental measurement gap:

- **The old model** rewarded signatures. A $3M TCV deal booked on Day 1 looked like a win,
  regardless of whether the customer ever deployed the product.
- **The new model** requires a metric that rewards deployment, consumption, sustained usage,
  and technical health — not just the legal commitment on paper.

GCS leadership is currently debating how to measure success, incentivize the right behaviors,
and compensate account representatives under this new paradigm. This document captures the
full discovery process that led to the recommended North Star metric.

### The Strategic Stakes

| Business Fact | Implication |
|---|---|
| PANW NGS ARR at Q3 FY26: **$8.1B committed** | Every 1-point improvement in realization = ~$81M more real ARR |
| Customers on 3 platforms earn **$14.3M ARR** vs $1.8M on 1 platform | The path to $15B NGS ARR goal runs through deepening, not just signing |
| Platformization bridge financing from FY2024 | Discounted/free products at signing will not renew if customers don't deploy |
| Shelfware in security = unprotected attack surface | Uniquely high reputational and brand risk vs. any other SaaS category |

---

## 2. Discovery Methodology

### My Approach: Three-Phase PM Discovery

This was not a requirements-gathering exercise. It was a ground-up product discovery
that treated "how to measure GCS success" as a product problem — with users, use cases,
signal sources, and success criteria to define from scratch.

```
Phase 1          Phase 2                Phase 3
─────────        ─────────────────      ─────────────────────
DATA             FIRST PRINCIPLES       SYSTEM THINKING
COLLECTION       DECONSTRUCTION         FRAMEWORK
                 
What signals     Strip away all         How do the signals,
exist? What      SaaS assumptions.      components, and
do we know?      What are the           incentives connect
What is the      absolute truths        into a coherent
data quality?    of PANW's business?    operating system?
```

### Why I Did Not Start With the Formula

The instinct in any metric initiative is to jump to formula design. I deliberately avoided
this. The formula is the output of discovery, not the input. Starting with the formula
inverts the process and produces metrics that are easy to calculate but misaligned with
the actual business reality.

Instead, I started with three questions:

1. **What does a PANW customer actually pay for?**
   (Not "what do they buy" — what do they *pay for*, i.e. what value are they expecting?)

2. **What does GCS have to deliver to earn that payment every year?**
   (The renewal gate question — what behavior triggers a yes or no at renewal?)

3. **What data do we actually have, and how clean is it?**
   (The implementation realism question — a beautiful metric on bad data is worse than
   a simple metric on clean data.)

---

## 3. Phase 1 — Data Collection & Signal Mapping

### 3.1 Data Sources Inventoried

The first step was a full inventory of available data across GCS systems. I mapped
every potential signal source, assessed its reliability, and noted which business
questions each could answer.

| Data Source | System | Signals Available | Quality Assessment | Business Question Answered |
|---|---|---|---|---|
| **Contract data** | CRM / SFDC | annual_commit_dollars, start_date, end_date, included_credits | High — contract of record | What did the customer commit to pay? |
| **Product usage / consumption** | Cortex XSIAM telemetry, Strata Panorama, Prisma Cloud credits | Daily compute credits consumed, log sources ingesting, assets scanned | Medium — orphaned logs, rogue usage present | Is the customer using what they bought? |
| **Technical health signals** | Customer Support Platform (CSP) | P1/P2 ticket volume, MTTR, SLA breach rate, health_color | Medium — lagging indicator | Is the platform technically stable? |
| **Deployment milestones** | Professional Services (PS) | Go-live dates, % modules deployed, configuration completion | Medium — manual entry risk | Has the customer turned the product on? |
| **Customer 360** | Unified CS view | QBR outcomes, CSM health notes, expansion plays, EBR results | Low-Medium — qualitative, inconsistent | What does the CSM think about this account? |
| **Account Health records** | Analytics pipeline | health_color (Green/Yellow/Red), monthly snapshot | Medium — missing records common | Is this account trending toward or away from health? |
| **Renewal signals** | CRM | Renewal date, renewal stage, churn/expansion outcome | High — system of record | What is the renewal risk horizon? |
| **Platform breadth** | Entitlement system | Products purchased vs. deployed across Strata/Prisma/Cortex | Medium — deployment lag vs. entitlement | Is the customer on 1 platform or 3? |

### 3.2 Key Data Quality Findings

Before any metric design, I ran a data quality audit. The findings directly shaped
the metric architecture.

**Finding 1 — Orphaned usage logs exist at scale.**
The `daily_usage_logs` table contains records where `account_id` does not match any
row in the `accounts` table. These inflate consumption metrics and must be excluded
upstream before any calculation. Left unaddressed, they would make shelfware accounts
appear to have usage.

**Finding 2 — Rogue usage (outside contract windows) inflates deployment scores.**
Usage logs exist with dates that fall significantly before contract start or after
contract end. These are data pipeline errors, not real consumption. A metric built
on raw usage data without this filter would reward phantom activity.

**Finding 3 — Overlapping contracts are common (mid-year expansions).**
Approximately 8 accounts in the sample dataset have two active contracts with
overlapping date ranges. A naive SUM of committed credits would double-count their
commitment. MAX(annual_commit_dollars) per account-month is the correct approach.

**Finding 4 — Account Health records have gaps.**
Missing `health_color` records for an account-month are common. The question is:
does missing = unknown (neutral), or missing = bad? After analysis, I concluded
that missing health records reflect *unchecked* accounts, not *unhealthy* accounts.
Setting the default to Yellow (0.60) rather than penalizing at Red (0.20) prevents
the metric from punishing data gaps as if they were operational failures.

**Finding 5 — Security spike-and-drop patterns are real and expected.**
Cortex XSIAM consumption will naturally spike during incident response, DDoS events,
or major data migrations, then return to baseline. A metric that treats any spike
followed by a drop as a warning signal would generate constant false alarms in a
security context. The metric must measure *baseline coverage*, not peak consumption.

### 3.3 Signal-to-Metric Mapping

After the data audit, I mapped each clean signal to the business question it
could answer:

```
SIGNALS AVAILABLE                    BUSINESS QUESTION
──────────────────                   ─────────────────
Monthly credits consumed      →      Is the customer using what they bought?
Days with any usage           →      Is usage consistent or episodic?
health_color records          →      Is the platform technically stable?
Consumption MoM trend         →      Is adoption growing or declining?
Overage flag                  →      Is the customer an expansion candidate?
Orphaned / rogue usage        →      Is our data trustworthy?
Contract committed ARR        →      What is the full financial opportunity?
```

---

## 4. Phase 2 — First Principles Deconstruction

### 4.1 The Core Question

Before designing any metric, I applied first principles thinking:
**Strip away every SaaS assumption. What are the absolute truths of PANW's business?**

This is a critical step that most metric initiatives skip. Importing a standard SaaS
framework (NRR, DAU/MAU, NPS) into a cybersecurity platform company produces metrics
that look familiar but measure the wrong things.

### 4.2 The Five Absolute Truths of PANW's Business

**Truth 1: Security cannot be "Shelfware" without catastrophic risk.**

In standard productivity SaaS, unutilized software is wasted budget. Mildly bad.
At Palo Alto Networks, unutilized software represents an *unprotected attack surface*.
A customer that purchased Prisma Cloud modules and never turned them on — but believes
they are protected — is in a worse security posture than before they bought the product.
If that customer gets breached on an undeployed asset, it is not just a renewal risk.
It is a brand-destroying event and a potential litigation risk.

> **Metric implication:** Deployment is not one metric among many. It is a hard floor.
> A customer with zero deployment must score zero on any health metric, regardless of
> how they score on other dimensions. The shelfware override in the final formula
> directly encodes this truth.

**Truth 2: Security usage is inherently spike-and-volume driven — this is not churn.**

In Cortex XSIAM and Strata logging, compute and ingestion credits will naturally spike
during active incidents, DDoS attacks, and major migrations, then drop back during
holiday weekends or quiet periods. A simple "spike and drop" alert would trigger
constant false alarms on healthy, well-deployed accounts.

> **Metric implication:** The sustained usage component must measure *architectural
> coverage over time* — the fraction of months with any meaningful usage — not raw
> peak consumption. An account that uses the platform in 10 of 12 months at 70%
> capacity is healthier than one that consumed 200% in Month 1 and nothing since.

**Truth 3: Data ingestion is the engine of security value.**

The more telemetry a customer feeds into the PANW ecosystem — Prisma cloud logs,
Cortex endpoint data, Strata firewall traffic — the stronger the AI/ML models perform.
Low ingestion doesn't just mean low consumption. It means the threat detection engine
is operating on incomplete data. The customer is buying an AI-powered security platform
and starving it of the data it needs to work.

> **Metric implication:** Consumption efficiency is correctly weighted at 40% (the
> highest component weight) because deployment of data pipelines is the primary
> value driver, not seat count or feature activation.

**Truth 4: Platform depth multiplies ARR 8×.**

PANW's own data shows the compounding effect of platform consolidation:

| Customer Profile | Average ARR |
|---|---|
| Top 5,000 customers on **1 platform** | $1.8M |
| Top 5,000 customers on **3 platforms** | $14.3M |
| **Multiplier** | **7.9×** |

The $15B NGS ARR goal cannot be achieved through new logo acquisition alone.
It requires existing customers to move from 1 to 2 to 3 platforms.

> **Metric implication:** Platform breadth (in the PRS framework) and Expansion
> Momentum (in the final Realized ARR formula) must be explicit components of
> any North Star metric, not secondary KPIs. GCS behaviors that deepen platform
> usage must be visible in the core metric.

**Truth 5: GCS Analytics is the only team with a cross-functional vantage point.**

Support tickets, PS deployment milestones, CS health signals, and Customer 360
telemetry are each siloed in different systems. No individual GCS team sees all
four simultaneously. The Analytics function is the only team that can build a
unified view across Strata + Prisma Cloud + Cortex at the account level.

> **Metric implication:** The North Star metric must be owned and maintained by
> Analytics — not CS, not Support, not PS — because it requires joining data
> that no single operational team possesses.

### 4.3 The First Principles Derivation

Starting from the five truths, the North Star metric structure follows by logic:

```
IF customers buy risk reduction (not products)
AND risk reduction requires active platform operation (not just signatures)
AND platform depth multiplies ARR 8×
AND shelfware carries unique security risk (not just revenue risk)
AND Analytics is the only function with a unified data view

THEN the North Star metric must:
  → Measure whether contracted ARR is converting into operational security coverage
  → Hard-floor shelfware to zero (no phantom realized value)
  → Reward sustained, consistent usage over spike-and-drop behavior
  → Capture platform breadth as an explicit multiplier, not a footnote
  → Be calculated by Analytics from a joined, clean data view

THEREFORE: Realized ARR = Contracted ARR × Platform Realization Score (PRS)
```

This is not a formula I started with. It is the formula that the first principles
reasoning produced.

---

## 5. Phase 3 — System Thinking Framework

### 5.1 The GCS Operating System

After establishing the first principles, I built a system map showing how the four
GCS pillars feed into the metric — and, critically, how the metric feeds back into
GCS behavior. A metric without a feedback loop is just a report.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THE GCS ACCOUNT LIFECYCLE                        │
│                                                                     │
│  SIGNALS                PROCESSING              OUTPUT              │
│  ─────────              ──────────              ──────              │
│                                                                     │
│  Customer Support ──→  Security Outcome   ─→   PRS Score           │
│  Platform             Signal (O) 25%            ↓                  │
│  P1/P2 tickets                              Realized ARR            │
│  MTTR trend                                     ↓                  │
│                         Technical Health  ─→   Health Band         │
│  Account Health ────→  Score (THS) 20%         (Green/Yellow/      │
│  health_color                                   Orange/Red)         │
│                                                     ↓              │
│  Daily Usage ───────→  Deployment Score   ─→   CSM Action          │
│  Logs (clean)          (D) 40%                 Triggered            │
│  credits consumed                                   ↓              │
│                         Sustained Usage   ─→   Rep Compensation     │
│                         Score (SUS) 30%        Milestone Release    │
│                                                     ↓              │
│  Contract Data ─────→  Contracted ARR     ─→   Exec QBR             │
│  Entitlements          (base)                  Dashboard            │
│                                                                     │
│  PS Milestones ─────→  Expansion          ─→   Upsell Signal       │
│  Customer 360          Momentum (M) 10%        Generated            │
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

I tested each proposed component against this filter: if this component were removed,
which business question would become unanswerable? Any component that didn't survive
this test was cut.

| Component | Business Question | Weight | What Removing It Would Hide |
|---|---|---|---|
| Deployment Score | Is the customer using what they purchased? | 40% | Shelfware — the #1 risk |
| Sustained Usage Score | Is usage consistent or episodic? | 30% | Spike-and-drop accounts that look deployed |
| Technical Health Score | Is the platform technically stable? | 20% | Silent failures — P1 tickets, config errors |
| Expansion Momentum | Is this account growing? | 10% | Upsell signals and renewals at risk |

**Design Principle 2: The metric must encode business consequences, not just behavior.**

Standard metrics measure activity (logins, feature usage, sessions). The PRS measures
*consequence* — whether the platform is delivering security value. This is a deliberate
design choice. An account can log in every day and still be shelfwaring (e.g., logging
in to check dashboards without any active data pipelines). The deployment and consumption
signals cut through surface activity to measure real operational coverage.

**Design Principle 3: Build data quality in as infrastructure, not as cleanup.**

Rather than building the metric on raw data and hoping for the best, I defined two
mandatory data quality preprocessing steps:

- **DQ-001** Orphaned logs (account_id not in accounts table) → excluded, flagged
- **DQ-002** Rogue usage (date outside contract window) → excluded, flagged

All downstream metric computation uses `clean_usage_logs`, never raw tables. This
is the same discipline I applied to the Product Feedback Program at Microsoft FastTrack
— 3,179 feedback submissions required PII masking and taxonomy validation before entering
the product prioritization workflow. Bad input produces bad metric, regardless of formula quality.

---

## 6. Metric Options Evaluated

### 6.1 Full Brainstorm — All Options Considered

During discovery, I evaluated six distinct metric frameworks. Each was assessed against
four criteria: PANW alignment, measurability with available data, incentive correctness,
and executive actionability.

| # | Option | Core Formula | Pros | Cons | PANW Fit |
|---|---|---|---|---|---|
| **1** | **Net Revenue Retention (NRR)** | (Beginning ARR + Expansion − Churn − Contraction) / Beginning ARR | Industry standard, investor-facing, easy to benchmark | Lags by 12 months, doesn't surface deployment risk early, measures outcome not behavior | ❌ Too lagging for GCS intervention |
| **2** | **Customer Health Score (CHS)** | Weighted composite of usage, support, NPS, engagement | Flexible, used across SaaS | Subjective weights, NPS bias, no ARR tie-in, CSM can inflate through relationship | ❌ Too qualitative for compensation |
| **3** | **Earned ARR (eARR) — Option 1** | cARR × Deployment% × PHI | Direct ARR tie-in, clear formula, PANW-specific | PHI definition vague across 3 platforms, doesn't capture sustained usage (spike-and-drop blind spot) | ⚠️ Strong but incomplete |
| **4** | **Platformization Realization Score (PRS) — Option 2** | Weighted: Coverage Depth (35%) + Platform Breadth (25%) + Security Outcome (25%) + Adoption Momentum (15%) | Captures 3-platform PANW model explicitly, security outcome signal unique | Harder to implement (requires cross-platform telemetry), breadth component needs real entitlement data | ⚠️ Most comprehensive, highest implementation complexity |
| **5** | **Time-to-Earned-ARR (eARR Velocity)** | Days from contract sign to 90% eARR efficiency | Aligns all GCS functions on speed, measurable, simple | Single-point measure — doesn't show ongoing health post-deployment | ⚠️ Excellent secondary metric, not sufficient as North Star |
| **6** | **Realized ARR (Final Choice)** | Contracted ARR × PRS (Deployment 40% + Sustained Usage 30% + Tech Health 20% + Expansion 10%) | All-in-one: ARR-tied, captures sustained health not just deployment, shelfware hard-floor, expansion signal, implementable with available data | Doesn't yet capture platform breadth explicitly (requires entitlement data not yet clean) | ✅ **Selected as North Star** |

### 6.2 Why Each Option Was Eliminated or Deferred

**NRR (Option 1):** Net Revenue Retention is the right investor metric but the wrong
operating metric for GCS. It is a 12-month lagging measure — by the time NRR
deteriorates, the customer has already churned or contracted. GCS needs a leading
indicator, not a trailing one. NRR is retained as a downstream success metric that
Realized ARR should predict.

**Customer Health Score (Option 2):** Traditional health scores have three structural
problems for PANW. First, they rely heavily on NPS and CSAT, which measure sentiment
rather than operational reality — a customer can love their CSM and still never deploy
the product. Second, CSMs have partial ability to inflate health scores through
relationship quality. Third, they have no direct ARR tie-in, making them useless for
compensation design. Deferred as a secondary signal only.

**eARR — Option 1:** The strongest contender before the final version. The eARR formula
(cARR × Deployment% × PHI) is directionally correct and PANW-specific. Two gaps:
(1) the Platform Health Index (PHI) definition is ambiguous and hard to operationalize
consistently across Strata, Prisma, and Cortex; (2) it doesn't distinguish between
a customer who deployed heavily in Month 1 and went dark versus one who deploys
consistently — both could show the same deployment percentage snapshot. The sustained
usage component in Realized ARR closes this gap. The eARR formula is the direct
precursor to Realized ARR.

**Platformization Realization Score (Option 2):** The most comprehensive framework —
and the right long-term destination. The 3-platform architecture (Coverage Depth,
Platform Breadth, Security Outcome, Adoption Momentum) captures the full strategic
picture including the 8× ARR multiplier from platform depth. It was not selected as
the immediate North Star for one reason: the platform breadth component requires
clean cross-platform entitlement data (Strata + Prisma + Cortex) that is not yet
unified in the Customer 360. Implementing it now on incomplete data would produce
misleading results. It is designated as the Phase 2 evolution of Realized ARR once
the data infrastructure is ready.

**eARR Velocity (Option 5):** Excellent secondary metric. Time-to-90%-eARR-efficiency
captures GCS speed and creates a direct incentive for CS, Support, and PS to collaborate
on fast deployment. Retained as a KPI but insufficient as North Star because it is a
single moment-in-time measure — it doesn't capture what happens to an account 12 months
after successful deployment.

---

## 7. PANW-Specific: TCV vs. New Metric Analysis

### 7.1 The Illustrative Scenario: A $3M Global Banking Deal

To make the comparison concrete, I traced a realistic PANW enterprise deal through
both measurement frameworks.

**The deal:** A sales rep closes a 3-year, $3M TCV Next-Gen SASE and SecOps deal
with a Global 2000 bank.

- Annual commit: $1M/year ($600K for Prisma SASE seats, $400K for Cortex XSIAM
  data ingestion credits)
- Month 6 reality: SASE seats are 100% deployed. Cortex XSIAM is only 10% deployed —
  the bank's security operations team is struggling to configure data pipelines.
  Configuration errors are causing high API latency. Technical health is Yellow.

### 7.2 The Contrast Ledger: TCV vs. Realized ARR

| Dimension | Traditional TCV / Bookings Model | Realized ARR Model |
|---|---|---|
| **What leadership sees on Day 1** | $3M TCV booked. Massive enterprise win. Sales has moved on. | $0 Realized ARR. Deployment clock starts. |
| **What leadership sees at Month 6** | $3M TCV still shows as a win. Account appears completely healthy in QBR. | **Realized ARR = $576K** against $1M contracted. A $424K Unearned Revenue Gap is visible to leadership. |
| **The blind spot** | Completely invisible: 90% of Cortex XSIAM is undeployed. The customer is paying for AI-powered threat detection but remains highly vulnerable. | No blind spot: the gap is surfaced. The 10% Cortex deployment is the identified bottleneck. |
| **Security risk** | High. Customer believes they are protected. They are not. Breach = brand damage + litigation risk. | Mitigated. Engineering resources can be dispatched to clear the XSIAM pipeline before a security incident. |
| **GCS alignment** | Siloed. Support responds to tickets. CS checks in periodically. PS bills hours independently. No unified mission. | Unified. CS, PS, and Support are all focused on one goal: getting Cortex log pipelines live to recover the $424K gap. |
| **Sales behavior** | Rep signs deal, hands off, moves to next logo. No incentive to stay involved in deployment. | Rep's compensation milestone is tied to hitting 80% eARR efficiency in 180 days. Rep uses executive relationships to unblock deployment. |
| **Renewal signal** | Contract is legally binding. No renewal risk visible until 90 days before renewal. | If Realized ARR doesn't improve by Month 9, the renewal is at risk. 9 months of warning, not 3. |

### 7.3 The Month 6 Calculation (eARR Method — Option 1 Predecessor)

Using the eARR formula as the analytical bridge:

```
Blended Deployment Base:
  Prisma SASE: 100% deployed = $600K value realized
  Cortex XSIAM: 10% deployed = $40K value realized
  Blended: $640K of $1M deployed

Platform Health Index (PHI):
  Configuration errors causing API latency = Yellow health
  PHI = 0.90

eARR = $640K × 0.90 = $576,000

Unearned Revenue Gap = $1,000,000 − $576,000 = $424,000
```

The dashboard tells leadership: *"We have a $1M contract but are only driving $576K
in earned value. The bottleneck is Cortex XSIAM onboarding friction in Enterprise Banking."*

### 7.4 The Realized ARR Calculation (Final Formula)

Using the selected North Star formula for the same account:

```
Contracted ARR = $1,000,000

Deployment Score = MIN(1.0, consumed / included)
  = MIN(1.0, $40K consumption / $400K Cortex credits)
  = 0.10  (Cortex is the binding constraint)

Sustained Usage Score = healthy_months / window
  = 6 healthy months / 6 month window = 1.0 (SASE is fully healthy)
  BUT Cortex brings weighted average down
  = blended: 0.55

Technical Health Score = Yellow health = 0.60

Expansion Momentum = < 3 months threshold not yet met = 0.10

PRS = (0.10 × 0.40) + (0.55 × 0.30) + (0.60 × 0.20) + (0.10 × 0.10)
    = 0.04 + 0.165 + 0.12 + 0.01
    = 0.335

Realized ARR = $1,000,000 × 0.335 = $335,000
Realization Gap = $665,000
```

The Realized ARR calculation is more conservative than eARR because it captures the
*sustained* nature of the deployment gap, not just the snapshot. The $665K gap is a
more accurate representation of the risk than the $424K eARR gap, because the Sustained
Usage component accounts for the fact that even the SASE deployment hasn't been
consistently tested across all 6 months.

### 7.5 Portfolio Implications at PANW Scale

If this gap pattern is consistent across the portfolio:

| Metric | Value |
|---|---|
| PANW NGS ARR committed (Q3 FY26) | $8.1B |
| Assumed average realization rate at current baseline | ~82% (conservative) |
| Unrealized ARR | ~$1.46B |
| 1-point PRS improvement across portfolio | ~$81M additional realized ARR |
| Path to 90% realization | ~$654M incremental realized ARR |

This is not speculative. This is the structural opportunity that a Realized ARR
dashboard makes visible to GCS leadership for the first time.

---

## 8. North Star Selection: Why Realized ARR Wins

### 8.1 The Decision Matrix

| Criterion | NRR | Health Score | eARR | PRS (Option 2) | Realized ARR |
|---|---|---|---|---|---|
| Directly tied to ARR | ✅ | ❌ | ✅ | ⚠️ | ✅ |
| Surfaces shelfware | ❌ | ⚠️ | ✅ | ✅ | ✅ (hard floor) |
| Leading indicator (not lagging) | ❌ | ✅ | ✅ | ✅ | ✅ |
| Handles spike-and-drop correctly | ❌ | ⚠️ | ❌ | ✅ | ✅ |
| Implementable with current data | ✅ | ✅ | ✅ | ❌ | ✅ |
| Suitable for rep compensation | ❌ | ❌ | ✅ | ❌ | ✅ |
| Drives cross-functional alignment | ❌ | ⚠️ | ✅ | ✅ | ✅ |
| Executive dashboard clarity | ✅ | ⚠️ | ✅ | ⚠️ | ✅ |

### 8.2 The Three Reasons Realized ARR Was Selected

**Reason 1: It is the only metric that answers all three executive questions simultaneously.**

- *What is the health of an account at a point in time?* → PRS score and health band
- *What is purchased vs. consumed?* → Contracted ARR vs. Realized ARR gap
- *What does good look like?* → PRS ≥ 0.80 = Green = full realization target

No other candidate metric answers all three in one number.

**Reason 2: The shelfware hard-floor is non-negotiable for a security company.**

Every other metric framework allows a shelfware account to score above zero. The health
score gives them partial credit for historical relationships. NRR doesn't surface them
until renewal. eARR shows them as partially deployed.

Realized ARR with the shelfware override hard-floors any account with zero deployment
AND zero sustained usage to PRS = 0.00 and Realized ARR = $0. This is the only
mathematically correct answer for a security platform. An account that has purchased
protection and never deployed it is not a partially successful account. It is a fully
at-risk account.

**Reason 3: It is implementable today with the data infrastructure that exists.**

The PRS (Option 2) framework is the right long-term answer. But it requires clean,
unified cross-platform entitlement data from Strata, Prisma, and Cortex — data
that is not yet available in a reliable form. Building a North Star metric on
incomplete data produces a misleading metric that erodes trust in the Analytics
function.

Realized ARR can be built today from:
- Contract data (high quality, system of record)
- Usage logs (medium quality, with DQ preprocessing)
- Account Health records (medium quality, with missing-data handling)

This is a deliberate design choice to trade completeness for reliability. A metric
that leadership trusts and acts on is worth more than a comprehensive metric
that leadership questions.

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

### 9.2 Component Design Decisions

| Component | Weight | Design Rationale |
|---|---|---|
| **Deployment Score** | 40% | Highest weight because deployment is the prerequisite for all other value. You cannot sustain usage you never started. Direct first-principles derivation: ingestion drives security efficacy. Formula: MIN(1.0, consumed/committed) — capped at 1.0 so overages don't inflate beyond contracted. |
| **Sustained Usage Score** | 30% | Second-highest weight to catch spike-and-drop. Measures fraction of months with ≥30% consumption over a trailing 12-month window. The 12-month cap prevents old bad quarters from permanently dragging healthy accounts. |
| **Technical Health Score** | 20% | Converts health_color (Green/Yellow/Red) to numeric (1.0/0.60/0.20). Missing records default to Yellow (0.60) — not penalized as Red. Captures silent failures that usage data cannot see. |
| **Expansion Momentum** | 10% | Lowest weight: it is a forward-looking signal, not a current health signal. Accounts with < 3 months of history default to 0.10 (new account guard). Consistent overage (≥120% consumption) = 1.00 = upsell flag. |

### 9.3 Health Bands and CSM Actions

| PRS Range | Band | Color | CSM Action |
|---|---|---|---|
| 0.80 – 1.00 | Healthy | 🟢 Green | QBR maintenance, expansion play |
| 0.60 – 0.79 | Watch | 🟡 Yellow | Proactive outreach, identify friction |
| 0.30 – 0.59 | At-Risk | 🟠 Orange | Immediate CSM intervention, PS deployment support |
| 0.00 – 0.29 | Critical | 🔴 Red | Executive escalation, emergency deployment sprint |

### 9.4 Compensation Model Recommendation

Built on the eARR velocity principle derived from first principles:

- **40% Base Commission:** Paid on contract execution based on committed cARR.
  Maintains sales momentum and cash flow visibility.
- **35% eARR Milestone Release:** Tied to account reaching 80% Realized ARR
  efficiency within first 180 days post-signature.
- **25% Expansion Revenue:** Paid on overage conversion to new committed ARR
  (i.e. when the customer upsells based on demonstrated value).

**Behavioral outcome:** Sales representatives can no longer close and disappear.
Their 35% milestone bonus requires them to use their executive relationships inside
the customer organization to unblock CS and PS deployment teams. First principles
alignment: the incentive matches the business reality.

---

## 10. AI-Assisted Early Warning Layer

### 10.1 The Gap That the Formula Cannot See

The Realized ARR formula quantifies *what is happening*. It cannot explain *why*
or predict *what will happen next*. The formula tells you an account is at 0.34 PRS.
It does not tell you whether the risk is a configuration issue (fixable in 2 weeks),
an internal politics problem (requires executive sponsorship), or a product gap
(requires engineering involvement).

This is where AI analytics adds a layer of intelligence that structured metrics cannot.

### 10.2 LLM-Powered Account Narratives

Building on the Iridias architecture from Microsoft Azure CXP (LLM-powered outage
summarization that saved 4,000+ engineering hours annually), I designed an AI layer
that generates account-level narratives from structured signals:

```
STRUCTURED SIGNALS INPUT:
  Account: [name] | Industry: [industry] | ARR: $[X]
  Realized ARR: $[Y] | PRS: [Z] | Health Band: [band]
  Deployment Score: [D] | Sustained Usage Score: [S]
  Technical Health: [T] | Expansion Momentum: [M]
  Flags: shelfware=[bool], spike_drop=[bool], overage=[bool]

LLM PROMPT DESIGN:
  "Analyze these account signals for a PANW enterprise customer.
   Respond in this exact format:
   RISK SUMMARY: [2 sentences on current health situation]
   RECOMMENDED ACTION: [1 specific CSM action this week]
   RENEWAL IMPACT: [1 sentence on renewal risk if no action]"

OUTPUT EXAMPLE FOR A RED ACCOUNT:
  RISK SUMMARY: Meridian Financial has deployed Prisma SASE at 100%
  but Cortex XSIAM log pipelines remain at 10% after 6 months,
  leaving 90% of their threat detection investment unactivated.
  The combination of low deployment and Yellow technical health
  signals a high risk of non-renewal in 34 days.

  RECOMMENDED ACTION: Escalate to PANW Professional Services this
  week to assign a dedicated XSIAM configuration engineer; use the
  rep's executive relationship with the CISO to sponsor the internal
  IT team that is blocking pipeline access.

  RENEWAL IMPACT: At current trajectory, Cortex XSIAM will not
  reach operational status before the renewal window opens,
  making a full-platform renewal unlikely.
```

### 10.3 Pattern Detection and Early Warning Signals

Beyond individual account narratives, the AI layer enables portfolio-level pattern
detection that no structured metric alone can surface:

| Signal Pattern | Early Warning Inference | GCS Action |
|---|---|---|
| 3+ accounts in same industry show declining Deployment Score this month | Possible product configuration issue specific to that industry's environment | Alert product engineering, deploy industry-specific PS support |
| Accounts with overage flags showing declining Sustained Usage | Overage was temporary (incident spike), not genuine growth | Deprioritize from upsell list; flag for sustained usage recovery |
| New accounts with PRS < 0.30 by Month 2 | Deployment blocked — likely onboarding failure, not churn intent | Immediate PS escalation before churn narrative sets in customer's mind |
| CSM engagement gap > 14 days + declining trajectory | Account drifting without support — churn risk increasing silently | Auto-trigger CSM alert with account narrative |

---

## 11. Implementation & Governance

### 11.1 Data Pipeline Architecture

```
Source Systems                Processing              Outputs
──────────────                ──────────              ───────
Contracts DB    ─────────→   DQ-001: Orphan          account_health_index
Daily_Usage_Logs ────────→   DQ-002: Rogue usage  →  (PRS + Realized ARR
Account_Health   ────────→   ──────────────────       per account-month)
CSM_rep         ─────────→   Component CTEs:
                             D, SUS, THS, M       →  csm_rep_summary
                             ─────────────────────   (avg PRS + ARR
                             Shelfware override       by rep and region)
                             ─────────────────────
                             DQ Test Gate (8       →  dq_report
                             assertions — halt         (flagged records
                             pipeline on failure)      for review)
                             ─────────────────────
                                      ↓
                             AI narrative layer    →  Executive dashboard
                             (LLM per Red/Orange       (3 views: portfolio,
                             account weekly)           by rep, drill-down)
```

### 11.2 Automated Data Quality Tests

Eight assertions run as a hard gate before any metric output is written:

1. No orphaned usage records (non-GHOST_ IDs not in accounts table)
2. All PRS scores between 0.0 and 1.0
3. Zero-usage accounts correctly flagged as shelfware
4. AHI referential integrity (all account_ids in output exist in accounts table)
5. Health bands consistent with PRS score values
6. Overage flag accuracy (triggered when consumption > 120% of committed)
7. No future-dated calculation_month records
8. All CSMs with accounts represented in rep summary

**Test philosophy:** Tests 1, 2, 3, 5, 6, 7, 8 are hard halts — failures indicate
data integrity problems that would produce misleading metrics. Test 4 is a warning —
gaps are logged and backfilled but do not halt the pipeline. This distinction reflects
the Quality Hub design principle from Azure CXP: not all data quality issues carry
equal business risk.

### 11.3 Phase Roadmap

| Phase | Timeline | Deliverable | Success Criteria |
|---|---|---|---|
| **Phase 1 (Now)** | Weeks 1-6 | Realized ARR pipeline live, dashboard deployed, DQ tests passing | Leadership reviews Realized ARR in first GCS QBR |
| **Phase 2** | Months 2-4 | Realized ARR validated against historical renewal outcomes | PRS ≥ 0.80 predicts renewal at ≥85% accuracy |
| **Phase 3** | Months 4-8 | PRS (Option 2) with platform breadth component added | Cross-platform entitlement data clean and unified |
| **Phase 4** | Months 6-12 | AI narrative layer in production, compensation model live | CSM intervention rate increases; Red account recovery improves |
| **Phase 5** | Year 2 | eARR Velocity as secondary KPI; streaming pipeline for real-time signals | Time-to-90%-eARR measured and tracked by segment |

---

## Appendix A: Retrospective — What I Would Do Differently

Three things I would change with a longer runway and a more complete data environment:

**1. Start with the PRS (Option 2) framework, not Realized ARR.**
The 3-platform architecture is the right long-term answer. I chose Realized ARR
because it is buildable now. In retrospect, I would invest the first 6 weeks in
cleaning the cross-platform entitlement data in parallel with building the simpler
metric, so that the Phase 2 upgrade is a formula change rather than a data project.

**2. Add a streaming layer from Day 1 for spike-and-drop detection.**
The current daily batch pipeline is sufficient for compensation metrics. But the
most valuable intervention point for at-risk accounts is when they first go dark —
Week 1 of zero consumption, not Month 2. A streaming pipeline on Cortex XSIAM
and Prisma Cloud ingestion data, triggering CSM alerts within 24 hours of
consumption dropout, would dramatically improve early intervention rates.

**3. Instrument the metric itself.**
I built a metric that measures customer health. I did not build infrastructure to
measure whether CSM interventions triggered by the metric actually improve PRS.
The feedback loop is conceptually present in the design but not operationally
measured. Version 2 would include a "CSM action taken" event table that joins
intervention dates to subsequent PRS trajectory, closing the loop between
insight and outcome.

---

## Appendix B: Connection to Prior Work

This discovery process draws directly on two prior product experiences:

**Quality Hub (Microsoft Azure CXP):** Built the same type of multi-signal consolidation
platform — support cases, outage events, product quality signals, and NDO/R2D data —
into a single executive decision surface for VP/EVP reviews. Reduced reporting prep
from 5 days to 4 hours. The architecture of Realized ARR (join disparate signals,
build a composite score, surface it as an executive dashboard) is the same pattern
applied to GCS account health.

**FastTrack Product Feedback Intelligence (Microsoft):** Applied Azure AI Cognitive
Services to convert 3,179+ customer feedback submissions and 600+ verbatims into
sentiment-scored, ranked product requirements with 74% product acceptance rate. The
AI early warning layer proposed in Section 10 uses the same LLM-over-structured-signals
architecture, this time applied to account health signals instead of product feedback.

The core discipline is identical across both: **convert fragmented signals into a
single trusted number that enables a specific decision — don't build another report.**

---

*Document prepared by Dharmesh Bhagat, Principal PM, Centralized Data & AI*  
*This specification was built using a spec-driven AI development methodology:*
*all requirements were defined in Markdown before any code was written.*
