# Commit Signature Verification Enforcement Bot with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your organization requires all commits to be GPG- or SSH-signed to guarantee author authenticity and prevent commit forgery. GitHub's native branch protection does not expose a "require signed commits" option that also allows per-repo exceptions or CI bot bypasses without disabling the rule globally.

You need a custom enforcement bot that fires on every `push` event, checks each new commit's signature status via the GitHub API, posts a comment on related PRs when unsigned commits are detected, and respects a bot-bypass list stored in KV — all without touching branch protection rules.

---

## Context

- GitHub emits a `push` webhook event for every ref push containing the before/after SHAs.
- The Commits API (`GET /repos/{owner}/{repo}/commits/{ref}`) returns a `commit.verification` object with `verified`, `reason`, and `signature` fields.
- GPG-signed commits have `reason: "valid"` and `verified: true`.
- CI bots (GitHub Actions, Renovate, Dependabot) push commits without signatures by design. These must be bypassed by login.
- Workers KV stores two data structures: the repo signing policy and the bot bypass list.
- Comments are posted to open PRs targeting the same base branch, looked up via the Search API.

---

## Solution

### wrangler.toml

```toml
name = "commit-signing-enforcer"
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
export interface CommitVerification {
  verified: boolean;
  reason: string;
  signature: string | null;
  payload: string | null;
}

export interface GitHubCommitDetail {
  sha: string;
  author: { login?: string; type?: string } | null;
  commit: {
    author: { name: string; email: string };
    message: string;
    verification: CommitVerification;
  };
}

export interface SigningPolicy {
  enabled: boolean;
  requiredReasons: string[];   // e.g. ["valid"] — accepted verification reasons
  bypassLogins: string[];      // GitHub logins exempt from signing (bots, CI)
  notifyOnViolation: boolean;  // post PR comment when unsigned commit found
}

export const DEFAULT_POLICY: SigningPolicy = {
  enabled: true,
  requiredReasons: ['valid'],
  bypassLogins: ['github-actions[bot]', 'renovate[bot]', 'dependabot[bot]'],
  notifyOnViolation: true,
};

export interface PushPayload {
  ref: string;
  before: string;
  after: string;
  commits: Array<{ id: string; author: { username?: string }; message: string }>;
  repository: { owner: { login: string }; name: string };
  sender: { login: string; type: string };
}
```

### src/github.ts

```typescript
const UA = 'commit-signing-enforcer/1.0';

export async function getCommitDetail(
  owner: string,
  repo: string,
  sha: string,
  token: string,
): Promise<GitHubCommitDetail> {
  const resp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/commits/${sha}`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA } },
  );
  if (!resp.ok) throw new Error(`getCommit ${sha} → ${resp.status}`);
  return resp.json() as Promise<GitHubCommitDetail>;
}

