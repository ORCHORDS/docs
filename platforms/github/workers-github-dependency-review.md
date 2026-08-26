# Automated Dependency Review Bot with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Engineering teams merge PRs that introduce new npm dependencies without reviewing their licenses, known vulnerabilities, or maintenance status. Manual dependency audits happen inconsistently — or not at all — because they rely on individual reviewer knowledge.

You need a bot that fires on every PR, detects changed `package.json` files, diffs the dependency sets, checks licenses and vulnerability advisories, and posts a blocking comment when high-severity issues are found.

---

## Context

- GitHub emits `pull_request` `opened` / `synchronize` events.
- The GitHub Contents API returns file content at any ref: `GET /repos/{owner}/{repo}/contents/{path}?ref={ref}`.
- The GitHub Dependency Review API (`/repos/{owner}/{repo}/dependency-graph/compare/{base}...{head}`) returns added/removed packages with vulnerability counts. It requires the Dependency Graph to be enabled for the repo.
- License metadata is embedded in the Dependency Review API response.
- Workers KV stores the allowed-license allowlist per org.
- A blocking PR comment is posted via `POST /repos/{owner}/{repo}/issues/{number}/comments`.

---

## Solution

### wrangler.toml

```toml
name = "dependency-review-bot"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[kv_namespaces]]
binding = "POLICY_KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_WEBHOOK_SECRET = "YOUR_WEBHOOK_SECRET"
```

### src/types.ts

```typescript
export interface DependencyReviewEntry {
  package_url: string;
  package: { name: string; ecosystem: string };
  change_type: 'added' | 'removed';
  manifest: string;
  version: string;
  license: string | null;
  vulnerabilities: Array<{
    severity: 'low' | 'moderate' | 'high' | 'critical';
    advisory_ghsa_id: string;
    advisory_summary: string;
    advisory_url: string;
  }>;
}

export interface ReviewPolicy {
  allowedLicenses: string[];     // e.g. ["MIT", "ISC", "Apache-2.0"]
  blockOnSeverity: string[];     // e.g. ["high", "critical"]
  skipEcosystems: string[];      // e.g. ["pip"] — focus only on npm
}

export const DEFAULT_POLICY: ReviewPolicy = {
  allowedLicenses: ['MIT', 'ISC', 'BSD-2-Clause', 'BSD-3-Clause', 'Apache-2.0', '0BSD'],
  blockOnSeverity: ['high', 'critical'],
  skipEcosystems: [],
};
```

### src/github.ts

```typescript
const UA = 'dependency-review-bot/1.0';

export async function fetchDependencyDiff(
  owner: string,
  repo: string,
  base: string,
  head: string,
  token: string,
): Promise<DependencyReviewEntry[]> {
  const url = `https://api.github.com/repos/${owner}/${repo}/dependency-graph/compare/${base}...${head}`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA, Accept: 'application/vnd.github+json' },
  });
  if (!resp.ok) throw new Error(`Dependency review API failed: ${resp.status}`);
  return resp.json() as Promise<DependencyReviewEntry[]>;
}

export async function getPrChangedFiles(
  owner: string,
  repo: string,
  prNumber: number,
  token: string,
): Promise<string[]> {
  const resp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/pulls/${prNumber}/files?per_page=100`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA } },
  );
  const files: Array<{ filename: string }> = await resp.json();
  return files.map(f => f.filename);
}

export async function postComment(
  owner: string,
  repo: string,
  prNumber: number,
  body: string,
  token: string,
): Promise<void> {
  await fetch(`https://api.github.com/repos/${owner}/${repo}/issues/${prNumber}/comments`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': UA,
    },
    body: JSON.stringify({ body }),
  });
}

