# Branch Protection Rule Enforcement via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

New repositories created in a GitHub organization frequently miss required branch protection rules — requiring code review, status checks, or signed commits. You need a Cloudflare Worker that:

1. Receives GitHub org webhooks for `repository.created` events and immediately applies a standard protection ruleset.
2. Runs on a schedule (Cron Trigger) to audit all repos for compliance drift.
3. Reports violations to Slack.
4. Writes an audit log of every protection change to D1.

## Context

GitHub's Branch Protection API (`PUT /repos/{owner}/{repo}/branches/{branch}/protection`) accepts a JSON body describing the full ruleset. GitHub Apps with the `Administration` permission (write) can call this endpoint for any repo in an org installation.

The Worker handles two execution contexts:

- **Webhook path** (`POST /webhook`) — responds in < 10 s by enqueuing heavy work with `waitUntil`.
- **Scheduled path** (`scheduled` export) — runs on a Cron Trigger (e.g., daily at 06:00 UTC), iterates all repos, checks compliance, reports gaps.

All mutations are logged in D1 for SOC-2 / audit purposes.

## Solution

```typescript
// src/index.ts
export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_APP_ID: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_APP_INSTALLATION_ID: string;
  GITHUB_ORG: string;
  DB: D1Database;
  SLACK_WEBHOOK_URL: string;
}

interface RepoEvent {
  action: string;
  repository: { name: string; default_branch: string; full_name: string };
}

interface GitHubRepo {
  name: string;
  default_branch: string;
  archived: boolean;
  fork: boolean;
}

interface BranchProtection {
  required_status_checks: {
    strict: boolean;
    contexts: string[];
  } | null;
  required_pull_request_reviews: {
    required_approving_review_count: number;
    dismiss_stale_reviews: boolean;
    require_code_owner_reviews: boolean;
  } | null;
  restrictions: null;
  enforce_admins: boolean;
  required_linear_history: boolean;
  allow_force_pushes: boolean;
  allow_deletions: boolean;
  required_conversation_resolution: boolean;
}

// Standard ruleset applied to all default branches
const REQUIRED_PROTECTION: BranchProtection = {
  required_status_checks: { strict: true, contexts: ['ci/tests', 'ci/lint'] },
  required_pull_request_reviews: {
    required_approving_review_count: 1,
    dismiss_stale_reviews: true,
    require_code_owner_reviews: false,
  },
  restrictions: null,
  enforce_admins: true,
  required_linear_history: true,
  allow_force_pushes: false,
  allow_deletions: false,
  required_conversation_resolution: true,
};

// --- GitHub App JWT + installation token (reuse pattern from release automation) ---
async function getInstallationToken(env: Env): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload = { iat: now - 60, exp: now + 600, iss: env.GITHUB_APP_ID };
  const pemContents = env.GITHUB_APP_PRIVATE_KEY.replace(
    /-----(?:BEGIN|END) RSA PRIVATE KEY-----/g,
    '',
  ).replace(/\s/g, '');
  const keyData = Uint8Array.from(atob(pemContents), (c) => c.charCodeAt(0));
  const privateKey = await crypto.subtle.importKey(
    'pkcs8',
    keyData,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const enc = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const header = enc({ alg: 'RS256', typ: 'JWT' });
  const body = enc(payload);
  const sig = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    privateKey,
    new TextEncoder().encode(`${header}.${body}`),
  );
  const jwt =
    `${header}.${body}.` +
    btoa(String.fromCharCode(...new Uint8Array(sig)))
      .replace(/=/g, '')
      .replace(/\+/g, '-')
      .replace(/\//g, '_');

  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_APP_INSTALLATION_ID}/access_tokens`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'orchords-protection-enforcer/1.0',
      },
    },
  );
  const { token } = (await res.json()) as { token: string };
  return token;
}

function ghHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'orchords-protection-enforcer/1.0',
    'Content-Type': 'application/json',
  };
}

// --- Apply protection to a single repo ---
async function applyProtection(
  token: string,
  owner: string,
  repo: string,
  branch: string,
  db: D1Database,
  reason: string,
): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/branches/${branch}/protection`,
    {
      method: 'PUT',
      headers: ghHeaders(token),
      body: JSON.stringify(REQUIRED_PROTECTION),
    },
  );
  const status = res.ok ? 'applied' : 'failed';
  await db
    .prepare(
      `INSERT INTO protection_audit (owner, repo, branch, status, reason, applied_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`,
    )
    .bind(owner, repo, branch, status, reason)
    .run();
  if (!res.ok) {
    throw new Error(
      `Failed to apply protection to ${owner}/${repo}@${branch}: ${await res.text()}`,
    );
  }
}

// --- Check compliance of a single repo ---
interface ComplianceResult {
  compliant: boolean;
  violations: string[];
}

async function checkCompliance(
  token: string,
  owner: string,
  repo: string,
  branch: string,
): Promise<ComplianceResult> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/branches/${branch}/protection`,
    { headers: ghHeaders(token) },
  );
  if (res.status === 404) {
    return { compliant: false, violations: ['No branch protection configured'] };
  }
  const protection = (await res.json()) as {
    required_pull_request_reviews?: { required_approving_review_count: number };
    allow_force_pushes?: { enabled: boolean };
    allow_deletions?: { enabled: boolean };
    required_linear_history?: { enabled: boolean };
    enforce_admins?: { enabled: boolean };
  };

  const violations: string[] = [];
  if (!protection.required_pull_request_reviews) violations.push('No PR review requirement');
  if ((protection.required_pull_request_reviews?.required_approving_review_count ?? 0) < 1)
    violations.push('Requires at least 1 approving review');
  if (protection.allow_force_pushes?.enabled) violations.push('Force pushes allowed');
  if (protection.allow_deletions?.enabled) violations.push('Branch deletions allowed');
  if (!protection.enforce_admins?.enabled) violations.push('Admins not subject to protections');

  return { compliant: violations.length === 0, violations };
}

