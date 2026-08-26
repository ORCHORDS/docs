# Lighthouse CI Performance Budget Enforcement

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A team ships a new marketing page and performance regresses: LCP goes from 1.8 s to 3.4 s, TBT from 120 ms to 680 ms.  Nobody notices until a customer complains two weeks later.  The team had a `performance-budget.json` file committed to the repo, but it was never wired into CI, so PRs were merged with no automated gate.  The Lighthouse score shown in PR previews was from a lab run in a non-production environment with no throttling, making regressions invisible.  **Lighthouse CI (LHCI)** solves this by running Lighthouse on every commit against realistic conditions and blocking the PR when budgets are exceeded.

## Context

**Lighthouse CI** is the official Lighthouse automation toolchain from the Chrome team.  It wraps Lighthouse with:

- **LHCI Server** — a storage server for historical Lighthouse reports (self-hosted or LHCI cloud)
- **LHCI Autorun** — a CLI that runs Lighthouse, uploads to the server, and asserts against budgets
- **Budget assertions** — declarative thresholds on any Lighthouse audit metric

Integration points:

| Mechanism | When to use |
|-----------|-------------|
| `budgets.json` file | Set resource size budgets (JS, CSS, image bytes) |
| `lighthouserc.js` assertions | Set score thresholds and metric ceilings (LCP, TBT, CLS) |
| LHCI server | Historical comparison and PR diff comments |
| GitHub Actions / GitLab CI | Block merge when assertions fail |

The key difference from a one-off `lighthouse` CLI run is that LHCI runs **multiple samples** (typically 3–5) and reports median values, reducing variance from single-run noise.  This makes budget assertions reliable enough to use as a merge gate.

## Section 1 — Installing and Configuring LHCI

```bash
# Install LHCI CLI
npm install --save-dev @lhci/cli

# Or globally
npm install -g @lhci/cli
```

Root-level `lighthouserc.js`:

```javascript
// lighthouserc.js
module.exports = {
  ci: {
    collect: {
      // URL(s) to audit — use the built-in static server or a real staging URL
      url: [
        'http://localhost:3000/',
        'http://localhost:3000/products',
        'http://localhost:3000/checkout',
      ],
      // Run the static server (Lighthouse CI serves build output)
      staticDistDir: './dist',  // omit if using startServerCommand

      // OR start the real server
      // startServerCommand: 'npm run start:prod',
      // startServerReadyPattern: 'Listening on port 3000',

      numberOfRuns: 3,          // 3 runs → median values; use 5 for tighter budgets
      settings: {
        // Throttle to simulate real-world mobile conditions
        throttlingMethod:          'simulate',
        throttling: {
          rttMs:                   40,    // 40 ms base RTT (Fast 3G equivalent)
          throughputKbps:          10_240, // 10 Mbps (typical mobile LTE)
          cpuSlowdownMultiplier:   4,     // 4× CPU slowdown (mid-range Android)
          requestLatencyMs:        0,
          downloadThroughputKbps:  10_240,
          uploadThroughputKbps:    10_240,
        },
        formFactor:     'mobile',
        screenEmulation: {
          mobile:            true,
          width:             375,
          height:            812,
          deviceScaleFactor: 2,
        },
        // Disable PWA audits to avoid false failures in CI
        onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
      },
    },

    assert: {
      // Inherit Chrome's preset, then override specific audits
      preset: 'lighthouse:no-pwa',

      assertions: {
        // Core Web Vitals — use 'warn' for informational, 'error' to block CI
        'largest-contentful-paint':   ['error', { maxNumericValue: 2500 }],
        'total-blocking-time':         ['error', { maxNumericValue: 300 }],
        'cumulative-layout-shift':     ['error', { maxNumericValue: 0.1 }],
        'interactive':                 ['error', { maxNumericValue: 3800 }],
        'first-contentful-paint':      ['warn',  { maxNumericValue: 1800 }],
        'speed-index':                 ['warn',  { maxNumericValue: 3400 }],

        // Lighthouse score thresholds
        'categories:performance':      ['error', { minScore: 0.75 }],
        'categories:accessibility':    ['error', { minScore: 0.90 }],

        // Render-blocking resources
        'render-blocking-resources':   ['warn',  { maxLength: 0 }],

        // Third-party scripts
        'third-party-summary':         ['warn',  { maxNumericValue: 250 }],
      },
    },

    upload: {
      // Upload to LHCI server for historical comparison
      // Set LHCI_TOKEN env var in CI
      target: 'lhci',
      serverBaseUrl: 'https://lhci.your-domain.com',
    },
  },
};
```