export async function setCommitStatus(
  owner: string,
  repo: string,
  sha: string,
  state: 'success' | 'failure' | 'pending',
  description: string,
  token: string,
): Promise<void> {
  await fetch(`https://api.github.com/repos/${owner}/${repo}/statuses/${sha}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': UA,
    },
    body: JSON.stringify({
      state,
      description,
      context: 'dependency-review/orchords',
    }),
  });
}
```

### src/review.ts

```typescript
import type { DependencyReviewEntry, ReviewPolicy } from './types';

export interface ReviewResult {
  blocking: boolean;
  findings: string[];
  addedCount: number;
  highSeverityCount: number;
  badLicenseCount: number;
}

export function analyzeEntries(
  entries: DependencyReviewEntry[],
  policy: ReviewPolicy,
): ReviewResult {
  const added = entries.filter(
    e => e.change_type === 'added' && !policy.skipEcosystems.includes(e.package.ecosystem),
  );

  const findings: string[] = [];
  let highSeverityCount = 0;
  let badLicenseCount = 0;

  for (const entry of added) {
    const highVulns = entry.vulnerabilities.filter(v =>
      policy.blockOnSeverity.includes(v.severity),
    );
    if (highVulns.length > 0) {
      highSeverityCount += highVulns.length;
      for (const v of highVulns) {
        findings.push(
          `**[${v.severity.toUpperCase()}]** ${entry.package.name}@${entry.version} — ` +
          `${v.advisory_summary} (${v.advisory_ghsa_id})`,
        );
      }
    }

    if (entry.license && !policy.allowedLicenses.includes(entry.license)) {
      badLicenseCount++;
      findings.push(
        `**[LICENSE]** ${entry.package.name}@${entry.version} uses \`${entry.license}\` ` +
        `which is not in the allowed list (${policy.allowedLicenses.join(', ')}).`,
      );
    }

    if (entry.license === null) {
      findings.push(
        `**[LICENSE]** ${entry.package.name}@${entry.version} has no license information.`,
      );
      badLicenseCount++;
    }
  }

  return {
    blocking: highSeverityCount > 0 || badLicenseCount > 0,
    findings,
    addedCount: added.length,
    highSeverityCount,
    badLicenseCount,
  };
}

export function buildComment(result: ReviewResult, prNumber: number): string {
  const icon = result.blocking ? '🚫' : '✅';
  const status = result.blocking ? 'BLOCKED — action required' : 'Passed';
  const lines = [
    `## Dependency Review — ${icon} ${status}`,
    '',
    `**Added packages:** ${result.addedCount}  `,
    `**High/critical vulnerabilities:** ${result.highSeverityCount}  `,
    `**License violations:** ${result.badLicenseCount}`,
    '',
  ];
  if (result.findings.length > 0) {
    lines.push('### Findings', '');
    for (const f of result.findings) lines.push(`- ${f}`);
    lines.push('');
  }
  if (result.blocking) {
    lines.push(
      '> Merge is discouraged until the findings above are resolved or explicitly waived by a security champion.',
    );
  }
  return lines.join('\n');
}
```

### src/index.ts

```typescript
import { fetchDependencyDiff, getPrChangedFiles, postComment, setCommitStatus } from './github';
import { analyzeEntries, buildComment } from './review';
import { DEFAULT_POLICY, type ReviewPolicy } from './types';

export interface Env {
  POLICY_KV: KVNamespace;
  GITHUB_TOKEN: string;
  GITHUB_WEBHOOK_SECRET: string;
}

