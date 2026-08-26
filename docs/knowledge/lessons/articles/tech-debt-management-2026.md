# tech-debt-management-2026

**Issue:** Tech debt — Fowler quadrant + 5-step framework
**Date:** 2026-08-09
**Status:** documented

## Symptom
Code is slow. The team complains. New features
take 3 weeks. The CTO asks why. You wish you had
a debt plan.

## Root cause
**Tech debt is invisible until it bites.** Manage it.

**Source:** Sourcegraph + Catio 2026.

## The "tech debt" concept

Tech debt:
- **Shortcut:** Quick solution now
- **Interest:** Future rework cost
- **Type:** Code, architecture, test, docs
- **Cost:** $6T globally (2024 estimate)
- **Analogy:** Loan + interest

The debt compounds.

## The "Fowler quadrant" pattern

For classification:
| | Deliberate | Inadvertent |
|---|---|---|
| **Prudent** | "Ship now, refactor later" | "Now we know how" |
| **Reckless** | "No time for design" | "What's layering?" |

The quadrant is per type.

## The "quadrant response" pattern

For response:
- **Prudent-Deliberate:** Scheduled payoff
- **Prudent-Inadvertent:** Document + refactor
- **Reckless-Deliberate:** Contain + rebuild
- **Reckless-Inadvertent:** Training + cleanup

The response is per quadrant.

## The "5-step framework" pattern

For management:
1. **Inventory:** Live codebase data
2. **Prioritize:** By interest, not size
3. **Allocate:** Standing budget
4. **Automate:** At scale
5. **Track:** Trends, prevent

The 5 are the framework.

## The "inventory" pattern

For inventory:
- **Live:** Queries, not docs
- **Examples:**
  - Legacy HTTP client usages
  - Old framework version services
  - @deprecated calls
- **Tool:** Sourcegraph, CodeQL
- **Update:** Automatic

The inventory is live.

## The "prioritize" pattern

For priority:
- **Interest:** Cost (incidents, drag, security)
- **Churn:** How often code changes
- **Score:** High interest + high churn = top
- **80/20:** Small fraction = most pain

The priority is per impact.

## The "standing budget" pattern

For budget:
- **15-25%:** Of sprint capacity
- **Predictable:** Not heroic
- **Two types:**
  - Planned campaigns
  - Opportunistic (Boy Scout)
- **Why:** Survives roadmap

The budget is defended.

## The "Boy Scout" pattern

For opportunistic:
- **Rule:** Leave the code better
- **Scope:** Sub-day
- **Permission:** Not needed
- **Effect:** Prevents entropy

The scout is the pattern.

## The "automate paydown" pattern

For automation:
- **Bulk refactor:** Codemod
- **CI check:** Block new usage
- **Replace:** Deprecated API
- **Track:** Per file

The automation scales.

## The "code-level signals" pattern

For signals:
- **Complexity:** Cyclomatic
- **Duplication:** DRY violations
- **Coverage:** Test %
- **Deprecated:** Pattern count
- **Trend:** Over time

The signals are tracked.

## The "delivery signals" pattern

For delivery:
- **Lead time:** Commit to prod
- **Change fail rate:** %
- **Rework time:** vs features
- **Business:** Already tracks

The delivery is the truth.

## The "live pattern count" pattern

For count:
- **Query:** Per deprecated pattern
- **Chart:** Over time
- **CI:** Block new usage
- **Goal:** Trend to zero

The count is per pattern.

## The "types of debt" pattern

For types:
- **Code:** Inline, complexity
- **Architecture:** Coupling, layers
- **Test:** Coverage gaps
- **Documentation:** Stale
- **Security:** Vulns
- **Infrastructure:** Manual

The type is per need.

## The "40-20-40 rule" pattern

For effort:
- **40%:** Design + analysis
- **20%:** Coding
- **40%:** Testing + integration
- **Why:** Reduce debt = plan + test

The ratio is per phase.

## The "no inventory" anti-pattern

For no list:
- **Issue:** Can't prioritize
- **Fix:** Live queries

The inventory is required.

## The "no budget" anti-pattern

For no budget:
- **Issue:** Paydown skipped
- **Fix:** Standing 15-25%

The budget is defended.

## The "deprioritize by size" anti-pattern

