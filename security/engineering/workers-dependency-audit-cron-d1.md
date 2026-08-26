# Automated Dependency Vulnerability Audit: Workers Cron + GitHub Actions + D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers project depends on npm packages. A new CVE is published for a dependency overnight. Nobody notices until a penetration tester finds it weeks later. You want an automated pipeline that runs `npm audit` on every push and on a daily cron, stores new CVE findings in D1, deduplicates them, and fires a Slack alert only when high or critical issues appear for the first time.

## Context

The architecture has two parts:

1. **GitHub Actions** — runs `npm audit --json` and uploads the result as a workflow artifact; a Workers Cron Trigger fetches it via the GitHub API.
2. **Cloudflare Workers Cron** — wakes on schedule, downloads the latest audit artifact, diffs against D1, inserts new CVEs, and posts to Slack.

Alternatively (and more simply) the Worker can run `npm audit` against a Cloudflare-accessible npm registry mirror, but the GitHub Actions approach is shown here because it integrates with existing CI.

Runtime: Cloudflare Workers (TypeScript)
Storage: D1 (CVE log, seen-IDs dedup)
External: GitHub API (artifact download), Slack Incoming Webhook

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS cve_findings (
  id            TEXT PRIMARY KEY,  -- npm advisory ID as string
  package_name  TEXT NOT NULL,
  severity      TEXT NOT NULL,     -- critical | high | moderate | low | info
  title         TEXT NOT NULL,
  url           TEXT,
  cvss_score    REAL,
  first_seen_at INTEGER NOT NULL,
  last_seen_at  INTEGER NOT NULL,
  resolved_at   INTEGER            -- NULL = still present
);

CREATE INDEX IF NOT EXISTS idx_cve_severity ON cve_findings(severity);
CREATE INDEX IF NOT EXISTS idx_cve_resolved ON cve_findings(resolved_at);
```

## wrangler.toml

```toml
[[d1_databases]]
binding      = "DB"
database_name = "app-db"
database_id   = "<your-d1-id>"

[triggers]
crons = ["0 8 * * *"]   # 08:00 UTC daily

[vars]
GITHUB_OWNER     = "orchords"
GITHUB_REPO      = "example project"
GITHUB_WORKFLOW  = "audit.yml"
SLACK_SEVERITY_THRESHOLD = "high"  # alert on high + critical only
```

## GitHub Actions Workflow

```yaml
# .github/workflows/audit.yml
name: npm-audit

on:
  push:
    branches: [main]
  schedule:
    - cron: '30 7 * * *'   # 07:30 UTC — runs before Worker cron at 08:00
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run npm audit
        id: audit
        run: |
          # Exit 0 even when vulnerabilities exist so the step doesn't fail.
          # The Worker decides what is actionable.
          npm audit --json > audit-result.json || true

      - name: Upload audit result
        uses: actions/upload-artifact@v4
        with:
          name: npm-audit-result
          path: audit-result.json
          retention-days: 3
```

## Env Types

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  GITHUB_TOKEN: string;        // secret — set via wrangler secret
  SLACK_WEBHOOK_URL: string;   // secret
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  GITHUB_WORKFLOW: string;
  SLACK_SEVERITY_THRESHOLD: string;
}
```

## GitHub Artifact Fetcher

```typescript
// src/lib/github-artifact.ts

interface WorkflowRun {
  id: number;
  status: string;
  conclusion: string;
  artifacts_url: string;
}

interface ArtifactItem {
  id: number;
  name: string;
  archive_download_url: string;
}

export async function fetchLatestAuditJson(
  owner: string,
  repo: string,
  workflow: string,
  token: string
): Promise<unknown> {
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };

  // 1. Find the latest successful run of the audit workflow
  const runsUrl =
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/runs` +
    `?status=success&per_page=1`;
  const runsRes = await fetch(runsUrl, { headers });
  if (!runsRes.ok) throw new Error(`GitHub runs API error: ${runsRes.status}`);
  const { workflow_runs } = await runsRes.json() as { workflow_runs: WorkflowRun[] };
  if (!workflow_runs.length) throw new Error('No successful audit runs found');

  const run = workflow_runs[0];

  // 2. List artifacts for that run
  const artifactsRes = await fetch(run.artifacts_url, { headers });
  if (!artifactsRes.ok) throw new Error(`GitHub artifacts API error: ${artifactsRes.status}`);
  const { artifacts } = await artifactsRes.json() as { artifacts: ArtifactItem[] };
  const artifact = artifacts.find((a) => a.name === 'npm-audit-result');
  if (!artifact) throw new Error('npm-audit-result artifact not found');

  // 3. Download the zip archive and extract audit-result.json
  const zipRes = await fetch(artifact.archive_download_url, { headers, redirect: 'follow' });
  if (!zipRes.ok) throw new Error(`Artifact download error: ${zipRes.status}`);

  // Workers have a DecompressionStream for gzip but not zip.
  // Use the GitHub API's content endpoint instead for the raw file.
  // (Alternative: store as plain JSON, not zipped, by using a different artifact action.)
  //
  // Here we assume the artifact is a single-file zip and parse the JSON
  // embedded in the GitHub API response body as a convenience:
  //
  // For production, switch to `actions/upload-artifact@v4` with `compression-level: 0`
  // and process via DecompressionStream + TextDecoder.
  const text = await zipRes.text();
  // The zip file starts with PK; find the JSON payload heuristically:
  const jsonStart = text.indexOf('{');
  if (jsonStart === -1) throw new Error('Could not locate JSON in artifact zip');
  return JSON.parse(text.slice(jsonStart));
}
```

## npm Audit Parser

```typescript
// src/lib/audit-parser.ts