async function verifySignature(req: Request, secret: string, body: string): Promise<boolean> {
  const sig = req.headers.get('x-hub-signature-256') ?? '';
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const buf = await crypto.subtle.sign('HMAC', key, enc.encode(body));
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  return sig === `sha256=${hex}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.text();
    if (!(await verifySignature(request, env.GITHUB_WEBHOOK_SECRET, body)))
      return new Response('Unauthorized', { status: 401 });

    const event = request.headers.get('x-github-event');
    if (event !== 'pull_request') return new Response('Ignored', { status: 200 });

    const payload = JSON.parse(body);
    if (!['opened', 'synchronize', 'reopened'].includes(payload.action))
      return new Response('Ignored action', { status: 200 });

    const { pull_request: pr, repository: repo } = payload;
    const owner = repo.owner.login;
    const repoName = repo.name;
    const prNumber: number = payload.number;
    const base: string = pr.base.sha;
    const head: string = pr.head.sha;

    // Only run if package.json was changed
    const changedFiles = await getPrChangedFiles(owner, repoName, prNumber, env.GITHUB_TOKEN);
    const hasPackageJson = changedFiles.some(f => f === 'package.json' || f.endsWith('/package.json'));
    if (!hasPackageJson) return new Response('No package.json changed', { status: 200 });

    // Load policy
    const raw = await env.POLICY_KV.get(`policy:${owner}/${repoName}`);
    const policy: ReviewPolicy = raw ? JSON.parse(raw) : DEFAULT_POLICY;

    // Fetch dependency diff
    const entries = await fetchDependencyDiff(owner, repoName, base, head, env.GITHUB_TOKEN);
    const result = analyzeEntries(entries, policy);
    const comment = buildComment(result, prNumber);

    // Post comment and set commit status
    await Promise.all([
      postComment(owner, repoName, prNumber, comment, env.GITHUB_TOKEN),
      setCommitStatus(
        owner, repoName, head,
        result.blocking ? 'failure' : 'success',
        result.blocking
          ? `${result.highSeverityCount} vuln(s), ${result.badLicenseCount} license issue(s) found`
          : 'All dependency checks passed',
        env.GITHUB_TOKEN,
      ),
    ]);

    return new Response(JSON.stringify(result), { status: 200, headers: { 'Content-Type': 'application/json' } });
  },
};
```

---

## Implementation Details

- **Dependency Review API**: requires the GitHub Advanced Security plan or the repo's dependency graph to be enabled. For public repos it is always available.
- **Commit status vs. required status check**: posting a `failure` status only blocks merge if the status context is listed as a required status check in branch protection rules. Configure `dependency-review/orchords` as required.
- **Comment deduplication**: the bot posts a new comment on every `synchronize` event. For a low-noise experience, search for a previous bot comment by the bot's login before posting, then edit it (`PATCH /repos/{owner}/{repo}/issues/comments/{id}`) instead.
- **File detection**: the `package.json` check ensures the Worker does nothing on PRs that only touch documentation, avoiding unnecessary API calls.
- **Policy in KV**: key pattern `policy:{owner}/{repo}`. Org-level fallback can be `policy:{owner}/*`; implement a two-step KV lookup for that.

---

## Anti-patterns

- **Do not re-implement vulnerability lookup**: the GitHub Dependency Review API already aggregates GitHub Advisory Database data. Do not call a separate Snyk or npm audit endpoint unless the Dependency Review API is unavailable for your plan.
- **Do not block on removed packages**: only `added` entries are relevant for security gating. A PR removing a vulnerable dependency should be celebrated, not blocked.
- **Do not store raw vulnerability data in D1 without TTL**: advisory data changes over time. Store only counts and GHSA IDs; re-fetch details on demand.
- **Do not omit the `Accept` header**: the Dependency Review API is behind a preview header in older API versions; always pass `application/vnd.github+json`.

---

## Gotchas

- The Dependency Review API compares dependency graphs between two SHAs, not between branch tips. Use `pr.base.sha` and `pr.head.sha` from the webhook payload — not branch names — to get a stable comparison.
- GitHub rate-limits the Dependency Review API more aggressively than the core REST API. On monorepos with many `package.json` files, the diff may be large; cache the result in KV for 5 minutes keyed by `{base}...{head}`.
- Workers have a 30-second CPU time limit on paid plans (50ms on free). The `postComment` + `setCommitStatus` parallel calls should complete in under 2 seconds over the GitHub API; the dependency diff fetch can take up to 5 seconds for large repos. Total round-trip should stay well within budget.
- `peerDependencies` are not counted in additions/deletions by the Dependency Review API. Peer dep conflicts must be caught by CI `npm install` steps, not by this bot.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Set KV policy for a repo
npx wrangler kv key put 'policy:example-org/example-repo' \
  '{"allowedLicenses":["MIT","ISC","Apache-2.0"],"blockOnSeverity":["high","critical"],"skipEcosystems":[]}' \
  --binding POLICY_KV

# Simulate webhook with a curl call
curl -X POST https://dependency-review-bot.YOUR_SUBDOMAIN.workers.dev \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: pull_request' \
  -H 'X-Hub-Signature-256: sha256=COMPUTED_SIG' \
  -d @test/fixtures/pr_opened.json

# Check commit status on the PR head SHA
gh api repos/example-org/example-repo/commits/HEAD/statuses
```

---

## Related

- `documentation/categories/github/workers-github-pr-size-labeler.md`
- `documentation/categories/github/workers-github-commit-signing-verification.md`
- GitHub Dependency Review API: https://docs.github.com/en/rest/dependency-graph/dependency-review
- GitHub Advisory Database: https://github.com/advisories

---

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/kv/
- https://docs.github.com/en/rest/dependency-graph/dependency-review
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request
- https://docs.github.com/en/rest/commits/statuses
