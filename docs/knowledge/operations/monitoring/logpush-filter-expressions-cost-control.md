# Logpush Filter Expressions and Field Selection for Cost Control

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
R2 storage bills and downstream analytics costs grow linearly with request volume because Logpush is configured to export all fields for every request. Filter expressions and selective field output reduce log volume by 60–90% without losing observability over error and latency signals.

## Context
Every Logpush job supports two orthogonal cost levers: `filter` (drop entire log lines that don't match a predicate) and `output_fields` (drop individual fields within a matching line). A third lever — `sample_rate` — probabilistically drops lines when even filtered volume is too high. Applied together, these can shrink a 100 GB/day workers_trace_events stream to under 10 GB/day while retaining 100% of errors and a representative sample of successes.

## Understanding Filter Expression Syntax

Logpush filter predicates are JSON objects sent in the `filter` field of the job creation/update payload.

```typescript
// src/filter-builder.ts

type Op =
  | 'eq' | 'neq'
  | 'lt' | 'lte' | 'gt' | 'gte'
  | 'contains' | 'startsWith' | 'endsWith'
  | 'matches';  // regex

interface Clause   { key: string; operator: Op; value: string | number }
interface AndGroup { and: (Clause | OrGroup | AndGroup)[] }
interface OrGroup  { or:  (Clause | AndGroup)[] }

type Predicate = Clause | AndGroup | OrGroup;

/** Build a filter that keeps errors AND requests slower than 500 ms */
export const errorOrSlowFilter: Predicate = {
  or: [
    { key: 'Outcome',    operator: 'neq', value: 'ok' },
    { key: 'WallTimeUs', operator: 'gt',  value: 500_000 },
  ],
};

/** Build a filter that keeps only specific scripts */
export const scriptAllowlist: Predicate = {
  or: [
    { key: 'ScriptName', operator: 'eq', value: 'api-worker' },
    { key: 'ScriptName', operator: 'eq', value: 'checkout-worker' },
  ],
};
```

## Applying Filter and Field Selection via the API

```typescript
// src/update-logpush-job.ts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const JOB_ID     = process.env.LOGPUSH_JOB_ID!;

// Only the fields needed for error analysis and latency bucketing
const OUTPUT_FIELDS = [
  'Timestamp',
  'RequestID',
  'ScriptName',
  'Outcome',
  'CPUTime',
  'WallTimeUs',
  'Status',
  'ClientCountry',
  'Exceptions',
].join(',');

const FILTER = {
  or: [
    { key: 'Outcome',    operator: 'neq', value: 'ok' },
    { key: 'WallTimeUs', operator: 'gt',  value: 200_000 },  // > 200 ms
    { key: 'Status',     operator: 'gte', value: 500 },
  ],
};

const resp = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs/${JOB_ID}`,
  {
    method: 'PUT',
    headers: {
      Authorization:  `Bearer ${API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      filter:          JSON.stringify(FILTER),
      logpull_options: `fields=${OUTPUT_FIELDS}&timestamps=rfc3339`,
    }),
  }
);

const json = await resp.json();
console.log('Updated job:', JSON.stringify(json.result, null, 2));
```

## Probabilistic Sampling for High-Volume Success Paths

When all requests must be sampled (e.g. for golden-signal dashboards), use `sample_rate` to keep a fraction of successful requests on top of the 100% error retention filter.

```typescript
// src/two-tier-sampling.ts
/**
 * Strategy: two Logpush jobs for the same dataset.
 *   Job 1 — errors + slow requests, 100% (filter as above)
 *   Job 2 — successful fast requests, 1% sample
 */

const successSampleJob = {
  name: 'workers-success-sample-1pct',
  dataset: 'workers_trace_events',
  enabled: true,
  logpull_options:
    `fields=Timestamp,ScriptName,Status,WallTimeUs&timestamps=rfc3339` +
    `&sample_rate=0.01`,
  filter: JSON.stringify({
    and: [
      { key: 'Outcome', operator: 'eq', value: 'ok' },
      { key: 'Status',  operator: 'lt', value: 400 },
    ],
  }),
  destination_conf: process.env.R2_DESTINATION_CONF!,
  output_type: 'ndjson',
};
```

## CI Validation of Filter Expressions

Validate filter JSON in CI to catch schema errors before they cause a silent Logpush misconfiguration.

```typescript
// scripts/validate-logpush-filter.ts
import { errorOrSlowFilter, scriptAllowlist } from './src/filter-builder';

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;

async function validateFilter(filter: object): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/validate/filter`,
    {
      method: 'POST',
      headers: {
        Authorization:  `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filter:  JSON.stringify(filter),
        dataset: 'workers_trace_events',
      }),
    }
  );

  const json: any = await resp.json();
  if (!json.success) {
    console.error('Filter validation failed:', JSON.stringify(json.errors, null, 2));
    process.exit(1);
  }
  console.log('Filter valid:', JSON.stringify(filter));
}

await validateFilter(errorOrSlowFilter);
await validateFilter(scriptAllowlist);
```

## Cost Modelling Before Applying Filters

Use the Logpush ownership API to measure current job throughput before committing to a filter, giving a baseline for cost comparison.

```typescript
// src/estimate-savings.ts
async function fetchJobStats(accountId: string, token: string, jobId: string) {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/logpush/jobs/${jobId}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const json: any = await resp.json();
  return {
    lastComplete:  json.result?.last_complete,
    lastError:     json.result?.last_error,
    frequency:     json.result?.frequency,
    outputType:    json.result?.output_type,
  };
}

// Estimate: typical workers_trace_events NDJSON is ~800 bytes/line uncompressed.
// At 10k RPS: 10_000 * 800 = 8 MB/s = ~690 GB/day.
// With 5% error rate and 200ms p99: ~8% of requests pass the filter = ~55 GB/day.
// R2 storage at $0.015/GB-month: from ~$310/month to ~$25/month.
```

## Anti-patterns
- Dropping the `Timestamp` and `RequestID` fields to save bytes — these are required for join operations and time-based partitioning
- Using a very restrictive filter that drops all successful requests — removes the ability to compute request rate, which is the denominator for error rate
- Applying `sample_rate` without a separate 100%-rate error job — sampled errors produce unreliable alerting thresholds
- Hardcoding filter JSON in wrangler.toml — store it as a deploy-time parameter and validate in CI before applying

## Gotchas
- `sample_rate` is applied after `filter` — sampling never applies to lines that did not match the filter
- The `matches` operator uses RE2 syntax, not PCRE; named groups are not supported
- Field names in `filter.key` are case-sensitive and must match the Logpush field schema exactly (e.g. `WallTimeUs`, not `wallTimeUs`)
- Changing `output_fields` requires a job PUT, not PATCH; the full job body must be re-submitted

## Verification
1. Call the validate endpoint in CI with `scripts/validate-logpush-filter.ts` — exit 0 expected
2. After applying the filter, monitor R2 object-put metrics in the Cloudflare dashboard for 24 hours
3. Verify error rows are still present: query the R2-backed Athena table for `WHERE Outcome != 'ok'` and compare row count against the Workers Analytics dashboard error count
4. Trigger a synthetic 500 and confirm the log line lands in R2 within 5 minutes despite the filter

## Related
- [cloudflare-logpush-setup.md](cloudflare-logpush-setup.md)
- [cloudflare-logpush-r2-partitioned-athena.md](cloudflare-logpush-r2-partitioned-athena.md)
- [logpush-bigquery-streaming-pipeline.md](logpush-bigquery-streaming-pipeline.md)
- [workers-logpush-observability-pipeline.md](workers-logpush-observability-pipeline.md)
- [log-sampling-strategies.md](log-sampling-strategies.md)
- [observability-cost-control.md](observability-cost-control.md)

## Sources
- https://developers.cloudflare.com/logs/reference/filters/
- https://developers.cloudflare.com/logs/get-started/api-configuration/#filter
- https://developers.cloudflare.com/logs/reference/log-fields/account/workers-trace-events/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