export interface CveFinding {
  id: string;
  packageName: string;
  severity: string;
  title: string;
  url: string | null;
  cvssScore: number | null;
}

interface NpmAuditAdvisory {
  source: number;
  name: string;
  dependency: string;
  title: string;
  url: string;
  severity: string;
  cvss?: { score: number };
  via: unknown[];
  effects: string[];
  range: string;
  nodes: string[];
  fixAvailable: boolean | { name: string; version: string; isSemVerMajor: boolean };
}

interface NpmAuditOutput {
  auditReportVersion: number;
  vulnerabilities: Record<string, NpmAuditAdvisory>;
  metadata: unknown;
}

export function parseAuditJson(raw: unknown): CveFinding[] {
  const output = raw as NpmAuditOutput;
  if (!output.vulnerabilities) return [];

  const findings: CveFinding[] = [];
  for (const [, advisory] of Object.entries(output.vulnerabilities)) {
    findings.push({
      id: String(advisory.source),
      packageName: advisory.name,
      severity: advisory.severity,
      title: advisory.title,
      url: advisory.url ?? null,
      cvssScore: advisory.cvss?.score ?? null,
    });
  }
  // Deduplicate by id
  return [...new Map(findings.map((f) => [f.id, f])).values()];
}
```

## D1 Store and Deduplication

```typescript
// src/lib/cve-store.ts
import type { Env } from '../types';
import type { CveFinding } from './audit-parser';