## Section 2 — Resource Budget File

The `budgets.json` file (referenced from `lighthouserc.js` or used standalone) enforces **byte budgets** per resource type:

```json
[
  {
    "path": "/*",
    "resourceCounts": [
      { "resourceType": "script",     "budget": 8  },
      { "resourceType": "stylesheet", "budget": 4  },
      { "resourceType": "image",      "budget": 20 },
      { "resourceType": "font",       "budget": 3  },
      { "resourceType": "third-party","budget": 5  }
    ],
    "resourceSizes": [
      { "resourceType": "script",     "budget": 300 },
      { "resourceType": "stylesheet", "budget": 50  },
      { "resourceType": "image",      "budget": 500 },
      { "resourceType": "font",       "budget": 80  },
      { "resourceType": "document",   "budget": 30  },
      { "resourceType": "total",      "budget": 1000 }
    ],
    "timings": [
      { "metric": "interactive",                "budget": 3800 },
      { "metric": "first-contentful-paint",     "budget": 1800 },
      { "metric": "largest-contentful-paint",   "budget": 2500 },
      { "metric": "total-blocking-time",        "budget": 300  },
      { "metric": "cumulative-layout-shift",    "budget": 0.1  }
    ]
  },
  {
    "path": "/checkout",
    "resourceSizes": [
      { "resourceType": "script",  "budget": 250 },
      { "resourceType": "total",   "budget": 800 }
    ]
  }
]
```

Reference the budget file from `lighthouserc.js`:

```javascript
// In the assert section of lighthouserc.js
assert: {
  budgetsFile: './budgets.json',
  assertions: {
    // Additional assertions beyond the budget file
    'uses-long-cache-ttl': ['warn', { maxLength: 0 }],
  },
},
```

## Section 3 — GitHub Actions Integration

```yaml
# .github/workflows/lighthouse-ci.yml
name: Lighthouse CI

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  lhci:
    name: Lighthouse Audit
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build production bundle
        run: npm run build
        env:
          NODE_ENV: production

      - name: Run Lighthouse CI
        run: npx lhci autorun
        env:
          LHCI_GITHUB_APP_TOKEN: ${{ secrets.LHCI_GITHUB_APP_TOKEN }}
          LHCI_TOKEN:            ${{ secrets.LHCI_TOKEN }}

      - name: Upload LHCI reports as artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: lighthouse-reports
          path: .lighthouseci/
          retention-days: 14
```

The `LHCI_GITHUB_APP_TOKEN` enables LHCI to post status check results directly to the PR (green check / red X per URL and per category), visible inline in the GitHub PR UI.

## Section 4 — Ratcheting Budgets: Never Regress

A budget that never tightens creates a ceiling, not a ratchet.  Use LHCI's **comparison mode** with ratcheting assertions to block any regression, even if the absolute budget is not exceeded:

```javascript
// lighthouserc.js — ratchet mode
assert: {
  assertions: {
    // Block CI if LCP is worse than the median of the last 3 successful runs
    'largest-contentful-paint': [
      'error',
      {
        maxNumericValue: 2500,  // absolute ceiling
        aggregationMethod: 'median-run',
        // Regression threshold: fail if this run's median is 10% worse than
        // the LHCI server's baseline for this branch
        // (Requires LHCI server + upload.target: 'lhci')
      },
    ],
    'total-blocking-time': ['error', { maxNumericValue: 300 }],
  },
},

upload: {
  target:        'lhci',
  serverBaseUrl: 'https://lhci.your-domain.com',
  // LHCI server stores baseline per branch; assertions compare against baseline
  // When upload is configured, LHCI autorun adds --assert-regression automatically
},
```

Additionally, use a `performance-budget-updater` script to tighten budgets automatically when a PR improves performance:

```javascript
// scripts/tighten-budgets.js
// Run after a successful merge to main that improved metrics.
// Reads the latest LHCI report and tightens budgets by 5% if metrics improved.
const fs   = require('fs');
const path = require('path');

const reportsDir = '.lighthouseci';
const budgetFile = 'budgets.json';

const reports = fs.readdirSync(reportsDir)
  .filter(f => f.endsWith('.json') && f.startsWith('lhr-'))
  .map(f => JSON.parse(fs.readFileSync(path.join(reportsDir, f), 'utf8')));

if (!reports.length) {
  console.log('No LHCI reports found');
  process.exit(0);
}

const lcp = reports.map(r =>
  r.audits['largest-contentful-paint']?.numericValue ?? Infinity
);
const medianLcp = lcp.sort((a, b) => a - b)[Math.floor(lcp.length / 2)];

const budgets = JSON.parse(fs.readFileSync(budgetFile, 'utf8'));
const lcpBudget = budgets[0]?.timings?.find(t => t.metric === 'largest-contentful-paint');

if (lcpBudget && medianLcp < lcpBudget.budget * 0.9) {
  // Actual is 10%+ better than budget — tighten budget to actual + 5% buffer
  lcpBudget.budget = Math.ceil(medianLcp * 1.05);
  fs.writeFileSync(budgetFile, JSON.stringify(budgets, null, 2));
  console.log(`Tightened LCP budget to ${lcpBudget.budget} ms`);
}
```

Run this script as part of a post-merge workflow and commit the updated `budgets.json` automatically.

## Anti-patterns

- **Running LHCI on the dev server** — the dev server includes HMR, unminified JS, and source maps.  Always build a production bundle (`NODE_ENV=production`) before LHCI runs.
- **Using `numberOfRuns: 1`** — a single Lighthouse run has high variance (±15% on LCP is common).  Use at least 3 runs; use 5 for budgets tight enough to catch 10% regressions.
- **Setting all assertions to `warn` instead of `error`** — `warn` does not fail the CI job.  Use `error` for metrics that directly block the user experience (LCP, TBT, CLS); use `warn` for informational audits.
- **Not throttling CPU and network** — running Lighthouse without throttling produces scores from a fast CI machine that never reflect a real user's device.  Always set `cpuSlowdownMultiplier: 4` for mobile and `rttMs: 40` for network.
- **Checking in LHCI report JSON files** — `.lighthouseci/*.json` files can be several MB each.  Add `.lighthouseci/` to `.gitignore` and upload them as CI artifacts instead.

## Gotchas

- LHCI `startServerCommand` does not wait for the server to be fully ready by default — use `startServerReadyPattern` (a regex matched against the server's stdout) to avoid race conditions where Lighthouse starts before the server is listening.
- Lighthouse audit results for the same page can vary significantly between runs even with the same configuration, due to garbage collection timing, V8 JIT state, and OS scheduling.  Accept that budgets must include a buffer of 10–20% above your measured median.
- The LHCI server requires a persistent database (SQLite by default, PostgreSQL for production).  Use the managed LHCI cloud (https://lhci.appspot.com) or self-host behind Cloudflare Workers + D1 for serverless storage.
- Lighthouse CI does not measure **field data** (real user metrics).  It is a synthetic tool.  Use `pagespeed-insights-api.md` or CrUX for field data validation alongside LHCI for synthetic gating.
- The `budgets.json` format for `resourceSizes` uses **KiloBytes** (1 KB = 1000 bytes), not KibiBytes.  A budget of `300` means 300,000 bytes of JavaScript.

## Verification

1. Intentionally add a large dependency (`import _ from 'lodash'`) to a page and submit a PR.  Verify that the GitHub Actions workflow fails with `LHCI assertion failed: script budget exceeded`.
2. Confirm that `numberOfRuns: 3` is producing stable results: run LHCI 5 times on the same commit and check that LCP variance across runs is < 15%.  If variance is higher, increase to 5 runs or check for CI resource contention.
3. Check the LHCI server dashboard at your `serverBaseUrl` to confirm reports from the last 5 PRs are visible with historical trending.

## Related

- `performance-budget-setup.md` — general performance budget strategy
- `web-performance-budgets-core-web-vitals.md` — CWV budget definitions
- `lighthouse-scoring.md` — Lighthouse scoring mechanics
- `bundle-size-budgets.md` — JS/CSS byte budget setup
- `pagespeed-insights-api.md` — PageSpeed Insights API for field data

## Sources

- Lighthouse CI repository: https://github.com/GoogleChrome/lighthouse-ci
- LHCI configuration reference: https://github.com/GoogleChrome/lighthouse-ci/blob/main/docs/configuration.md
- Performance budgets: https://web.dev/articles/performance-budgets-101
- Lighthouse assertions: https://github.com/GoogleChrome/lighthouse-ci/blob/main/docs/assertions.md
