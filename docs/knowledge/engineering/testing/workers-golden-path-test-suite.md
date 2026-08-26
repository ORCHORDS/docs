# Golden Path Test Suite for Workers APIs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Each deploy triggers a battery of unit, integration, and E2E tests, but there is no single authoritative signal that the most important user journeys are working right now. On-call engineers have to correlate logs, dashboards, and test results to answer "is the golden path healthy?". You need a curated, data-driven test suite that runs the critical journeys end-to-end and emits a structured pass/fail signal after each deploy.

## Context

A **golden path test suite** is a small set of carefully chosen tests that cover the critical user journeys from first request to final response, including all Worker integrations (D1, KV, Queue, Service Bindings). It is:

- **Data-driven** — test cases are defined in D1 fixture tables, not hard-coded in test files.
- **Environment-aware** — uses a `BASE_URL` per environment (staging, production).
- **Observable** — results are written to Workers Analytics Engine for dashboarding.
- **Triggered after each deploy** — a GitHub Actions workflow calls the suite via `wrangler deploy --dispatch-namespace` or a simple HTTP call to a `/__golden-path` diagnostic Worker route.

The suite complements E2E tests: E2E tests run in CI against local Miniflare; the golden path runs against live deployments.

## Solution

```typescript
// src/golden-path/runner.ts
// Runs inside a lightweight diagnostic Worker invoked after each deploy

export interface GoldenPathCase {
  id: string;
  journey: string;          // e.g. "browse-and-purchase"
  method: string;
  path: string;
  headers?: Record<string, string>;
  body?: unknown;
  expectedStatus: number;
  expectedBodyContains?: string;
  criticalityLevel: 'P0' | 'P1' | 'P2';
}

export interface GoldenPathResult {
  caseId: string;
  journey: string;
  passed: boolean;
  statusCode: number;
  durationMs: number;
  error?: string;
  timestamp: string;
}

export async function runGoldenPath(
  cases: GoldenPathCase[],
  baseUrl: string,
  authToken: string
): Promise<GoldenPathResult[]> {
  const results: GoldenPathResult[] = [];

  for (const tc of cases) {
    const start = Date.now();
    let statusCode = 0;
    let passed = false;
    let error: string | undefined;

    try {
      const res = await fetch(`${baseUrl}${tc.path}`, {
        method: tc.method,
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
          ...tc.headers,
        },
        body: tc.body ? JSON.stringify(tc.body) : undefined,
      });

      statusCode = res.status;
      const body = await res.text();

      const statusOk = res.status === tc.expectedStatus;
      const bodyOk   = tc.expectedBodyContains
        ? body.includes(tc.expectedBodyContains)
        : true;
      passed = statusOk && bodyOk;

      if (!statusOk)  error = `Expected status ${tc.expectedStatus}, got ${res.status}`;
      if (!bodyOk)    error = `Body did not contain "${tc.expectedBodyContains}"`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      passed = false;
    }

    results.push({
      caseId: tc.id,
      journey: tc.journey,
      passed,
      statusCode,
      durationMs: Date.now() - start,
      error,
      timestamp: new Date().toISOString(),
    });
  }

  return results;
}
```

```typescript
// src/golden-path/fixtures.ts
// Load golden path test cases from D1

import type { D1Database } from '@cloudflare/workers-types';
import type { GoldenPathCase } from './runner';

export async function loadGoldenPathCases(
  db: D1Database,
  environment: string
): Promise<GoldenPathCase[]> {
  const { results } = await db
    .prepare(
      `SELECT
         id, journey, method, path, headers_json, body_json,
         expected_status, expected_body_contains, criticality_level
       FROM golden_path_cases
       WHERE enabled = 1
         AND (environment = ? OR environment = 'all')
       ORDER BY criticality_level ASC, journey ASC`
    )
    .bind(environment)
    .all<{
      id: string;
      journey: string;
      method: string;
      path: string;
      headers_json: string | null;
      body_json: string | null;
      expected_status: number;
      expected_body_contains: string | null;
      criticality_level: 'P0' | 'P1' | 'P2';
    }>();

  return results.map((row) => ({
    id: row.id,
    journey: row.journey,
    method: row.method,
    path: row.path,
    headers:               row.headers_json ? JSON.parse(row.headers_json) : undefined,
    body:                  row.body_json    ? JSON.parse(row.body_json)    : undefined,
    expectedStatus:        row.expected_status,
    expectedBodyContains:  row.expected_body_contains ?? undefined,
    criticalityLevel:      row.criticality_level,
  }));
}
```