For big:
- **Issue:** Big = scary
- **Fix:** High interest first

The priority is by interest.

## The "one-time cleanup" anti-pattern

For one-time:
- **Issue:** Re-accumulates
- **Fix:** Standing system

The cleanup is continuous.

## The "no prevention" anti-pattern

For no prevention:
- **Issue:** New debt
- **Fix:** CI blocks

The prevention is the gate.

## The "no measurement" anti-pattern

For no measure:
- **Issue:** Can't improve
- **Fix:** Track over time

The measure is required.

## The "no exec sponsor" anti-pattern

For no exec:
- **Issue:** Budget cut
- **Fix:** Educate + sponsor

The exec is bought in.

## The "tech debt budget" pattern

For budget:
- **15-25% of sprint:** Most teams
- **Dedicated:** Ring-fenced
- **Visible:** Per sprint
- **Reported:** To leadership

The budget is per sprint.

## The "tech debt dashboard" pattern

For dashboard:
- **Live count:** Per pattern
- **Interest:** Per debt
- **Trend:** Over time
- **Sprint:** Burndown

The dashboard is live.

## The "tech debt in PM" pattern

For PM:
- **Same workflow:** As features
- **Acceptance:** Clear
- **Estimation:** Sized
- **Status:** Tracked

The debt is in PM.

## The "coding standards" pattern

For standards:
- **Practical:** Enforceable
- **Reviewed:** Per quarter
- **Updated:** Per tech change
- **Trained:** New joiners

The standards are current.

## The "debt as feature" pattern

For strategic:
- **Sometimes debt is feature:** Ship fast
- **Documented:** With payback plan
- **Tracked:** When paid
- **Not:** Excuse for bad

The strategic is intentional.

## The "debt velocity" pattern

For tracking:
- **Debt / feature ratio:** Per sprint
- **Trend:** Down = good
- **Alert:** When trending up
- **Action:** Investigate

The velocity is tracked.

## The "no rebuild" pattern

For rebuild:
- **Don't:** Full rewrite often fails
- **Do:** Strangler fig pattern
- **Or:** Incremental
- **Avoid:** Big bang

The rebuild is incremental.

## The "tech debt in retros" pattern

For retros:
- **Track:** Per sprint
- **Surface:** In retro
- **Allocate:** Action items
- **Review:** Monthly

The debt is in retro.

## The "tech debt in code review" pattern

For review:
- **Note:** @tech-debt
- **Issue:** Track separately
- **Priority:** Per impact
- **Don't:** Block feature

The review flags debt.

## The "tech debt pricing" pattern

For pricing:
- **Engineer weeks:** Direct
- **Opportunity cost:** Lost features
- **Coordination:** Cross-team
- **Rewrite risk:** Overshoot

The pricing is full.

## The "blast radius" pattern

For impact:
- **Deps:** How many
- **Hot files:** How touched
- **Risk:** Of fix
- **Priority:** Per blast

The radius is per dep.

## The "tech debt checklist" pattern

For checklist:
- [ ] Live inventory (queries)
- [ ] Fowler quadrant classification
- [ ] Prioritize by interest
- [ ] 15-25% sprint budget
- [ ] Boy Scout slice
- [ ] Code-level signals tracked
- [ ] Delivery signals tracked
- [ ] Trend over time
- [ ] CI blocks new debt
- [ ] Quarterly exec review
- [ ] In PM tool

The checklist is 11.

## Verification
- **Test:** Inventory live
- **Test:** Budget spent
- **Test:** Trend down
- **Test:** CI blocks
- **Audit:** Quarterly

## Gotchas
- **The "no budget" anti-pattern.** 15-25%.
- **The "no prevention" anti-pattern.** CI blocks.
- **The "one-time" anti-pattern.** Continuous.

## Related
- `lessons/scope-discipline.md`
- `lessons/lazy-fail-discoveries.md`
- `lessons/code-review-best-practices.md`
- `issues/dora-metrics.md`
- `patterns/safe-deploy-checklist.md`
- Sourcegraph: https://sourcegraph.com/blog/technical-debt-management
- Monday: https://monday.com/blog/rnd/technical-debt/
- Catio: https://www.catio.tech/blog/reducing-technical-debt
