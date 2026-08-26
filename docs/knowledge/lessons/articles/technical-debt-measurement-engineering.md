# Technical Debt Measurement for Engineering Teams

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Engineering leadership suspects the team is slower than it was six months ago
but has no data to confirm it. Developers say "everything takes twice as long
because of the codebase" but cannot quantify it. A Cloudflare Workers bundle
that once deployed in 800ms now takes 14 seconds and nobody tracked the
inflection point. Mobile crash-free rate has drifted from 99.8% to 99.1%
without a specific incident to blame. Tech debt is real and costly but
invisible to product managers and executives because it has no unit.

## Context

Technical debt is the accumulation of design decisions, deferred maintenance,
and architectural compromises that make future changes slower and riskier.
Unlike financial debt, engineering debt has no invoice; it manifests as
increased cycle time, higher defect rates, and growing cognitive load. Without
measurement, debt management becomes a political argument between product and
engineering rather than a data-driven prioritization problem. The techniques
below are appropriate for a Cloudflare-native startup with Workers, D1, KV,
and a mobile client surface.

## Debt quantification methods

### 1. Code quality proxies (static analysis)

Static analysis tools produce proxies that correlate with maintenance cost:

```
Metric                   What it predicts          Tooling
─────────────────────────────────────────────────────────────────────
Cyclomatic complexity     Defect probability         ESLint complexity,
(per function)           Cognitive load             SonarQube
                         (>10 = high risk)

File churn rate           Files changed most often   git log --stat
(commits per file/month)  are highest debt targets   + analysis script

Code duplication %        Regression surface area    jscpd, SonarQube
                         Copy-paste debt

Dependency age            Supply chain risk,         npm audit,
(days since release)      upgrade cost               Renovate summary

Test coverage %           Change safety              Vitest --coverage
(per module)             gap indicator
```

Pull these monthly and track trends. A rising cyclomatic complexity trend
in your Workers source signals debt accumulation ahead of defect rate
increases.

### 2. DORA metrics as delivery-level debt signal

DORA metrics measure the output cost of accumulated debt:

```
Debt signal                     DORA metric that degrades
──────────────────────────────────────────────────────────────────────
Slow, manual deployment steps   Lead Time for Changes increases
Fear of deploying               Deployment Frequency decreases
Fragile integration points      Change Failure Rate increases
Poor observability              MTTR increases

Track DORA trends quarterly. A degrading lead time trend alongside
stable team size is a quantitative debt signal readable to
non-engineers.
```

The link between debt and DORA is not always immediate: a codebase
can accumulate debt for 6–12 months before DORA metrics visibly degrade.
Use static analysis metrics as the early-warning layer and DORA as
the business-impact layer.

### 3. Cloudflare Workers build size tracking

Bundle size is a first-class debt metric on Workers because:

- Workers have a 10 MB compressed script size limit (free: 1 MB).
- Cold start time correlates with bundle size — large bundles mean
  slower edge cold starts for mobile users on the first request.
- Untracked bundle growth signals dead code, duplicated dependencies,
  and missing tree-shaking.

Track bundle size in CI:

```yaml
# .github/workflows/bundle-size.yml
name: Workers bundle size

on: [push, pull_request]

jobs:
  bundle-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx wrangler build 2>&1 | tee build.log
      - name: Extract and record bundle size
        run: |
          SIZE=$(stat -c%s dist/worker.js 2>/dev/null || \
                 stat -f%z dist/worker.js)
          echo "BUNDLE_SIZE_BYTES=$SIZE" >> "$GITHUB_OUTPUT"
          echo "Bundle size: $SIZE bytes"
          # Fail if over 900 KB compressed (10% headroom below 1 MB free limit)
          if [ "$SIZE" -gt 921600 ]; then
            echo "ERROR: bundle size exceeds 900 KB threshold"
            exit 1
          fi
      - name: Store size in D1 (optional trend tracking)
        if: github.ref == 'refs/heads/main'
        run: |
          curl -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"sql\": \"INSERT INTO build_metrics (commit_sha, bundle_bytes, built_at) VALUES ('$GITHUB_SHA', $SIZE, unixepoch('now'))\"}"
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          D1_DB_ID: ${{ secrets.D1_BUILD_METRICS_DB_ID }}
```

Query D1 to visualize the trend:

```sql
SELECT
  substr(commit_sha, 1, 8) AS sha,
  bundle_bytes,
  ROUND(bundle_bytes / 1024.0, 1) AS kb,
  datetime(built_at, 'unixepoch') AS built_at
FROM build_metrics
ORDER BY built_at DESC
LIMIT 30;
```

A bundle that grew 40% in 30 days with no intentional feature additions
is a quantified debt signal with an attached PR history.

### 4. Mobile performance debt

Mobile debt manifests differently from server-side debt:

```
Mobile debt category         How to measure
──────────────────────────────────────────────────────────────────────────
App startup time             Time to interactive (TTI) — measure with
(time to interactive)        Flipper, Perfetto, or instruments.
                             Track p50 and p95 per OS version.

Binary size growth           iOS: IPA size in App Store Connect.
                             Android: APK/AAB size in Play Console.
                             Both: track per release in a spreadsheet
                             or D1 table, same as bundle size above.

JavaScript bundle size       React Native: metro bundler output size.
(React Native)               Track per build; set a CI threshold.

Crash-free rate trend        Firebase Crashlytics or Sentry.
                             Deteriorating crash-free rate is a
                             leading debt indicator, especially if
                             no specific incident caused it.

Frame drop rate              Jank = JS thread blocking old code.
(JS frame budget)            > 5% dropped frames is actionable.

Network retry rate           A rising retry rate signals degraded
(from mobile telemetry)      backend reliability or client-side
                             error-handling debt.
```

Crash-free rate is particularly important: a drop from 99.8% to 99.1%
sounds small but means 7x more crashes per user session. Track and
trend it; set a policy that 99.2% triggers a debt sprint.

### 5. Cognitive load proxy: time-to-onboard

A proxy for architectural complexity debt is how long it takes a new
engineer to make their first production contribution:

```
Week 1: read codebase, set up local dev with Wrangler
Week 2: first PR merged to a non-critical Worker
Week 3: first change to a D1 schema migration
Week 4: first production deploy of a mobile feature

Baseline this for each new hire. If it is growing quarter over quarter,
the codebase is becoming harder to navigate — structural debt, not
team-size scaling.
```

## Debt prioritization after measurement

Measurement without prioritization produces reports nobody acts on.
Use a simple impact-effort matrix applied to measured debt items:

```
Impact (delivery slowdown or defect risk)
         High │ Do next sprint    │  Do this quarter
              │                   │
         Low  │ Backlog/accept    │  Automate or skip
              └───────────────────┴──────────────────
                   Low effort          High effort
```

Debt with a measured DORA impact (rising lead time, higher CFR) goes
into "Do next sprint." Debt with static analysis signals only but no
DORA impact goes to "Do this quarter." Debt with low impact and high
effort is a backlog item or accepted until the surrounding code is
touched for another reason.

## Anti-patterns

- **Measuring debt only with story points** — story points estimate
  effort, not debt. A story that takes 3x longer than estimated may
  reflect debt but the point is assigned to the feature, not the debt.
  Use cycle time and lead time instead.
- **Tech debt "sprints"** — designating one sprint per quarter for
  debt reduction without ongoing measurement produces cleanup theater.
  Debt accumulates in the 11 other weeks faster than one sprint removes it.
- **Bundle size monitoring only at threshold breach** — by the time
  a bundle hits the 1 MB Workers free-tier limit, the debt is already
  large. Track the trend starting from the first build.
- **Treating all debt as equal** — debt in a hot code path (high churn,
  high complexity) is 10x more costly than debt in a cold path. Weight
  by file churn rate, not by line count.
- **Using debt as cover for missing features** — "we need a debt sprint"
  is sometimes accurate and sometimes a team avoiding hard product work.
  Data — DORA trends, complexity metrics — separates the two.

## Gotchas

- **Workers build output format varies** — `wrangler build` may output
  to `.wrangler/` or `dist/` depending on version and `wrangler.toml`
  config. Test the stat path in CI before relying on it.
- **D1 free-tier for build metrics** — the build metrics D1 database
  is operational metadata; it does not need to live in the production
  D1 instance. Create a separate D1 database for CI/CD telemetry to
  avoid polluting production row counts.
- **Crash-free rate denominator** — some SDKs count crash-free
  sessions, others count crash-free users. Make sure you are comparing
  the same denominator over time when trending.
- **Static analysis thresholds require calibration** — cyclomatic
  complexity > 10 is a widely-used heuristic but Workers event handler
  functions with complex routing logic may legitimately exceed it.
  Set project-specific thresholds and document the rationale.

## Verification

- Bundle size is tracked per commit on the main branch in D1 or a
  time-series store, not just at deploy time.
- CI fails if Workers bundle size exceeds the defined threshold.
- DORA metrics (Lead Time, Deployment Frequency, CFR, MTTR) are
  reviewed quarterly and trended over at least two quarters.
- Mobile crash-free rate is tracked per release with a defined alert
  threshold (e.g., < 99.2% triggers investigation).
- A debt prioritization meeting is held each quarter using measured
  data, not team opinion.
- New-hire time-to-first-production-contribution is tracked per
  cohort as a cognitive load proxy.

## Related

- `documentation/docs/policies/lessons/dora-metrics-engineering-measurement.md`
- `documentation/docs/policies/lessons/technical-debt-measurement-prioritization.md`
- `documentation/docs/policies/lessons/over-engineering-is-a-form-of-tech-debt.md`
- `documentation/docs/policies/lessons/feature-flag-lifecycle-management.md`
- `documentation/docs/policies/lessons/ci-matrix-rows-need-evidence-owners.md`

## Source URLs (verified 2026-08-22)

- DORA 2024 State of DevOps Report — https://dora.dev/research/2024/dora-report/
- Cloudflare Workers size limits — https://developers.cloudflare.com/workers/platform/limits/
- SonarQube cognitive complexity — https://docs.sonarsource.com/sonarqube/latest/user-guide/metric-definitions/
- Google Code Health Guide — https://testing.googleblog.com/2017/04/code-health-googles-internal-code.html
- Martin Fowler on Technical Debt — https://martinfowler.com/bliki/TechnicalDebt.html
