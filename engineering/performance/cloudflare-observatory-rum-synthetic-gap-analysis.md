# Cloudflare Observatory RUM vs Synthetic Monitoring Gap Analysis

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Lab Scores That Don't Match Field Reality

Lighthouse CI (synthetic) and Cloudflare Observatory field data frequently disagree. A page can score 90+ in Lighthouse while real users experience LCP above 4 s. The inverse also happens: Observatory shows excellent field LCP but Lighthouse CI fails budget checks because it tests on throttled mobile, hitting a code path that real traffic never reaches.

When these two signals diverge without explanation, teams either ignore the field data ("the lab says it's fine") or ignore synthetic results ("real users are happy"), losing the complementary value of each. The correct response is to quantify the gap systematically, trace it to a root cause, and alert when the divergence exceeds a defined threshold.

This article covers pulling Observatory RUM data and Lighthouse CI JSON results into a unified comparison pipeline, computing gap metrics, and triggering alerts via a scheduled Worker when the lab-to-field discrepancy is out of bounds.

## Context

Cloudflare Observatory exposes field data through the GraphQL Analytics API under `rumPageloadEventsAdaptiveGroups`. Lighthouse CI stores JSON reports in a configurable storage backend (LHCI server, cloud storage, or local files). To correlate them you need: (1) a consistent URL fingerprint as the join key, (2) the same metric names mapped between the two schemas, and (3) a time window that aligns a synthetic run with the RUM sample it represents.

Key metric mappings:

| Observatory field  | Lighthouse CI audit key          |
|--------------------|----------------------------------|
| `lcp`              | `largest-contentful-paint`       |
| `inp`              | `interaction-to-next-paint`      |
| `cls`              | `cumulative-layout-shift`        |
| `ttfb`             | `server-response-time`           |
| `fcp`              | `first-contentful-paint`         |

## Pulling Observatory Field Data

```typescript
const CF_GRAPHQL = 'https://api.cloudflare.com/client/v4/graphql';

interface RumMetric {
  url: string;
  p75Lcp: number;
  p75Inp: number;
  p75Cls: number;
  p75Ttfb: number;
  sampleCount: number;
}

async function fetchObservatoryRum(
  accountId: string,
  apiToken: string,
  siteTag: string,
  sinceHours = 24,
): Promise<RumMetric[]> {
  const since = new Date(Date.now() - sinceHours * 3600 * 1000).toISOString();
  const query = `
    query RumField($accountTag: String!, $siteTag: String!, $since: String!) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          rumPageloadEventsAdaptiveGroups(
            limit: 200
            filter: {
              siteTag: $siteTag
              datetime_geq: $since
              deviceType: "MOBILE"
            }
            orderBy: [count_DESC]
          ) {
            count
            avg { lcp inp cls ttfb }
            quantiles { lcpP75: lcp75 inpP75: inp75 clsP75: cls75 ttfbP75: ttfb75 }
            dimensions { requestHost requestPath }
          }
        }
      }
    }
  `;
  const res = await fetch(CF_GRAPHQL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, variables: { accountTag: accountId, siteTag, since } }),
  });
  const json = await res.json<{ data: any }>();
  const groups = json.data.viewer.accounts[0].rumPageloadEventsAdaptiveGroups;
  return groups.map((g: any) => ({
    url: `https://${g.dimensions.requestHost}${g.dimensions.requestPath}`,
    p75Lcp:  g.quantiles.lcpP75,
    p75Inp:  g.quantiles.inpP75,
    p75Cls:  g.quantiles.clsP75,
    p75Ttfb: g.quantiles.ttfbP75,
    sampleCount: g.count,
  }));
}
```

## Pulling Lighthouse CI Synthetic Results

```typescript
// Assumes LHCI server is running; adapt for R2 or GCS storage
interface LhciResult {
  url: string;
  lcp: number;   // ms
  inp: number;   // ms
  cls: number;   // score 0–1
  ttfb: number;  // ms
  fcp: number;   // ms
  runAt: string; // ISO timestamp
}

async function fetchLatestLhciRun(
  lhciServerUrl: string,
  lhciToken: string,
  projectId: string,
): Promise<LhciResult[]> {
  const buildsRes = await fetch(
    `${lhciServerUrl}/v1/projects/${projectId}/builds?limit=1`,
    { headers: { 'x-lhci-token': lhciToken } },
  );
  const [build] = await buildsRes.json<any[]>();
  if (!build) return [];

  const runsRes = await fetch(
    `${lhciServerUrl}/v1/projects/${projectId}/builds/${build.id}/runs`,
    { headers: { 'x-lhci-token': lhciToken } },
  );
  const runs = await runsRes.json<any[]>();

  return runs.map(run => {
    const lhr = JSON.parse(run.lhr);
    const get = (id: string) => lhr.audits[id]?.numericValue ?? 0;
    return {
      url: lhr.finalDisplayedUrl,
      lcp:  get('largest-contentful-paint'),
      inp:  get('interaction-to-next-paint'),
      cls:  get('cumulative-layout-shift'),
      ttfb: get('server-response-time'),
      fcp:  get('first-contentful-paint'),
      runAt: build.createdAt,
    };
  });
}
```

## Computing the Gap and Triggering Alerts

```typescript
interface GapReport {
  url: string;
  metric: string;
  fieldP75: number;
  syntheticValue: number;
  gapPercent: number;
  direction: 'lab_worse' | 'field_worse' | 'aligned';
}

