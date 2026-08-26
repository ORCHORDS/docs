# Auto-merging Dependabot PRs via a GitHub App Worker

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Dependabot opens dozens of dependency update PRs each week, and manually reviewing and merging patch and minor version bumps consumes significant engineering time. A GitHub App Worker can listen for `pull_request` and `check_suite` events, verify that the PR is from Dependabot, that CI passes, and that the version bump is patch or minor, then automatically merge it — logging each action to D1 for auditing.

---

## Context
Dependabot PRs are identifiable by `sender.login === "dependabot[bot]"` in the webhook payload. The version bump type is encoded in PR labels: `dependencies`, `patch`, `minor`, or `major`. Merging should only occur after CI checks complete successfully — the `check_suite` event with `conclusion === "success"` is the correct trigger, not the `pull_request.opened` event. The Worker cross-references the PR number from the check suite's associated PRs, retrieves the PR details to validate Dependabot authorship and labels, then calls the GitHub Merge API. All merge decisions are logged to a D1 table for compliance review.

---

## Section 1 — Worker and D1 Configuration (`wrangler.toml`)
```toml
name = "dependabot-auto-merge"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "MERGE_LOG"
database_name = "dependabot-merge-log"
database_id = "YOUR_D1_DATABASE_ID"

[[kv_namespaces]]
binding = "INSTALLATION_TOKENS"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_APP_ID = "123456"
ALLOWED_REPOS = "owner/repo1,owner/repo2"

[secrets]
# wrangler secret put GITHUB_WEBHOOK_SECRET
# wrangler secret put GITHUB_APP_PRIVATE_KEY
```

## Section 2 — D1 Schema and Event Router
```typescript
// src/schema.sql (run once via: wrangler d1 execute MERGE_LOG --file=src/schema.sql)
// CREATE TABLE IF NOT EXISTS merge_log (
//   id INTEGER PRIMARY KEY AUTOINCREMENT,
//   repo TEXT NOT NULL,
//   pr_number INTEGER NOT NULL,
//   pr_title TEXT NOT NULL,
//   bump_type TEXT NOT NULL,
//   sha TEXT NOT NULL,
//   merged_at TEXT NOT NULL,
//   skipped_reason TEXT
// );

// src/index.ts
export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_APP_ID: string;
  ALLOWED_REPOS: string;
  INSTALLATION_TOKENS: KVNamespace;
  MERGE_LOG: D1Database;
}

async function verifySignature(secret: string, signature: string | null, body: ArrayBuffer): Promise<boolean> {
  if (!signature?.startsWith('sha256=')) return false;
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = await crypto.subtle.sign('HMAC', key, body);
  const actual = Array.from(new Uint8Array(mac)).map(b => b.toString(16).padStart(2, '0')).join('');
  const expected = signature.slice(7);
  if (actual.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < actual.length; i++) diff |= actual.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const rawBody = await request.arrayBuffer();
    if (!await verifySignature(env.GITHUB_WEBHOOK_SECRET, request.headers.get('X-Hub-Signature-256'), rawBody)) {
      return new Response('Unauthorized', { status: 401 });
    }

    const event = request.headers.get('X-GitHub-Event') ?? '';
    const payload = JSON.parse(new TextDecoder().decode(rawBody));

    if (event === 'check_suite' && payload.action === 'completed') {
      await handleCheckSuite(payload, env);
    }

    return new Response('OK', { status: 200 });
  },
};
```

## Section 3 — Auto-merge Handler with D1 Logging
```typescript
// src/auto-merge.ts
import { Env } from './index';

const DEPENDABOT_LOGIN = 'dependabot[bot]';
const SAFE_LABELS = new Set(['patch', 'minor']);
const DEPENDENCIES_LABEL = 'dependencies';

async function getInstallationToken(installationId: number, env: Env): Promise<string> {
  const cached = await env.INSTALLATION_TOKENS.get(`install-token:${installationId}`);
  if (cached) return cached;

  const now = Math.floor(Date.now() / 1000);
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const claims = btoa(JSON.stringify({ iat: now - 60, exp: now + 540, iss: env.GITHUB_APP_ID })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const pemBody = env.GITHUB_APP_PRIVATE_KEY.replace(/-----[^-]+-----|\s/g, '');
  const keyBytes = Uint8Array.from(atob(pemBody), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey('pkcs8', keyBytes, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(`${header}.${claims}`));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const jwt = `${header}.${claims}.${sigB64}`;

  const res = await fetch(`https://api.github.com/app/installations/${installationId}/access_tokens`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${jwt}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'orchords-dependabot-merger/1.0' },
  });

  const { token } = await res.json<{ token: string }>();
  await env.INSTALLATION_TOKENS.put(`install-token:${installationId}`, token, { expirationTtl: 3300 });
  return token;
}

