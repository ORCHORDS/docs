# performance-regression-gates-ci

**Issue:** A dependency bump adds 40KB to the bundle; a "harmless" N+1 refactor adds 300ms to p95; neither breaks any functional test, so both ship. Three weeks later, dashboards show Core Web Vitals degrading and nobody can name the commit that did it. Performance regressed like functionality regresses — one merge at a time — so it needs what functionality has: a CI gate that fails the PR that crosses a budget. This article covers designing performance gates that actually block regressions without drowning the team in noise, informed by web.dev's performance-budgets-in-build guidance, the Lighthouse CI project (assertions, budgets, `budget.json`), and current bundle-size tooling.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing what to gate

1. **Gate leading indicators you control directly, not aggregate scores.** Bundle bytes per entry point, individual asset sizes, number of blocking requests, and API p95/p99 for critical endpoints are mechanically attributable to a diff. Aggregate scores (Lighthouse performance score, Total Blocking Time) move with network conditions and test-runner variance; use them as tracked trends, and gate on the deterministic metrics — this is the web.dev position on budgets in build tooling.
2. **Separate static budgets (deterministic, gate every PR) from runtime budgets (noisy, gate with variance handling).** Static: gzip sizes of JS/CSS artifacts, image weights, font counts — same input, same number, perfect for hard fails. Runtime: Lighthouse metrics, load timings — sample multiple runs, compare distributions, and use tolerance bands (Lighthouse CI's `numberOfRuns` plus assert `aggregationMethod: median`/`optimistic` exists precisely for this).
3. **Budget the user-visible critical paths, not the whole app uniformly.** A 40KB increase on the marketing entry point is noise; 40KB on the checkout bundle is a regression. Per-route budgets concentrate the team's attention where latency costs money and let cold paths grow freely within reason.
4. **Count startup cost as a budgeted artifact: cold-start duration for functions/containers.** On this repo's Cloudflare Workers, a bundle that pulls in heavy dependencies inflates cold start; budget parse/execute time per worker (`wrangler` dev timings or a platform-reported metric) just like bundle bytes. For latency gates on stateless endpoints, the harness mechanics live in `performance-testing-k6.md` — this article is where its thresholds become CI policy.

## Writing the assertions

1. **Encode budgets as config checked into the repo, applied identically locally and in CI.** Lighthouse CI's `lighthouserc` assertions and `budget.json` (resource-size budgets the browser tooling also respects), or `bundlesize`/`size-limit` config in `package.json` — one source of truth, run as a normal test step (`pnpm test:perf`), never a CI-only surprise.
2. **Fail on absolute thresholds; warn on trend deltas.** "entry.checkout.js gzip ≤ 180KB" is a hard fail; "+8KB vs main" is a warning shown on the PR. Absolute thresholds catch slow drift; delta warnings catch the one-off big adds and give reviewers the number in context without blocking legitimate work.
3. **Assert per-asset and per-type budgets, not just totals.** A total-JS budget of 500KB lets an import rewrite silently shift 100KB from the deferred chunk into the initial one with the total unchanged; per-entry budgets (initial JS, total JS, images, fonts) make the shift visible.
4. **Use median-of-N for any runtime assertion and document the variance.** Lighthouse CI runs the audit multiple times (`numberOfRuns: 3–5`) and asserts on a chosen aggregation because single-run TBT/LCP swings by double-digit percents on shared CI runners; a gate without variance handling trains the team to hit re-run, which is the retry antipattern from `test-retry-strategies.md` wearing a perf costume.
5. **Include a composition guard: dependency-count and duplicate-package budgets.** `size-limit`/bundle-analyzer output showing the same library at two versions, or a new 60KB transitive dep, explains size jumps before a human has to spelunk; fail on duplicate versions of core deps (React, lodash) outright.

## Making the gate survive contact with the team

1. **Set initial budgets from measurement, not aspiration.** Run the gate on main for a week, take the current values, add 5–10% headroom, and ship those as the starting budgets (the standard advice in Lighthouse CI adoption guides: run locally first, set realistic budgets, then wire the pipeline). Aspirational budgets fail every PR on day one and get deleted by day three.
2. **Ratchet downward deliberately.** When optimization work lands and the new normal is well under budget, tighten the budget in the same PR — the gate is a ratchet that only turns one way except through explicit, reviewed budget-change commits. Budget files changing should be as visible in review as dependency changes.
3. **Give the failure an owner-shaped message.** "checkout.js is 192KB, budget 180KB (+12KB). Biggest additions: lodash.get 14KB, date-fns 9KB. Try: dynamic import for the date picker." Tools like size-limit print per-package deltas — wire that output into the failure so the fix path is in the error, not in a wiki.
4. **Never auto-bypass with `continue-on-error` or a blanket allowlist.** Every escape hatch must be per-PR, explicit (a label or config edit in the diff), and time-boxed by convention; a performance gate with a silent permanent bypass is a dashboard, not a gate.
5. **Track the trend where reviewers see it.** Lighthouse CI's server (or a GitHub check with historical data) turns the gate into a visible slope; regressions that squeak under budget still show as stair-steps on the chart and get caught in weekly triage before they compound into a budget bump.

## Extending beyond the frontend bundle

1. **Diff-based benchmarking for compute-heavy code.** For parsers, routers, and data pipelines, run a micro-benchmark suite on the PR and on main in the same runner image, compare medians, and fail on >X% regression — the statistical discipline from `random-seed-control-deterministic-tests.md` applies (fix seeds, many iterations, compare distributions, not single runs).
2. **Gate memory footprint for long-lived processes.** Assert RSS after a warmup + fixed workload loop stays within a band (the short form of `soak-endurance-testing-methodology.md`); catches the "one small closure per request" leak class at PR time instead of at 3am.
3. **Make the same budget consumable at deploy time.** The `budget.json`/assertion config that fails CI can also feed deploy-time checks (CDN layer limits, alert thresholds), so the numbers teams reason about in PRs are the numbers production alerts on — one definition of "too big," not two.
4. **Re-baseline on environment changes, explicitly.** Runner upgrades, Node version bumps, and browser version changes shift absolute numbers; when the environment changes, re-measure main, and commit the new baseline with a message naming the environment change — otherwise the gate fails mysteriously on a no-code-change PR and trust erodes. And keep the gate's runtime honest: cache dependencies and unchanged-route audits, because a perf gate that adds 10 minutes to CI gets disabled regardless of its value.

## Related

- `lighthouse-ci-integration.md` — Lighthouse CI setup mechanics this article's policy builds on
- `jest-coverage-thresholds.md` — the ratcheting-gate pattern applied to coverage
- `performance-testing-k6.md` — generating the latency numbers the gates assert on
- `soak-endurance-testing-methodology.md` — the long-duration budgets CI gates can't cover