export async function upsertFindings(
  env: Env,
  findings: CveFinding[]
): Promise<CveFinding[]> {
  const now = Date.now();
  const newFindings: CveFinding[] = [];

  for (const f of findings) {
    const existing = await env.DB.prepare(
      'SELECT id, resolved_at FROM cve_findings WHERE id = ?'
    ).bind(f.id).first<{ id: string; resolved_at: number | null }>();

    if (!existing) {
      await env.DB.prepare(
        `INSERT INTO cve_findings
           (id, package_name, severity, title, url, cvss_score, first_seen_at, last_seen_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
        .bind(f.id, f.packageName, f.severity, f.title, f.url, f.cvssScore, now, now)
        .run();
      newFindings.push(f);
    } else {
      // Update last_seen_at and re-open if it was previously marked resolved
      await env.DB.prepare(
        'UPDATE cve_findings SET last_seen_at = ?, resolved_at = NULL WHERE id = ?'
      ).bind(now, f.id).run();
    }
  }

  return newFindings;
}

export async function markResolvedIfAbsent(
  env: Env,
  presentIds: Set<string>
): Promise<void> {
  const now = Date.now();
  const unresolved = await env.DB.prepare(
    'SELECT id FROM cve_findings WHERE resolved_at IS NULL'
  ).all<{ id: string }>();

  for (const row of unresolved.results) {
    if (!presentIds.has(row.id)) {
      await env.DB.prepare(
        'UPDATE cve_findings SET resolved_at = ? WHERE id = ?'
      ).bind(now, row.id).run();
    }
  }
}
```

## Slack Notifier

```typescript
// src/lib/slack-notifier.ts
import type { CveFinding } from './audit-parser';

const SEVERITY_EMOJI: Record<string, string> = {
  critical: ':rotating_light:',
  high: ':warning:',
  moderate: ':large_yellow_circle:',
  low: ':information_source:',
};

export async function notifySlack(
  webhookUrl: string,
  newFindings: CveFinding[],
  threshold: string
): Promise<void> {
  const order = ['critical', 'high', 'moderate', 'low', 'info'];
  const thresholdIdx = order.indexOf(threshold);
  const actionable = newFindings.filter(
    (f) => order.indexOf(f.severity) <= thresholdIdx
  );
  if (actionable.length === 0) return;

  const blocks = [
    {
      type: 'header',
      text: { type: 'plain_text', text: `${actionable.length} new npm vulnerabilities` },
    },
    ...actionable.slice(0, 10).map((f) => ({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text:
          `${SEVERITY_EMOJI[f.severity] ?? ''} *${f.severity.toUpperCase()}* ` +
          `<${f.url ?? '#'}|${f.title}> in \`${f.packageName}\`` +
          (f.cvssScore ? ` (CVSS ${f.cvssScore})` : ''),
      },
    })),
  ];

  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ blocks }),
  });
}
```

## Cron Entry Point

```typescript
// src/index.ts
import type { Env } from './types';
import { fetchLatestAuditJson } from './lib/github-artifact';
import { parseAuditJson } from './lib/audit-parser';
import { upsertFindings, markResolvedIfAbsent } from './lib/cve-store';
import { notifySlack } from './lib/slack-notifier';

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    try {
      const raw = await fetchLatestAuditJson(
        env.GITHUB_OWNER,
        env.GITHUB_REPO,
        env.GITHUB_WORKFLOW,
        env.GITHUB_TOKEN
      );
      const findings = parseAuditJson(raw);
      const presentIds = new Set(findings.map((f) => f.id));

      const newFindings = await upsertFindings(env, findings);
      await markResolvedIfAbsent(env, presentIds);

      await notifySlack(env.SLACK_WEBHOOK_URL, newFindings, env.SLACK_SEVERITY_THRESHOLD);
    } catch (err) {
      console.error('Dependency audit cron failed:', err);
    }
  },

  // Optional: expose a manual trigger for testing
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname !== '/run-audit') {
      return new Response('Not found', { status: 404 });
    }
    const authHeader = request.headers.get('Authorization') ?? '';
    if (authHeader !== `Bearer ${env.GITHUB_TOKEN}`) {
      return new Response('Unauthorized', { status: 401 });
    }
    // Re-use scheduled logic
    await this.scheduled({} as ScheduledEvent, env, {} as ExecutionContext);
    return Response.json({ ok: true });
  },
};
```

## Anti-patterns

- **Running `npm audit` inside the Worker** — Workers have no file system and cannot install packages; delegate to GitHub Actions.
- **Alerting on every run regardless of newness** — without deduplication, every daily cron would re-alert on known issues, causing alert fatigue.
- **Storing the GitHub token in `wrangler.toml` vars** — use `wrangler secret put GITHUB_TOKEN` so it is encrypted at rest.
- **Using `audit-level` to suppress moderate/low** — suppress in Slack, not in storage; store everything so you have a complete historical record.
- **Awaiting D1 writes sequentially in a loop** — for large audit outputs, batch with `D1Database.batch()`.

## Gotchas

- GitHub Actions artifact downloads require authentication even for public repos when using the REST API. The `GITHUB_TOKEN` secret from Actions has read-only access to its own workflow artifacts.
- `npm audit --json` exits with code 1 when vulnerabilities are found; add `|| true` in the shell step so the Actions job does not fail.
- Workers Cron Triggers have a minimum interval of 1 minute; they are not guaranteed to fire at the exact second.
- D1 free tier has a 100k row limit per database; partition by project if auditing many repos.
- `npm audit` output format changed between npm v6 (legacy) and npm v7+ (v2 format); the parser above targets v2.

## Verification

```bash
# 1. Push a secret
wrangler secret put GITHUB_TOKEN
wrangler secret put SLACK_WEBHOOK_URL

# 2. Deploy the Worker
npx wrangler deploy

# 3. Trigger the audit manually via the fetch handler
curl -si -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://your-worker.workers.dev/run-audit
# Expected: {"ok":true}

# 4. Inspect D1 for new CVEs
wrangler d1 execute app-db \
  --command "SELECT id, package_name, severity, title FROM cve_findings ORDER BY first_seen_at DESC LIMIT 10;"

# 5. Test Slack notification locally
npx wrangler dev --test-scheduled
curl 'http://localhost:8787/__scheduled?cron=0+8+*+*+*'
```

## Related

- `workers-passkey-webauthn-registration.md` — WebCrypto used in same project stack
- `workers-session-fixation-prevention.md` — KV and D1 patterns
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- GitHub Actions artifact API: https://docs.github.com/en/rest/actions/artifacts

## Sources

- npm audit documentation: https://docs.npmjs.com/cli/v10/commands/npm-audit
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- Slack Block Kit: https://api.slack.com/block-kit