```typescript
// src/golden-path/analytics.ts
// Emit golden path results to Workers Analytics Engine

import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';
import type { GoldenPathResult } from './runner';

export function emitGoldenPathResults(
  dataset: AnalyticsEngineDataset,
  results: GoldenPathResult[],
  environment: string,
  deployId: string
): void {
  for (const r of results) {
    dataset.writeDataPoint({
      blobs: [
        r.caseId,
        r.journey,
        environment,
        deployId,
        r.passed ? 'pass' : 'fail',
        r.error ?? '',
      ],
      doubles: [r.durationMs, r.statusCode],
      indexes: [r.caseId],
    });
  }
}
```

```typescript
// src/golden-path/index.ts
// Worker entry point for the golden path diagnostic route

import type { Env } from '../types';
import { loadGoldenPathCases } from './fixtures';
import { runGoldenPath }       from './runner';
import { emitGoldenPathResults } from './analytics';

export async function handleGoldenPath(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  // Guard: only allow internal invocations
  const secret = <redacted-secret>'X-Golden-Path-Secret');
  if (secret !== env.GOLDEN_PATH_SECRET) {
    return new Response('Forbidden', { status: 403 });
  }

  const { environment = 'production', deployId = 'unknown' } =
    await request.json<{ environment?: string; deployId?: string }>();

  const cases = await loadGoldenPathCases(env.DB, environment);
  const baseUrl = env.SELF_BASE_URL; // e.g. https://api.example.com
  const authToken = env.E2E_AUTH_TOKEN;

  const results = await runGoldenPath(cases, baseUrl, authToken);
  emitGoldenPathResults(env.ANALYTICS, results, environment, deployId);

  const totalPassed = results.filter((r) => r.passed).length;
  const p0Failed    = results.filter((r) => !r.passed && r.criticalityLevel === 'P0');

  const summary = {
    total:       results.length,
    passed:      totalPassed,
    failed:      results.length - totalPassed,
    p0Failed:    p0Failed.length,
    allP0Pass:   p0Failed.length === 0,
    results,
  };

  return new Response(JSON.stringify(summary, null, 2), {
    status: p0Failed.length > 0 ? 424 : 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

```typescript
// tests/golden-path/runner.test.ts
// Unit tests for the runner logic — uses fetch mocking

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runGoldenPath, type GoldenPathCase } from '../../src/golden-path/runner';

const BASE_CASE: GoldenPathCase = {
  id: 'gp-001',
  journey: 'health-check',
  method: 'GET',
  path: '/health',
  expectedStatus: 200,
  criticalityLevel: 'P0',
};

beforeEach(() => { vi.restoreAllMocks(); });

describe('runGoldenPath', () => {
  it('marks a case as passed when status and body match', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('{"status":"ok"}', { status: 200 })
    ));

    const results = await runGoldenPath(
      [{ ...BASE_CASE, expectedBodyContains: '"status":"ok"' }],
      'http://localhost',
      'token'
    );

    expect(results[0].passed).toBe(true);
    expect(results[0].error).toBeUndefined();
  });

  it('marks a case as failed on unexpected status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('Not Found', { status: 404 })
    ));

    const results = await runGoldenPath([BASE_CASE], 'http://localhost', 'token');

    expect(results[0].passed).toBe(false);
    expect(results[0].error).toMatch(/Expected status 200, got 404/);
  });

  it('marks a case as failed when body does not contain expected string', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('{"status":"degraded"}', { status: 200 })
    ));

    const results = await runGoldenPath(
      [{ ...BASE_CASE, expectedBodyContains: '"status":"ok"' }],
      'http://localhost',
      'token'
    );

    expect(results[0].passed).toBe(false);
  });

  it('handles fetch errors gracefully', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));

    const results = await runGoldenPath([BASE_CASE], 'http://localhost', 'token');

    expect(results[0].passed).toBe(false);
    expect(results[0].error).toMatch(/ECONNREFUSED/);
  });

  it('runs all cases and returns results in order', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('ok', { status: 200 })
    ));

    const cases: GoldenPathCase[] = [
      { ...BASE_CASE, id: 'gp-001', path: '/a' },
      { ...BASE_CASE, id: 'gp-002', path: '/b' },
      { ...BASE_CASE, id: 'gp-003', path: '/c' },
    ];

    const results = await runGoldenPath(cases, 'http://localhost', 'token');
    expect(results.map((r) => r.caseId)).toEqual(['gp-001', 'gp-002', 'gp-003']);
  });
});
```

```yaml
# .github/workflows/golden-path.yml
name: Golden Path
on:
  workflow_run:
    workflows: [Deploy]
    types: [completed]