const GAP_THRESHOLD_PERCENT = 30; // alert if divergence > 30%

function computeGaps(rum: RumMetric[], lhci: LhciResult[]): GapReport[] {
  const lhciByUrl = new Map(lhci.map(r => [normalizeUrl(r.url), r]));
  const reports: GapReport[] = [];

  for (const field of rum) {
    const lab = lhciByUrl.get(normalizeUrl(field.url));
    if (!lab || field.sampleCount < 50) continue; // need enough RUM samples

    const pairs: Array<[string, number, number]> = [
      ['lcp',  field.p75Lcp,  lab.lcp],
      ['inp',  field.p75Inp,  lab.inp],
      ['ttfb', field.p75Ttfb, lab.ttfb],
    ];

    for (const [metric, fieldVal, labVal] of pairs) {
      if (fieldVal === 0 && labVal === 0) continue;
      const base = Math.max(fieldVal, labVal);
      const gapPercent = base > 0 ? Math.abs(fieldVal - labVal) / base * 100 : 0;
      reports.push({
        url: field.url,
        metric,
        fieldP75: fieldVal,
        syntheticValue: labVal,
        gapPercent: Math.round(gapPercent),
        direction: labVal > fieldVal ? 'lab_worse' : fieldVal > labVal ? 'field_worse' : 'aligned',
      });
    }
  }
  return reports.filter(r => r.gapPercent > GAP_THRESHOLD_PERCENT);
}

function normalizeUrl(url: string): string {
  try {
    const u = new URL(url);
    u.search = '';
    u.hash = '';
    return u.toString().replace(/\/$/, '');
  } catch {
    return url;
  }
}

// Scheduled Worker that runs the pipeline and sends alerts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const [rum, lhci] = await Promise.all([
      fetchObservatoryRum(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, env.RUM_SITE_TAG),
      fetchLatestLhciRun(env.LHCI_SERVER_URL, env.LHCI_TOKEN, env.LHCI_PROJECT_ID),
    ]);

    const gaps = computeGaps(rum, lhci);
    if (gaps.length === 0) return;

    // POST alert to a webhook (Slack, PagerDuty, etc.)
    await fetch(env.ALERT_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: `Lab-to-field gap alert: ${gaps.length} metric(s) diverged > ${GAP_THRESHOLD_PERCENT}%`,
        attachments: gaps.slice(0, 5).map(g => ({
          title: `${g.metric.toUpperCase()} on ${g.url}`,
          text: `Field p75: ${g.fieldP75}ms | Lab: ${g.syntheticValue}ms | Gap: ${g.gapPercent}% (${g.direction})`,
          color: g.direction === 'field_worse' ? 'danger' : 'warning',
        })),
      }),
    });
  },
};
```

## Anti-patterns

- **Comparing field averages to lab values** — always use p75 for field metrics and compare to the same percentile of synthetic runs (median of 3 Lighthouse runs). Averages are skewed by outliers in RUM and not comparable to single-run lab scores.
- **Using desktop Lighthouse against mobile RUM** — Observatory segments by `deviceType`. Run Lighthouse CI in mobile-emulation mode (`--preset=perf`) when comparing to the `MOBILE` segment.
- **Alerting on every run** — short-term RUM fluctuations are normal. Apply a minimum sample count threshold (e.g., 50 page views) and a moving average over 3 synthetic runs before triggering an alert.
- **Ignoring the direction** — `lab_worse` gaps (lab sees higher latency than field) often indicate the synthetic test hits a cold-cache code path. `field_worse` gaps indicate real user conditions (slow networks, CPU contention) that the lab doesn't reproduce.

## Gotchas

- Observatory RUM data has a processing delay of up to 30 minutes. When comparing a just-completed Lighthouse CI run to RUM, always use the `sinceHours` window that predates the run by at least 1 hour.
- CLS comparison is tricky: Lighthouse CI measures CLS during its load simulation; field CLS accumulates across the full session. Field CLS p75 is almost always higher. Consider a looser threshold for CLS gaps.
- URLs with query parameters need normalization before joining. Canonical URLs in Observatory may differ from `finalDisplayedUrl` in Lighthouse (redirects, canonical tags).
- LHCI server pagination: builds endpoint returns newest first. Always take `builds?limit=1` to get the most recent run.

## Verification

```bash
# Run the scheduled Worker immediately via Wrangler
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Or query directly: compare Observatory GraphQL against your LHCI server results
# and verify gap percentages match manual calculation
```

## Related

- `rum-vs-synthetic-metrics.md`
- `analytics-engine-rum-web-vitals.md`
- `lighthouse-ci-budget-enforcement.md`
- `crux-field-data.md`
- `performance-regression-detection.md`

## Sources

- Cloudflare Observatory RUM: https://developers.cloudflare.com/speed/speed-test/
- Cloudflare GraphQL Analytics: https://developers.cloudflare.com/analytics/graphql-api/
- Lighthouse CI: https://github.com/GoogleChrome/lighthouse-ci
- Web Vitals field vs lab: https://web.dev/articles/lab-and-field-data-differences
