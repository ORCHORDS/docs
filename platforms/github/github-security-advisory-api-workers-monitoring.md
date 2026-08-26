# GitHub Security Advisory API Monitoring with Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Teams that maintain open-source packages or consume many third-party dependencies need
proactive alerts when new GitHub Security Advisories (GHSAs) are published that affect
their ecosystem. Waiting for Dependabot PRs is reactive and delayed. A Cloudflare
Worker scheduled to poll the GitHub Advisory Database API can detect new CVEs within
minutes of publication, filter to relevant ecosystems and severity thresholds, persist
findings in D1, and push alerts to Slack or PagerDuty before CI pipelines even run.

---

## Context

GitHub exposes two advisory sources:

1. **REST API** – `GET /advisories` (global advisory database, public, no auth needed
   for public advisories; auth needed for private org advisories).
2. **GraphQL API** – `securityAdvisories` query, supports filtering by `ecosystem`,
   `severity`, `classifications`, and `publishedSince`.

Advisories have a `ghsaId` (e.g. `GHSA-xxxx-xxxx-xxxx`) and a matching `cveId`.
Each advisory lists affected `packages` with `vulnerableVersionRange` and
`firstPatchedVersion` for each ecosystem.

The Cloudflare Worker polls on a schedule, stores new advisories in D1, and emits
webhook alerts for any advisory matching configured severity + ecosystem rules.

---

## 1. D1 Schema

```sql
-- migrations/0001_advisories.sql
CREATE TABLE IF NOT EXISTS advisories (
  ghsa_id         TEXT PRIMARY KEY,
  cve_id          TEXT,
  summary         TEXT,
  severity        TEXT,   -- LOW | MODERATE | HIGH | CRITICAL
  ecosystem       TEXT,
  package_name    TEXT,
  vulnerable_range TEXT,
  patched_version TEXT,
  published_at    TEXT,
  alerted_at      TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_advisories_severity ON advisories(severity, alerted_at);
CREATE INDEX IF NOT EXISTS idx_advisories_package  ON advisories(ecosystem, package_name);
```

---

## 2. GraphQL Poller

```typescript
// workers/advisory-monitor/src/poll.ts
export interface Advisory {
  ghsaId: string;
  summary: string;
  severity: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
  publishedAt: string;
  identifiers: Array<{ type: string; value: string }>;
  vulnerabilities: {
    nodes: Array<{
      package: { ecosystem: string; name: string };
      vulnerableVersionRange: string;
      firstPatchedVersion: { identifier: string } | null;
    }>;
  };
}

const QUERY = `
  query($since: DateTime!, $after: String) {
    securityAdvisories(publishedSince: $since, orderBy: {field: PUBLISHED_AT, direction: ASC}, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        ghsaId
        summary
        severity
        publishedAt
        identifiers { type value }
        vulnerabilities(first: 20) {
          nodes {
            package { ecosystem name }
            vulnerableVersionRange
            firstPatchedVersion { identifier }
          }
        }
      }
    }
  }
`;

export async function fetchAdvisories(
  githubToken: string,
  since: string,
  cursor?: string
): Promise<{ advisories: Advisory[]; nextCursor?: string }> {
  const res = await fetch("https://api.github.com/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${githubToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query: QUERY, variables: { since, after: cursor } }),
  });

  const { data, errors } = await res.json<{
    data: { securityAdvisories: { pageInfo: { hasNextPage: boolean; endCursor: string }; nodes: Advisory[] } };
    errors?: Array<{ message: string }>;
  }>();

  if (errors?.length) throw new Error(errors[0].message);

  const page = data.securityAdvisories;
  return {
    advisories: page.nodes,
    nextCursor: page.pageInfo.hasNextPage ? page.pageInfo.endCursor : undefined,
  };
}
```

---

## 3. Alert Dispatcher

