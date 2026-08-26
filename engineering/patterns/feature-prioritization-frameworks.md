# feature-prioritization-frameworks

**Issue:** How to prioritize features — RICE, ICE, MoSCoW
**Date:** 2026-08-09
**Status:** documented

## Symptom
The product backlog has 200 features. The team ships 1 per
week. Customers ask for features that take a year to ship.
You ship a feature that no one uses. The team is frustrated.

## Root cause
**Prioritization is a discipline.** Without a framework, the
priorities are based on whoever shouts loudest.

**Source:** Various product management guides.

## The 3 frameworks

### 1. RICE (Intercom)

The RICE score = (Reach × Impact × Confidence) / Effort

- **Reach:** How many users does this affect per quarter?
- **Impact:** How much does it impact each user? (3=massive,
  2=high, 1=medium, 0.5=low, 0.25=minimal, 0=negligible)
- **Confidence:** How confident are you? (100%=high, 80%=
  medium, 50%=low)
- **Effort:** How many person-months?

| Feature | Reach | Impact | Confidence | Effort | RICE |
|---|---|---|---|---|---|
| Login | 100k | 3 | 100% | 2 | 150k |
| New dashboard | 50k | 2 | 80% | 4 | 20k |
| Photo upload | 10k | 1 | 50% | 1 | 5k |

The higher the RICE, the higher the priority.

✅ **Quantitative**
❌ **Subjective** (the impact score is opinion)
❌ **Time-consuming** (every feature needs a RICE)

### 2. ICE (Sean Ellis)

The ICE score = Impact × Confidence × Ease

- **Impact:** How much will it move the metric? (1-10)
- **Confidence:** How sure are you? (1-10)
- **Ease:** How easy is it? (1-10)

| Feature | Impact | Confidence | Ease | ICE |
|---|---|---|---|---|
| Login | 9 | 10 | 7 | 630 |
| New dashboard | 7 | 5 | 4 | 140 |
| Photo upload | 5 | 5 | 9 | 225 |

Faster than RICE; less precise.

✅ **Fast**
❌ **Less precise**
❌ **Easy to game** (everyone scores their favorite feature 10)

### 3. MoSCoW

A categorization, not a score.

- **Must have:** Critical; without it, the product doesn't
  work
- **Should have:** Important; the product works without it,
  but it's a pain
- **Could have:** Nice to have; would be nice but not
  essential
- **Won't have (this time):** Out of scope for this release

| Feature | MoSCoW |
|---|---|
| Login | Must |
| Dashboard | Must |
| Photo upload | Should |
| Search | Should |
| Dark mode | Could |
| AI summaries | Won't (this time) |

✅ **Simple**
❌ **No relative priority** (3 "Must haves" compete)

## The hybrid approach

Use RICE for big features, MoSCoW for sprint planning:
1. **Quarterly:** Use RICE to decide what to build this
   quarter
2. **Per sprint:** Use MoSCoW to decide what's in the next
   sprint
3. **Per story:** Use ICE for "is this story worth doing
   in this sprint?"

## The "say no" framework

A backlog of 200 features is a backlog of 200 things you've
said "yes" to. To prioritize, you have to say "no."

The "say no" framework:
- **What it is:** A clear, documented reason for NOT doing
  something
- **When to use it:** When a feature doesn't meet the bar
- **Who decides:** The product owner

Common "no" reasons:
- **Low RICE:** The math says no
- **Wrong segment:** It's a feature for users we don't serve
- **Wrong time:** It's a feature for next quarter, not this
  one
- **Wrong team:** It's a feature for a different product
- **Out of scope:** It's a feature, not a bug; it's not in
  this product

## The "validation" anti-pattern

A feature is built, then validated. A better pattern:
1. **Validate first:** Build a low-fidelity version
   (prototype, mockup, A/B test)
2. **Build second:** Once validated, build the real version

For a "photo upload" feature:
- Validate: Survey 100 users; do they want it?
- Build: A simple file upload with no editing

For a "AI summaries" feature:
- Validate: Build a prototype; test with 10 users
- Build: The production version

## The "customer development" pattern

The most important data for prioritization is **customer
feedback**:
1. **Talk to customers weekly** (5-10 customer calls per week)
2. **Track feedback** in a CRM (Salesforce, Hubspot, etc.)
3. **Quantify:** How many customers asked for this?
4. **Prioritize:** Top requested features get top priority

A feature requested by 50 customers is more important than a
feature requested by 1 customer with a big voice.

## The "OKR" alignment

Priorities should align with **OKRs** (Objectives + Key
Results):
- **Objective:** A goal (e.g. "Increase user retention")
- **Key Results:** Measurable outcomes (e.g. "Increase 30-day
  retention from 30% to 50%")

A feature that moves a KR is high priority. A feature that
doesn't is low priority.

## Verification
- **Process:** Quarterly review of priorities vs results
- **Live:** Feature usage is tracked; unused features are
  killed
- **Audit:** Annual review of prioritization framework

## Gotchas
- **The framework is not the answer.** RICE, ICE, MoSCoW are
  tools. The product owner's judgment matters.
- **Quantitative ≠ correct.** A RICE score is based on
  estimates; estimates are wrong. Use the score as a guide,
  not a decision.
- **The "what to build" question is not just "what features."**
  Sometimes the answer is "fix the bugs" or "improve the
  performance" or "rewrite the legacy code."
- **Priorities change.** A feature that was high priority
  last quarter may be low priority this quarter. Re-
  evaluate.
- **The "loudest customer" is not the right customer.** Use
  quantitative feedback (surveys, analytics) over qualitative
  (one customer's opinion).
- **The "everything is high priority" trap.** If everything
  is high priority, nothing is. The product owner must
  rank.

## Related
- `feature-flags.md` (validating features in production)
- `feature-flags-best-practices.md`
- `safe-deploy-checklist.md`
- `error-budget-slo.md` (SLOs as priorities)
- RICE: https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/
- ICE: https://www.seanellis.me/blog/ice-scoring-prioritization
- MoSCoW: https://www.atlassian.com/agile/product-management/prioritization
