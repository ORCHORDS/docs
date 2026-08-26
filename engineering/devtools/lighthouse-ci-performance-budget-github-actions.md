# Lighthouse CI Performance Budget in GitHub Actions

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Pages regress silently on Core Web Vitals after otherwise-routine
feature merges. No one notices until a performance audit is run
manually weeks later. LCP climbs from 1.8 s to 4.2 s; CLS jumps from
0.04 to 0.22; the team is not alerted at PR time.

## Context

Lighthouse CI (`@lhci/cli`) runs Lighthouse audits inside CI, stores
results on a persistent server or temporary public storage, and gates
PRs using assertion thresholds or a `budget.json` file. The workflow
described here uses the GitHub Actions LHCI Action, posts a PR comment
with a score table, and enforces budgets on mobile and desktop
configurations separately.

Requires Node.js ≥ 18, a built static site or a running dev server,
and either an LHCI server (self-hosted or lhci.io) or the
`temporary-public-storage` target for ephemeral public links.

## 1. Installing and configuring LHCI

```bash
npm install --save-dev @lhci/cli
```

Create `lighthouserc.js` at the repo root:

```js
// lighthouserc.js
/** @type {import('@lhci/cli').LighthouseRcConfig} */
module.exports = {
  ci: {
    collect: {
      staticDistDir: "./dist",       // or use startServerCommand
      numberOfRuns: 3,
      settings: {
        preset: "desktop",
        throttlingMethod: "simulate",
      },
    },
    assert: {
      assertions: {
        "categories:performance":    ["error", { minScore: 0.85 }],
        "categories:accessibility":  ["warn",  { minScore: 0.90 }],
        "first-contentful-paint":    ["error", { maxNumericValue: 2000 }],
        "largest-contentful-paint":  ["error", { maxNumericValue: 2500 }],
        "cumulative-layout-shift":   ["error", { maxNumericValue: 0.10 }],
        "total-blocking-time":       ["error", { maxNumericValue: 300 }],
        "interactive":               ["warn",  { maxNumericValue: 3800 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
```

For a self-hosted LHCI server swap `upload` to:

```js
upload: {
  target: "lhci",
  serverBaseUrl: "https://lhci.internal.example.com",
  token: process.env.LHCI_TOKEN,
},
```

## 2. GitHub Actions workflow

```yaml
# .github/workflows/lhci.yml
name: Lighthouse CI

on:
  pull_request:
    branches: [main]

jobs:
  lighthouse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Run Lighthouse CI
        uses: treosh/lighthouse-ci-action@v12
        with:
          configPath: ./lighthouserc.js
          uploadArtifacts: true
          temporaryPublicStorage: true
        env:
          LHCI_GITHUB_APP_TOKEN: ${{ secrets.LHCI_GITHUB_APP_TOKEN }}

      - name: Post PR comment
        uses: actions/github-script@v7
        if: github.event_name == 'pull_request'
        with:
          script: |
            const fs = require('fs');
            const manifest = JSON.parse(
              fs.readFileSync('.lighthouseci/manifest.json', 'utf8')
            );
            const r = manifest[0].summary;
            const row = (k, v) =>
              `| ${k} | ${(v * 100).toFixed(0)} |`;
            const body = [
              '## Lighthouse Scores',
              '| Category | Score |',
              '|---|---|',
              row('Performance',   r['categories.performance']),
              row('Accessibility', r['categories.accessibility']),
              row('Best Practices',r['categories.best-practices']),
              row('SEO',           r['categories.seo']),
            ].join('\n');
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              issue_number: context.issue.number,
              body,
            });
```

## 3. budget.json vs assertions in RC config

`budget.json` follows the W3C Performance Budget spec and governs
resource weights, while RC `assertions` govern audit metrics. Use both
together:

```json
// budget.json
[
  {
    "path": "/*",
    "timings": [
      { "metric": "first-contentful-paint", "budget": 1800 },
      { "metric": "largest-contentful-paint", "budget": 2500 },
      { "metric": "cumulative-layout-shift",  "budget": 0.1  }
    ],
    "resourceSizes": [
      { "resourceType": "script",     "budget": 300 },
      { "resourceType": "total",      "budget": 1000 }
    ],
    "resourceCounts": [
      { "resourceType": "third-party", "budget": 10 }
    ]
  }
]
```

Reference the budget from `lighthouserc.js`:

```js
collect: {
  settings: { budgetPath: "./budget.json" },
},
```

## 4. Comparing mobile vs desktop scores

Run two separate collect passes with different settings by using an
array of `collect` objects or two workflow jobs:

```yaml
strategy:
  matrix:
    preset: [mobile, desktop]
steps:
  - name: Run LHCI (${{ matrix.preset }})
    run: |
      npx lhci autorun \
        --collect.settings.preset=${{ matrix.preset }} \
        --collect.numberOfRuns=3
```

Mobile uses the default throttling (3G + CPU 4×); desktop uses
`--throttlingMethod=simulate` with no throttling. Keep separate
thresholds: mobile LCP budget is typically 3000 ms vs 2500 ms desktop.

## Anti-patterns

- Running only one Lighthouse pass (`numberOfRuns: 1`) — metric
  variance (especially TBT) makes single-run results unreliable.
- Asserting on `minScore` only — a score of 0.85 can mask a TBT of
  800 ms if other audits carry the score up.
- Skipping the upload step — without stored results, historical
  regression graphs and PR links are unavailable.
- Using `--chrome-flags="--no-sandbox"` in production CI without also
  setting `--headless=new` — some environments require both flags or
  Chrome fails to start.

## Gotchas

- `treosh/lighthouse-ci-action` requires a GitHub App token (not a
  PAT) to post status checks on commits. Without it, PR checks appear
  as "pending" forever.
- `staticDistDir` does not support SPA client-side routing. Use
  `startServerCommand` with `--serve` or your framework's preview
  server and set `startServerReadyPattern` to wait for it.
- The `temporary-public-storage` target deletes reports after 7 days.
  Use the LHCI server for permanent history and regression detection.
- CLS values of 0 in CI are suspicious — the headless environment
  may not trigger layout shifts that occur during font loading.
  Add `--extra-headers` to force the font cache to miss.

## Verification

```bash
# Local dry-run
npx lhci autorun --config=lighthouserc.js

# Check assertion failures (exit code 1 on error)
echo $?

# View stored manifest
cat .lighthouseci/manifest.json | jq '.[0].summary'
```

## Related

- `web-vitals` library for RUM (real-user measurement) to complement
  lab data from Lighthouse.
- Cloudflare Zaraz or SpeedVitals for continuous RUM reporting.
- `@lhci/server` Helm chart for a self-hosted persistent LHCI server.

## Source URLs (verified 2026-08-17)

https://github.com/GoogleChrome/lighthouse-ci
https://github.com/treosh/lighthouse-ci-action
https://web.dev/articles/vitals
https://developer.chrome.com/docs/lighthouse/performance/performance-scoring
https://github.com/nickvdyck/lighthouse-ci-action
