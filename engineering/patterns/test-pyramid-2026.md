# test-pyramid-2026

**Issue:** Test pyramid — unit / integration / E2E
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 80% E2E tests. CI takes 1 hour. Tests are
flaky. Bugs slip through. You wish you had a pyramid.

## Root cause
**Without pyramid, ice cream cone.** Use layers.

**Source:** SoftwareTestPilot + Autonoma 2026.

## The "test pyramid" concept

Test pyramid (Mike Cohn):
- **Base:** Unit (many, fast, cheap)
- **Middle:** Integration (some)
- **Top:** E2E (few, slow)

The shape is the allocation.

## The "70/20/10" pattern

For allocation:
- **70%:** Unit
- **20%:** Integration
- **10%:** E2E

The split is the rule.

## The "AI era shift" pattern

For AI-generated code:
- **Old:** 70/20/10
- **New:** 60/25/15 or 50/30/20
- **Why:** AI passes unit, fails integration
- **E2E:** More important for AI

The ratio shifts.

## The "unit test" pattern

For unit:
- **What:** Single function/class
- **Speed:** Milliseconds
- **Mocked:** All deps
- **Count:** 1000s
- **When:** Every commit

The unit is the base.

## The "integration test" pattern

For integration:
- **What:** Components + DB/queue
- **Speed:** Seconds
- **Real deps:** DB, queue
- **Count:** 100s
- **When:** Every PR

The integration is middle.

## The "E2E test" pattern

For E2E:
- **What:** Full user flow
- **Speed:** Minutes
- **Real:** Full stack
- **Count:** 10-50
- **When:** Nightly + pre-release

The E2E is the apex.

## The "comparison" pattern

For layers:
| Dim | Unit | Integration | E2E |
|---|---|---|---|
| Speed | ms | sec | 10-60s |
| Confidence | Low | Medium | High |
| Maintenance | Low | Medium | High |
| Debug signal | Excellent | Good | Poor |
| Setup | Minimal | Moderate | High |
| Parallel | Excellent | Good | Limited |

The layer is per need.

## The "what to test where" pattern

For test placement:
- **Pure function:** Unit
- **DB query:** Integration
- **Service boundary:** Integration
- **API contract:** Integration / Contract
- **Login flow:** E2E
- **Checkout:** E2E
- **Multi-step form:** E2E

The placement is per behavior.

## The "tool selection" pattern

For tools:
| Layer | Tools |
|---|---|
| Unit | Jest, Vitest, JUnit, pytest |
| Integration | Testcontainers, Supertest, Pact, WireMock |
| E2E | Playwright, Cypress, Selenium |

The tool is per layer.

## The "ice cream cone" anti-pattern

For cone:
- **Issue:** 80% E2E
- **Result:** Slow, flaky
- **Fix:** Push logic to unit

The cone is broken.

## The "no E2E" anti-pattern

For no E2E:
- **Issue:** Missed user flow bugs
- **Fix:** Top 5-10 critical journeys

The E2E is required.

## The "E2E for everything" anti-pattern

For too much E2E:
- **Issue:** Slow CI, flaky
- **Fix:** Push down to integration

The E2E is minimal.

## The "test containers" pattern

For integration:
```typescript
import { PostgreSqlContainer } from "@testcontainers/postgresql";

const container = await new PostgreSqlContainer()
  .start();
const dbUrl = container.getConnectionUri();
// Run real DB queries
```

The container is real.

## The "contract test" pattern

For service boundary:
- **Tool:** Pact
- **Consumer:** Defines expected
- **Provider:** Verifies
- **Result:** Catches breaking

The contract is per service.

## The "Pact broker" pattern

For sharing:
- **Pact Broker:** Stores pacts
- **Consumer:** Publishes
- **Provider:** Verifies
- **CI:** Both run

The broker is shared.

## The "Playwright vs Cypress" pattern

For E2E:
- **Playwright:** Multi-browser, fast
- **Cypress:** Component + E2E
- **Choose:** Playwright for cross-browser
- **Or:** Cypress for component-driven

The choice is per need.

## The "Pyramid audit" pattern