export async function findOpenPrsForBranch(
  owner: string,
  repo: string,
  branch: string,
  token: string,
): Promise<number[]> {
  const q = encodeURIComponent(`repo:${owner}/${repo} type:pr state:open head:${branch}`);
  const resp = await fetch(
    `https://api.github.com/search/issues?q=${q}&per_page=10`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': UA } },
  );
  if (!resp.ok) return [];
  const data: { items: Array<{ number: number }> } = await resp.json();
  return data.items.map(i => i.number);
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
```

### src/signing.ts

```typescript
import type { GitHubCommitDetail, SigningPolicy } from './types';

export interface ViolatingCommit {
  sha: string;
  shortSha: string;
  author: string;
  reason: string;
  message: string;
}

export function findViolations(
  commits: GitHubCommitDetail[],
  policy: SigningPolicy,
): ViolatingCommit[] {
  const violations: ViolatingCommit[] = [];
  for (const c of commits) {
    const login = c.author?.login ?? c.commit.author.name;
    if (policy.bypassLogins.includes(login)) continue;
    if (c.author?.type === 'Bot') continue;

    const { verified, reason } = c.commit.verification;
    const acceptable = verified && policy.requiredReasons.includes(reason);
    if (!acceptable) {
      violations.push({
        sha: c.sha,
        shortSha: c.sha.slice(0, 7),
        author: login,
        reason,
        message: c.commit.message.split('\n')[0].slice(0, 72),
      });
    }
  }
  return violations;
}

export function buildViolationComment(violations: ViolatingCommit[], branch: string): string {
  const rows = violations
    .map(v => `| \`${v.shortSha}\` | ${v.author} | \`${v.reason}\` | ${v.message} |`)
    .join('\n');
  return [
    '## Commit Signature Enforcement — Unsigned Commits Detected',
    '',
    `The following commits pushed to \`${branch}\` are not GPG/SSH-signed or have an invalid signature:`,
    '',
    '| Commit | Author | Verification reason | Message |',
    '|--------|--------|---------------------|---------|',
    rows,
    '',
    '**Action required:** Re-sign the commits above and force-push the branch.',
    '',
    '```bash',
    '# Re-sign all commits in the branch interactively',
    'git rebase --exec "git commit --amend --no-edit --gpg-sign" origin/main',
    'git push --force-with-lease',
    '```',
    '',
    '> This check is enforced by the example.com commit-signing-enforcer bot.',
  ].join('\n');
}
```

### src/index.ts

```typescript
import { getCommitDetail, findOpenPrsForBranch, postComment } from './github';
import { findViolations, buildViolationComment } from './signing';
import { DEFAULT_POLICY, type PushPayload, type SigningPolicy } from './types';

export interface Env {
  POLICY_KV: KVNamespace;
  GITHUB_TOKEN: string;
  GITHUB_WEBHOOK_SECRET: string;
}

async function verifySignature(req: Request, secret: string, body: string): Promise<boolean> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const buf = await crypto.subtle.sign('HMAC', key, enc.encode(body));
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
  return (req.headers.get('x-hub-signature-256') ?? '') === `sha256=${hex}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.text();
    if (!(await verifySignature(request, env.GITHUB_WEBHOOK_SECRET, body)))
      return new Response('Unauthorized', { status: 401 });

    if (request.headers.get('x-github-event') !== 'push')
      return new Response('Ignored', { status: 200 });

    const payload: PushPayload = JSON.parse(body);
    const { ref, commits, repository: repo, sender } = payload;

    // Only process branch pushes (not tag pushes)
    if (!ref.startsWith('refs/heads/')) return new Response('Not a branch push', { status: 200 });
    const branch = ref.replace('refs/heads/', '');
    const owner = repo.owner.login;
    const repoName = repo.name;

    // Load policy from KV
    const raw = await env.POLICY_KV.get(`signing:${owner}/${repoName}`);
    const policy: SigningPolicy = raw ? JSON.parse(raw) : DEFAULT_POLICY;
    if (!policy.enabled) return new Response('Signing check disabled', { status: 200 });

    // Bypass entire push if the sender is a known bot
    if (policy.bypassLogins.includes(sender.login) || sender.type === 'Bot')
      return new Response('Bot sender bypassed', { status: 200 });

    // Fetch full commit details in parallel (max 20 commits per push event)
    const shas = commits.map(c => c.id).slice(0, 20);
    const details = await Promise.all(
      shas.map(sha => getCommitDetail(owner, repoName, sha, env.GITHUB_TOKEN)),
    );

    const violations = findViolations(details, policy);
    if (violations.length === 0) return new Response('All commits signed', { status: 200 });

    if (!policy.notifyOnViolation)
      return new Response(`${violations.length} unsigned commit(s) found, notification disabled`, { status: 200 });

    // Find open PRs for this branch and post comment
    const prNumbers = await findOpenPrsForBranch(owner, repoName, branch, env.GITHUB_TOKEN);
    const comment = buildViolationComment(violations, branch);

    await Promise.all(
      prNumbers.map(prNumber => postComment(owner, repoName, prNumber, comment, env.GITHUB_TOKEN)),
    );

    return new Response(
      JSON.stringify({ violations: violations.length, notified: prNumbers }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  },
};
```

---

## Implementation Details

- **Verification reasons**: GitHub returns a `reason` string even when `verified` is false. Common unverified reasons: `unsigned`, `no_user`, `unverified_email`, `bad_email`, `unknown_key`, `malformed_signature`. The policy `requiredReasons` array should list only `"valid"` for strict enforcement.
- **SSH signatures**: GitHub supports SSH commit signing since 2022. SSH-signed commits also return `verified: true` with `reason: "valid"`. No special handling required.
- **Parallel commit fetching**: Each commit requires one API call. A push can contain up to 20 commits per webhook event (GitHub pages after 20). Process in parallel with `Promise.all`; stay within the 6,000-request/hour rate limit for GitHub Apps.
- **Branch bypass**: For protected branches like `main`, you may want to skip enforcement and rely on branch protection's "Require signed commits" setting instead. Use the `bypassBranches` policy field to exclude those.
- **PR search latency**: After a push, the PR search index may have up to 30-second staleness. If no PRs are found, that is acceptable — the next push to the branch will retry.

---

## Anti-patterns

- **Do not fetch the diff to verify the signature**: the signature is on the commit object itself. Use the `GET /commits/{sha}` endpoint, not the diff API.
- **Do not process `push` events on `refs/tags/*`**: tag objects have different signing semantics and the PR search for a tag is meaningless.
- **Do not store the signature payload in KV**: it can be megabytes. Store only violation counts or short SHA lists for audit purposes.
- **Do not block the `default_branch` push**: the bot posts comments on PRs. If no PR exists for a direct push to `main`, silently log the violation rather than returning a 4xx (which would cause GitHub to alert the pusher).

---

## Gotchas

- GitHub's commit verification requires the signer's GPG/SSH key to be registered in their GitHub account. A valid GPG signature from an unregistered key returns `reason: "unknown_key"` and `verified: false`.
- The `push` webhook event payload includes only the commits in that push batch (max 20). If a force-push rewrites many commits, only the incremental 20 are in the webhook. For completeness, compare `before` and `after` SHAs and enumerate commits between them using the Compare API if needed.
- The Worker's `x-hub-signature-256` verification uses the raw request body as-is. Do not parse JSON before verification — string equality on the body matters.
- Workers KV has ~60-second eventual consistency. A policy update (e.g., adding a new bot to `bypassLogins`) may not take effect immediately across all PoPs.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Set signing policy for a repo
npx wrangler kv key put 'signing:example-org/example-repo' \
  '{"enabled":true,"requiredReasons":["valid"],"bypassLogins":["github-actions[bot]","renovate[bot]"],"notifyOnViolation":true}' \
  --binding POLICY_KV

# Trigger a test by pushing an unsigned commit to a branch with an open PR
git commit --no-gpg-sign -m 'test: unsigned commit' --allow-empty
git push origin HEAD:refs/heads/test-signing

# Confirm the bot posted a comment on the PR
gh pr view --json comments --jq '.comments[-1].body' $(gh pr list --head test-signing --json number --jq '.[0].number')
```

---

## Related

- `documentation/categories/github/workers-github-dependency-review.md`
- `documentation/categories/github/workers-github-repo-archival-bot.md`
- GitHub commit signature verification: https://docs.github.com/en/authentication/managing-commit-signature-verification
- GitHub Commits API: https://docs.github.com/en/rest/commits/commits

---

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/kv/
- https://docs.github.com/en/rest/commits/commits
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#push
- https://docs.github.com/en/authentication/managing-commit-signature-verification/checking-for-existing-gpg-keys