```typescript
// workers/advisory-monitor/src/alert.ts
export interface AlertPayload {
  ghsaId: string;
  cveId?: string;
  summary: string;
  severity: string;
  ecosystem: string;
  packageName: string;
  vulnerableRange: string;
  patchedVersion?: string;
  publishedAt: string;
}

export async function sendSlackAlert(
  webhookUrl: string,
  advisory: AlertPayload
): Promise<void> {
  const severityEmoji: Record<string, string> = {
    CRITICAL: ":red_circle:",
    HIGH:     ":orange_circle:",
    MODERATE: ":yellow_circle:",
    LOW:      ":white_circle:",
  };

  const blocks = [
    {
      type: "header",
      text: { type: "plain_text", text: `${severityEmoji[advisory.severity] ?? ""} ${advisory.severity} Advisory – ${advisory.ecosystem}/${advisory.packageName}` },
    },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: `*GHSA:* <https://github.com/advisories/${advisory.ghsaId}|${advisory.ghsaId}>` },
        { type: "mrkdwn", text: `*CVE:* ${advisory.cveId ?? "pending"}` },
        { type: "mrkdwn", text: `*Affected range:* \`${advisory.vulnerableRange}\`` },
        { type: "mrkdwn", text: `*Patched:* ${advisory.patchedVersion ?? "no patch yet"}` },
      ],
    },
    { type: "section", text: { type: "mrkdwn", text: advisory.summary } },
  ];

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks }),
  });
}
```

---

## 4. Scheduled Worker

```typescript
// workers/advisory-monitor/src/index.ts
export interface Env {
  DB: D1Database;
  GITHUB_TOKEN: string;       // Fine-grained PAT with "Security advisories: read"
  SLACK_WEBHOOK_URL: string;
  ALERT_ECOSYSTEMS: string;   // comma-separated: "npm,pip,rubygems"
  MIN_SEVERITY: string;       // LOW | MODERATE | HIGH | CRITICAL
  LAST_POLL_KV: KVNamespace;
}

import { fetchAdvisories } from "./poll";
import { sendSlackAlert, AlertPayload } from "./alert";

const SEVERITY_RANK: Record<string, number> = { LOW: 1, MODERATE: 2, HIGH: 3, CRITICAL: 4 };

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const ecosystems = new Set(env.ALERT_ECOSYSTEMS.split(",").map((e) => e.trim().toUpperCase()));
    const minRank = SEVERITY_RANK[env.MIN_SEVERITY.toUpperCase()] ?? 2;

    // Resume from last successful poll timestamp
    const since = (await env.LAST_POLL_KV.get("last_poll_at")) ?? new Date(Date.now() - 3_600_000).toISOString();
    let latestPublished = since;
    let cursor: string | undefined;

    do {
      const { advisories, nextCursor } = await fetchAdvisories(env.GITHUB_TOKEN, since, cursor);
      cursor = nextCursor;

      for (const advisory of advisories) {
        if (advisory.publishedAt > latestPublished) latestPublished = advisory.publishedAt;

        for (const vuln of advisory.vulnerabilities.nodes) {
          const eco = vuln.package.ecosystem.toUpperCase();
          if (!ecosystems.has(eco)) continue;
          if ((SEVERITY_RANK[advisory.severity] ?? 0) < minRank) continue;

          const cveId = advisory.identifiers.find((i) => i.type === "CVE")?.value;
          const payload: AlertPayload = {
            ghsaId: advisory.ghsaId,
            cveId,
            summary: advisory.summary,
            severity: advisory.severity,
            ecosystem: vuln.package.ecosystem,
            packageName: vuln.package.name,
            vulnerableRange: vuln.vulnerableVersionRange,
            patchedVersion: vuln.firstPatchedVersion?.identifier,
            publishedAt: advisory.publishedAt,
          };

          // Upsert into D1 (skip if already alerted)
          const existing = await env.DB
            .prepare("SELECT alerted_at FROM advisories WHERE ghsa_id = ? AND package_name = ?")
            .bind(advisory.ghsaId, vuln.package.name)
            .first<{ alerted_at: string | null }>();

          if (existing?.alerted_at) continue; // already alerted

          await env.DB.prepare(`
            INSERT INTO advisories (ghsa_id, cve_id, summary, severity, ecosystem, package_name, vulnerable_range, patched_version, published_at, alerted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ghsa_id) DO UPDATE SET alerted_at = datetime('now')
          `).bind(
            advisory.ghsaId, cveId ?? null, advisory.summary, advisory.severity,
            vuln.package.ecosystem, vuln.package.name, vuln.vulnerableVersionRange,
            vuln.firstPatchedVersion?.identifier ?? null, advisory.publishedAt
          ).run();

          await sendSlackAlert(env.SLACK_WEBHOOK_URL, payload);
        }
      }
    } while (cursor);

    await env.LAST_POLL_KV.put("last_poll_at", latestPublished);
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. wrangler.toml

