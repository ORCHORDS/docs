# Feature Prioritization Framework

**Project:** Beetle Studio  
**Owner:** Chris Taylor (Product Manager)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)  
**ISO Standards:** ISO/IEC 12207:2017 (requirements definition), ISO/IEC 25010:2023 (functional suitability, value)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | MoSCoW + RICE prioritization methodology |
| **Diátaxis form** | Explanation |
| **Primary audience** | Chris Taylor, all leads, Mooned Dev |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines how Chris Taylor prioritizes features and work items for the Beetle Studio roadmap. Per **ISO/IEC 12207:2017 section 6.1**, requirements must be evaluated and prioritized. This framework makes prioritization explicit, repeatable, and transparent.
## Contents

- [The Framework](#the-framework)
  - [Step 1: MoSCoW — Categorize](#step-1-moscow-categorize)
  - [Step 2: RICE — Score Within Categories](#step-2-rice-score-within-categories)
- [What Makes It to the Roadmap](#what-makes-it-to-the-roadmap)
  - [Must Have (Non-Negotiable)](#must-have-non-negotiable)
  - [Should Have (Weighted by RICE)](#should-have-weighted-by-rice)
  - [Could Have (RICE Tiebreaker)](#could-have-rice-tiebreaker)
- [Inputs to Prioritization](#inputs-to-prioritization)
- [The Prioritization Process](#the-prioritization-process)
- [Why Something Doesn't Make It](#why-something-doesnt-make-it)
- [Stakeholder Input](#stakeholder-input)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## The Framework

We use a hybrid approach: **MoSCoW** for categorization + **RICE** for scoring within categories.

### Step 1: MoSCoW — Categorize

| Category | Meaning | Target % of Sprint |
|---|---|---|
| **Must have** | Core functionality without which the product doesn't work as advertised | Sprint capacity |
| **Should have** | Important but not critical; workaround exists | Fill remaining capacity |
| **Could have** | Desirable improvements; no workaround but limited impact | Pick if capacity allows |
| **Won't have** (this release) | Explicitly deprioritized; documented why | N/A — parked |

### Step 2: RICE — Score Within Categories

RICE scores are calculated for items in each MoSCoW category to determine relative priority.

**RICE = (Reach × Impact × Confidence) / Effort**

| Factor | What It Measures | How to Calculate |
|---|---|---|
| **Reach** | How many users impacted per quarter | Estimated users affected (1–1000) |
| **Impact** | Effect on user outcomes | 3 = massive, 2 = high, 1 = medium, 0.5 = low, 0.25 = minimal |
| **Confidence** | How sure we are of estimates | 100% = data-backed, 80% = some data, 50% = gut feel |
| **Effort** | Person-months of engineering work | Engineering estimate (in months) |

**Example:**

| Feature | Reach | Impact | Confidence | Effort | RICE |
|---|---|---|---|---|---|
| GPU color wheels | 500 users/qtr | 2 (high) | 80% | 1 month | **800** |
| Timeline zoom gesture | 800 users/qtr | 1 (medium) | 100% | 0.25 months | **3,200** |
| AV1 encode | 100 users/qtr | 1 (medium) | 80% | 3 months | **27** |

Timeline zoom wins despite being "smaller" because it reaches more users at lower effort.

---

## What Makes It to the Roadmap

### Must Have (Non-Negotiable)

Must-haves are requirements that, if missing, would prevent us from shipping or would break core functionality:

- Feature is required for a committed release date
- Feature is a legal or compliance requirement
- Feature is needed to fix a critical regression from a previous version

### Should Have (Weighted by RICE)

Should-haves are prioritized using RICE. The higher the score, the sooner it ships.

### Could Have (RICE Tiebreaker)

Could-haves get picked if:
1. Two or more could-haves have the same RICE score
2. Sprint capacity allows after all must-haves and should-haves are scheduled

---

## Inputs to Prioritization

Chris Taylor considers these inputs when evaluating features:

| Input | Source | Weight |
|---|---|---|
| User feedback | Beta program, community forum, support tickets | High |
| Competitive analysis | What After Effects / DaVinci / Premiere ship | Medium |
| Sales feedback | Kevin Brown — what prospects ask about | Medium |
| Technical constraints | Kirk Beka — what's feasible this quarter | High |
| Business strategy | Mooned Dev — strategic direction | High |
| Technical debt | Kirk Beka — infrastructure work needed | Medium |
| Performance issues | Lisa Martinez — bugs that block features | High |

---

## The Prioritization Process

```
Feature Idea or Request
         │
         ▼
┌──────────────────────┐
│  Does it solve a     │── No ──► Park (Won't Have this release)
│  real user problem?  │
└──────────┬───────────┘
           │ Yes
           ▼
┌──────────────────────┐
│  Is it technically   │── No ──► Re-architect or park
│  feasible this quarter?│
└──────────┬───────────┘
           │ Yes
           ▼
┌──────────────────────┐
│  MoSCoW categorization│
│  Must / Should / Could │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Calculate RICE score │
│  within category      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Add to roadmap      │
│  with priority order  │
└──────────────────────┘
```

---

## Why Something Doesn't Make It

Features get parked. This is normal. Reasons are documented, not hidden:

- **Effort too high** — RICE score too low relative to other items
- **Not a user problem** — insufficient evidence that users actually need it
- **Wrong time** — technically infeasible this quarter; revisit next
- **Duplicate** — similar feature already in progress or shipped
- **Strategic fit** — important feature but conflicts with current product direction

When parking a feature, Chris Taylor records:
1. The reason it was parked
2. What would need to change for it to be a higher priority
3. A date to re-evaluate

---

## Stakeholder Input

| Stakeholder | How They Influence Priority |
|---|---|
| **Mooned Dev** | Sets strategic direction and hard constraints (e.g., "must ship Windows Store before Q4") |
| **Kirk Beka** | Flags technical feasibility, flags technical debt that must be addressed |
| **Beta users** | Vote with feedback — features with repeated requests get priority |
| **Sales (Kevin Brown)** | Flags what enterprise customers are asking for |
| **Lisa Martinez** | Flags quality issues that need to be addressed before new features |
| **Team** | Engineers can flag dependencies and complexity |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial framework — aligned with ISO/IEC 12207:2017 §6.1 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Requirements Definition and Evaluation), ISO/IEC 25010:2023 (Functional Suitability)*



---

## References

### Internal Documents

_No internal documents referenced._

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Chris Taylor | Initial version |
| 1.0.1 | June 2026 | Chris Taylor | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Chris Taylor (Product Manager)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type