jobs:
  golden-path:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-22.04
    steps:
      - name: Trigger golden path suite
        run: |
          STATUS=$(curl -s -o response.json -w "%{http_code}" \
            -X POST \
            -H "X-Golden-Path-Secret: ${{ secrets.GOLDEN_PATH_SECRET }}" \
            -H "Content-Type: application/json" \
            -d '{"environment":"production","deployId":"${{ github.sha }}"}' \
            ${{ secrets.GOLDEN_PATH_URL }})

          cat response.json | jq .
          [ "$STATUS" = "200" ] || exit 1
```

## Implementation Details

**D1 fixture table schema:**

```sql
CREATE TABLE golden_path_cases (
  id                   TEXT PRIMARY KEY,
  journey              TEXT NOT NULL,
  method               TEXT NOT NULL DEFAULT 'GET',
  path                 TEXT NOT NULL,
  headers_json         TEXT,
  body_json            TEXT,
  expected_status      INTEGER NOT NULL DEFAULT 200,
  expected_body_contains TEXT,
  criticality_level    TEXT NOT NULL CHECK (criticality_level IN ('P0','P1','P2')),
  environment          TEXT NOT NULL DEFAULT 'all',
  enabled              INTEGER NOT NULL DEFAULT 1
);
```

**Analytics Engine dashboard** — query Analytics Engine with the Cloudflare dashboard SQL UI to build a "Golden Path Health" chart:

```sql
SELECT
  blob5 AS result,
  blob3 AS environment,
  COUNT() AS count,
  avg(double1) AS avg_duration_ms
FROM GOLDEN_PATH_RESULTS
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY blob5, blob3
ORDER BY count DESC;
```

## Anti-patterns

- **Too many golden path cases** — the suite should cover 5–15 critical journeys. Anything larger becomes slow and noisy. Use the full E2E suite for breadth; golden path for depth on critical paths.
- **Mutable test data in the golden path** — cases that create records (POST /orders) must clean up after themselves or use a dedicated test account that is reset between runs.
- **Treating P1/P2 failures as deploys blockers** — only P0 failures should block a deploy. P1/P2 failures should page on-call but not roll back.
- **Hard-coding base URLs** — use `SELF_BASE_URL` binding or an environment variable. Hard-coded URLs in D1 fixture rows cause staging tests to hit production.

## Gotchas

- Workers Analytics Engine writes are fire-and-forget; the Worker must `ctx.waitUntil(promise)` the write if the Worker returns before the Analytics call resolves.
- The golden path Worker must have `SELF_BASE_URL` set to its own deployed URL, not `localhost`. A Worker cannot fetch itself on `localhost` in a production deployment.
- Analytics Engine data has a write latency of 1–5 minutes. Do not query it immediately after the golden path run to assert results; use the HTTP response instead.
- The `E2E_AUTH_TOKEN` stored in Worker secrets must correspond to a real test account in the production database. Rotate it on a schedule and update the secret via `wrangler secret put`.

## Verification

```bash
# Insert a sample P0 case into local D1
npx wrangler d1 execute DB --local --command "
  INSERT INTO golden_path_cases (id, journey, method, path, expected_status, criticality_level)
  VALUES ('gp-health', 'health-check', 'GET', '/health', 200, 'P0');
"

# Invoke the golden path endpoint locally
curl -s -X POST http://localhost:8787/__golden-path \
  -H 'X-Golden-Path-Secret: <redacted-secret>' \
  -H 'Content-Type: application/json' \
  -d '{"environment":"local","deployId":"dev"}' | jq .

# Run unit tests
npx vitest run tests/golden-path/

# Query Analytics Engine for golden path results (after a live run)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob1, blob5, double1 FROM GOLDEN_PATH_RESULTS LIMIT 10"
```

## Related

- `documentation/docs/policies/testing/workers-contract-testing-pact.md`
- `documentation/docs/policies/testing/workers-e2e-testing-playwright-workers.md`
- `documentation/docs/policies/testing/workers-load-testing-k6-workers.md`
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare D1: https://developers.cloudflare.com/d1/

## Sources

- Cloudflare Workers — Analytics Engine write API (2025)
- Cloudflare D1 — Query API (2025)
- example.com internal runbook: golden-path-test-suite (2026-08)