```toml
# wrangler.toml
name = "advisory-monitor"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[triggers]
crons = ["*/15 * * * *"]   # poll every 15 minutes

[[d1_databases]]
binding = "DB"
database_name = "advisory-monitor-db"
database_id   = "YOUR_D1_DB_ID"

[[kv_namespaces]]
binding = "LAST_POLL_KV"
id      = "YOUR_KV_NAMESPACE_ID"

[vars]
ALERT_ECOSYSTEMS = "npm,pip"
MIN_SEVERITY     = "HIGH"

# Secrets via: npx wrangler secret put GITHUB_TOKEN
# Secrets via: npx wrangler secret put SLACK_WEBHOOK_URL
```

---

## Anti-patterns

- **Polling without a cursor/timestamp bookmark** – re-fetching all advisories from the
  beginning on every run wastes API quota and produces duplicate alerts.
- **Alerting on all severities without a minimum threshold** – LOW severity advisories
  are extremely noisy; start at HIGH or CRITICAL and expand after tuning.
- **Using a GITHUB_TOKEN with excessive scopes** – advisory API is public for the global
  database; a fine-grained PAT with read-only `security_events` is sufficient.
- **Not de-duplicating by `ghsa_id` + `package_name`** – an advisory may be updated
  multiple times; store the first alert timestamp and skip re-alerts unless severity
  escalates.

---

## Gotchas

- The GraphQL `securityAdvisories` query returns advisories sorted by `PUBLISHED_AT`
  ascending; using `UPDATED_AT` order catches advisory revisions but requires tracking
  the `updatedAt` field separately from `publishedAt`.
- GitHub's Advisory Database includes advisories for all GitHub-hosted repositories,
  not only the npm/pip/etc. ecosystems; always filter by `ecosystems` in the query.
- The REST `GET /advisories` endpoint returns at most 100 per page and requires a PAT
  even for public advisories when using authenticated filters (e.g. `severity=high`).
- `firstPatchedVersion` may be `null` if no patch exists at publication time; your
  alert copy must handle this gracefully rather than showing "null".
- Worker cron triggers are best-effort and may fire up to 30 seconds late; for
  critical real-time alerting, pair with a GitHub webhook on `security_advisory` events.

---

## Verification

```bash
# Check D1 for stored advisories
npx wrangler d1 execute advisory-monitor-db \
  --command "SELECT ghsa_id, severity, ecosystem, package_name, alerted_at FROM advisories ORDER BY alerted_at DESC LIMIT 10"

# Manually trigger scheduled run in local dev
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*/15+*+*+*+*"

# Confirm KV bookmark was updated
npx wrangler kv key get --namespace-id=<ID> last_poll_at

# Verify a known GHSA is in D1
npx wrangler d1 execute advisory-monitor-db \
  --command "SELECT * FROM advisories WHERE ghsa_id = 'GHSA-xxxx-xxxx-xxxx'"
```

---

## Related

- `github-security-advisories.md`
- `github-security-advisory-cve-request-and-publication.md`
- `github-advanced-security-sarif-workers-upload.md`
- `github-secret-scanning.md`
- `dependabot-config.md`

---

## Sources

- GitHub REST Advisory API: https://docs.github.com/en/rest/security-advisories/global-advisories
- GitHub GraphQL securityAdvisories: https://docs.github.com/en/graphql/reference/queries#securityadvisories
- GitHub Advisory Database: https://github.com/advisories
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- GHSA identifier spec: https://github.com/github/advisory-database#ghsa-identifiers