For audit:
- **Count tests** per layer
- **If E2E > 20%:** Cone
- **If unit < 50%:** No base
- **If integration < 10%:** No contracts

The audit is per team.

## The "push down" pattern

For refactor:
- **Logic in E2E:** Move to unit
- **API in E2E:** Move to integration
- **Keep:** Critical journeys

The push is gradual.

## The "make visible" pattern

For metrics:
- **Report:** Per layer
- **Sprint review:** Show pyramid
- **Track:** Trend
- **Goal:** Healthier shape

The pyramid is visible.

## The "test pyramid for AI" pattern

For AI code:
- **More E2E:** AI misses user flows
- **More integration:** AI misses boundaries
- **Less unit:** AI passes
- **Ratio:** 50/30/20

The ratio is AI-aware.

## The "unit test quality" pattern

For unit:
- **AAA:** Arrange, Act, Assert
- **One assertion:** Per test (mostly)
- **No logic:** In tests
- **Names:** Behavior, not method
- **Coverage:** Branch, not line

The quality is high.

## The "integration patterns" pattern

For patterns:
- **Testcontainers:** Real DB
- **WireMock:** External API
- **LocalStack:** AWS services
- **Docker compose:** Multi-service

The pattern is per need.

## The "test data" pattern

For data:
- **Fixtures:** Per test
- **Factories:** Reusable
- **Truncate:** Between tests
- **No global state:** Per test
- **Realistic:** Production-like

The data is fresh.

## The "test isolation" pattern

For isolation:
- **Per test:** Fresh DB
- **No order dependency**
- **No shared state**
- **Truncate:** Between
- **Speed:** Important

The isolation is strict.

## The "flaky test" pattern

For flakiness:
- **Identify:** Quarantine + retry
- **Fix:** Or remove
- **Quarantine:** Allow merge
- **Track:** Per test
- **Budget:** 0 flaky

The flakiness is tracked.

## The "test in CI" pattern

For CI:
- **Commit:** Unit
- **PR:** + Integration
- **Merge:** + Contract
- **Nightly:** Full + E2E
- **Pre-release:** Smoke

The CI is per stage.

## The "no unit" anti-pattern

For no unit:
- **Issue:** Slow tests
- **Fix:** Push logic to unit

The unit is required.

## The "test all in E2E" anti-pattern

For all E2E:
- **Issue:** 1h CI
- **Fix:** Pyramid

The pyramid is required.

## The "no contract" anti-pattern

For no contract:
- **Issue:** Service breaks other
- **Fix:** Pact

The contract is per service.

## The "flaky ignored" anti-pattern

For flakiness:
- **Issue:** Tests ignored
- **Fix:** Quarantine + fix

The flakiness is owned.

## The "test pyramid checklist" pattern

For checklist:
- [ ] 70% unit (60% for AI)
- [ ] 20% integration (25% for AI)
- [ ] 10% E2E (15% for AI)
- [ ] Testcontainers for DB
- [ ] Pact for contracts
- [ ] Playwright for E2E
- [ ] Per-commit: unit
- [ ] Per-PR: + integration
- [ ] Nightly: full
- [ ] Flake budget 0

The checklist is 10.

## Verification
- **Test:** Pyramid shape healthy
- **Test:** Unit < 5 min
- **Test:** Integration < 15 min
- **Test:** E2E < 30 min
- **Test:** No flaky
- **Audit:** Quarterly

## Gotchas
- **The "ice cream cone" anti-pattern.** Pyramid.
- **The "no E2E" anti-pattern.** Critical only.
- **The "flaky ignored" anti-pattern.** Quarantine.

## Related
- `patterns/chaos-engineering-deep-dive.md`
- `deploy/canary-deployments.md`
- `patterns/safe-deploy-checklist.md`
- `issues/dora-metrics.md`
- SoftwareTestPilot: https://softwaretestpilot.com/blog/manual-testing/test-pyramid-explained
- Autonoma: https://getautonoma.com/blog/unit-vs-integration-vs-e2e-testing
- Imperialis: https://imperialis.tech/en/blog/api-testing-strategies-unit-contract-2026