export async function handleCheckSuite(payload: any, env: Env): Promise<void> {
  const { check_suite, repository, installation } = payload;

  if (check_suite.conclusion !== 'success') return;
  if (!installation) return;

  const allowedRepos = env.ALLOWED_REPOS.split(',').map(r => r.trim());
  if (!allowedRepos.includes(repository.full_name)) return;

  const prs: any[] = check_suite.pull_requests ?? [];
  if (prs.length === 0) return;

  const token = await getInstallationToken(installation.id, env);
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'orchords-dependabot-merger/1.0',
  };

  for (const prRef of prs) {
    const prRes = await fetch(
      `https://api.github.com/repos/${repository.full_name}/pulls/${prRef.number}`,
      { headers: authHeaders }
    );
    const pr = await prRes.json<any>();

    const isDependabot = pr.user?.login === DEPENDABOT_LOGIN;
    const labels: string[] = (pr.labels ?? []).map((l: any) => l.name);
    const hasDependenciesLabel = labels.includes(DEPENDENCIES_LABEL);
    const bumpType = labels.find(l => SAFE_LABELS.has(l));
    const isMergeable = pr.mergeable === true && pr.state === 'open';

    if (!isDependabot || !hasDependenciesLabel || !bumpType || !isMergeable) {
      await logMerge(env, repository.full_name, pr, bumpType ?? 'unknown', check_suite.head_sha,
        !isDependabot ? 'not-dependabot' :
        !hasDependenciesLabel ? 'no-dependencies-label' :
        !bumpType ? 'major-bump-skipped' : 'not-mergeable');
      continue;
    }

    const mergeRes = await fetch(
      `https://api.github.com/repos/${repository.full_name}/pulls/${pr.number}/merge`,
      {
        method: 'PUT',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          commit_title: `chore(deps): merge dependabot PR #${pr.number}`,
          commit_message: pr.title,
          merge_method: 'squash',
          sha: pr.head.sha,
        }),
      }
    );

    if (mergeRes.ok) {
      console.log(`Merged PR #${pr.number} (${bumpType}) in ${repository.full_name}`);
      await logMerge(env, repository.full_name, pr, bumpType, check_suite.head_sha, null);
    } else {
      const err = await mergeRes.text();
      console.error(`Failed to merge PR #${pr.number}: ${err}`);
      await logMerge(env, repository.full_name, pr, bumpType, check_suite.head_sha, `merge-failed: ${err}`);
    }
  }
}

async function logMerge(
  env: Env,
  repo: string,
  pr: any,
  bumpType: string,
  sha: string,
  skippedReason: string | null
): Promise<void> {
  await env.MERGE_LOG.prepare(
    `INSERT INTO merge_log (repo, pr_number, pr_title, bump_type, sha, merged_at, skipped_reason)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).bind(repo, pr.number, pr.title, bumpType, sha, new Date().toISOString(), skippedReason).run();
}
```

---

## Anti-patterns
- **Merging on `pull_request.opened`** — CI has not run yet; always wait for `check_suite.completed` with `conclusion === "success"`.
- **Merging without verifying `pr.mergeable`** — The GitHub API sets `mergeable: null` while computing mergeability; merging without checking leads to failed merges or conflicts.
- **Allowing `major` version bumps** — Major bumps may introduce breaking changes; restrict auto-merge to `patch` and `minor` labels only.
- **Not checking `pr.head.sha` on merge** — Always pass the `sha` field to the merge API to guard against a PR head changing between check completion and merge.
- **Skipping the `ALLOWED_REPOS` allowlist** — Without a repo allowlist, the Worker will attempt to auto-merge Dependabot PRs across every installed repository.

---

## Gotchas
- Dependabot's login in webhook payloads is `dependabot[bot]` (with brackets), not `dependabot`.
- The `check_suite.pull_requests` array may be empty if the branch was pushed without an open PR; handle the empty case.
- GitHub's merge API returns 405 if branch protection rules require reviews; configure the App with `bypass_pull_request_allowances` in branch protection if auto-merge should bypass review requirements.
- `pr.mergeable` can return `null` (pending computation); implement a short retry or rely on the merge API error response.
- D1 `INSERT` failures should not block the merge response; wrap in try/catch and log separately.

---

## Verification
```bash
# Create D1 schema
wrangler d1 execute MERGE_LOG --file=src/schema.sql

# Query merge log
wrangler d1 execute MERGE_LOG --command "SELECT * FROM merge_log ORDER BY merged_at DESC LIMIT 10"

# Simulate a check_suite success event (replace values as needed)
curl -X POST https://your-worker.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: check_suite" \
  -H "X-Hub-Signature-256: sha256=$(echo -n '{"action":"completed"}' | openssl dgst -sha256 -hmac 'secret' | awk '{print $2}')" \
  -d '{"action":"completed","check_suite":{"conclusion":"success","head_sha":"abc123","pull_requests":[{"number":42}]},"repository":{"full_name":"owner/repo"},"installation":{"id":1}}'

# Verify Worker logs
wrangler tail
```

---

## Related
- `github-app-webhook-workers-installation.md`
- `github-deployment-status-workers-cloudflare.md`

---

## Sources
- GitHub Dependabot documentation — https://docs.github.com/en/code-security/dependabot/working-with-dependabot/automating-dependabot-with-github-actions
- GitHub Pulls merge API — https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
- GitHub check_suite webhook event — https://docs.github.com/en/webhooks/webhook-events-and-payloads#check_suite
- Cloudflare D1 — https://developers.cloudflare.com/d1/