// --- List all org repos (paginated) ---
async function listOrgRepos(token: string, org: string): Promise<GitHubRepo[]> {
  const repos: GitHubRepo[] = [];
  let page = 1;
  while (true) {
    const res = await fetch(
      `https://api.github.com/orgs/${org}/repos?per_page=100&page=${page}`,
      { headers: ghHeaders(token) },
    );
    const batch = (await res.json()) as GitHubRepo[];
    if (!Array.isArray(batch) || batch.length === 0) break;
    repos.push(...batch);
    page++;
  }
  return repos;
}

// --- HMAC webhook verification ---
async function verifySignature(secret: string, sig: string, body: ArrayBuffer): Promise<void> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, body);
  const expected =
    'sha256=' +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  if (expected !== sig) throw new Error('Bad signature');
}

// --- Main export ---
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const rawBody = await request.arrayBuffer();
    await verifySignature(
      env.GITHUB_WEBHOOK_SECRET,
      request.headers.get('X-Hub-Signature-256') ?? '',
      rawBody,
    );

    const ghEvent = request.headers.get('X-GitHub-Event');
    if (ghEvent !== 'repository') return new Response('Ignored', { status: 200 });

    const payload = JSON.parse(new TextDecoder().decode(rawBody)) as RepoEvent;
    if (payload.action !== 'created') return new Response('Ignored', { status: 200 });

    const { repository: { name: repo, default_branch } } = payload;

    ctx.waitUntil(
      (async () => {
        const token = await getInstallationToken(env);
        await applyProtection(
          token,
          env.GITHUB_ORG,
          repo,
          default_branch,
          env.DB,
          'repository.created webhook',
        );
      })(),
    );

    return new Response('Protection scheduled', { status: 202 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      (async () => {
        const token = await getInstallationToken(env);
        const repos = await listOrgRepos(token, env.GITHUB_ORG);
        const violations: string[] = [];

        for (const repo of repos) {
          if (repo.archived || repo.fork) continue;
          const { compliant, violations: v } = await checkCompliance(
            token,
            env.GITHUB_ORG,
            repo.name,
            repo.default_branch,
          );
          if (!compliant) {
            violations.push(`*${repo.name}* (${repo.default_branch}): ${v.join(', ')}`);
            // Auto-remediate
            await applyProtection(
              token,
              env.GITHUB_ORG,
              repo.name,
              repo.default_branch,
              env.DB,
              'scheduled compliance audit',
            ).catch((e) => violations.push(`  Remediation failed: ${(e as Error).message}`));
          }
        }

        if (violations.length > 0) {
          await fetch(env.SLACK_WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              text: `:shield: *Branch protection audit — ${violations.length} violation(s) found and remediated*`,
              attachments: [{ color: '#e01e5a', text: violations.slice(0, 20).join('\n') }],
            }),
          });
        }
      })(),
    );
  },
};
```

## Implementation Details

**D1 audit schema**:

```sql
CREATE TABLE IF NOT EXISTS protection_audit (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner      TEXT    NOT NULL,
  repo       TEXT    NOT NULL,
  branch     TEXT    NOT NULL,
  status     TEXT    NOT NULL, -- 'applied' | 'failed'
  reason     TEXT    NOT NULL,
  applied_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_repo ON protection_audit(owner, repo);
```

**wrangler.toml**:

```toml
[triggers]
crons = ["0 6 * * *"]

[[d1_databases]]
binding       = "DB"
database_name = "branch-protection-audit"
database_id   = "<your-id>"

[vars]
GITHUB_ORG = "orchords"
```

## Anti-patterns

- Do not apply protection rules synchronously in the webhook handler — GitHub has a 10-second delivery timeout and `PUT /branches/{branch}/protection` can be slow.
- Do not skip archived or forked repos — they cannot have protection rules applied and will return 403.
- Do not hard-code required status check contexts; drive them from a KV config so teams can customize per-repo without a Worker redeploy.
- Do not log raw GitHub API responses to D1 — they contain sensitive metadata; store only what the audit schema requires.

## Gotchas

- Newly created repos may not yet have a default branch — wait for the `push` event (first commit) before applying protection, or check `default_branch` is not `null`.
- GitHub Enterprise Cloud uses `required_signatures` on a separate endpoint; it is not part of the main protection PUT body.
- The `enforce_admins` field in the GET response is nested as `{ enabled: boolean }`, but in the PUT request body it is a plain boolean.
- Rate limits: listing 1 000 repos costs 10 API calls (100 per page); compliance checks cost 1 call per repo. With 200 repos, you consume ~210 calls — well within the 5 000/hour App limit.

## Verification

```bash
# Create a test repo and watch the log
gh repo create example-org/example-repo --private
wrangler tail --format=pretty

# Query audit log
wrangler d1 execute branch-protection-audit \
  --command "SELECT * FROM protection_audit ORDER BY applied_at DESC LIMIT 10" \
  --remote
```

## Related

- `documentation/docs/policies/github/workers-github-release-automation.md`
- `documentation/docs/policies/github/workers-github-dependency-update-bot.md`
- `documentation/docs/policies/cloudflare/workers-cron-triggers.md`

## Sources

- https://docs.github.com/en/rest/branches/branch-protection
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#repository
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
