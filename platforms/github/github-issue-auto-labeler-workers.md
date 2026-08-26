# GitHub Issue Auto-Labeler via Cloudflare Workers Webhook

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Incoming GitHub issues arrive without labels, making triage, project board automation, and SLA tracking unreliable.
This article implements a lightweight auto-labeler running as a Cloudflare Worker that classifies new issues by keyword rules and applies labels via the GitHub API.

## Context
GitHub's native label automation requires GitHub Actions (billed minutes) or third-party apps; a Workers webhook handler is always-on with zero cold-start latency on the Cloudflare global network.
The Worker verifies the `X-Hub-Signature-256` HMAC using the `crypto` Web API (no npm dependencies), then matches issue titles and bodies against a configurable rule set stored in a KV namespace.
Labels are applied via the GitHub REST API using a fine-grained PAT or GitHub App installation token stored in Workers Secrets.

---

## Worker Entry Point and Webhook Verification

```typescript
// src/index.ts
import { Env } from './types';
import { verifySignature } from './verify';
import { classifyIssue } from './classify';
import { applyLabels } from './github';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const rawBody = await request.text();

    const valid = await verifySignature(
      rawBody,
      request.headers.get('X-Hub-Signature-256') ?? '',
      env.GITHUB_WEBHOOK_SECRET,
    );
    if (!valid) return new Response('Unauthorized', { status: 401 });

    const event = request.headers.get('X-GitHub-Event');
    if (event !== 'issues') return new Response('Ignored', { status: 200 });

    const payload = JSON.parse(rawBody);
    if (payload.action !== 'opened') return new Response('Not opened', { status: 200 });

    const { number, title, body, labels: existing } = payload.issue;
    const repo = payload.repository.full_name; // "owner/repo"

    const existingNames = (existing as { name: string }[]).map(l => l.name);
    const newLabels = await classifyIssue(title, body ?? '', env, existingNames);

    if (newLabels.length > 0) {
      await applyLabels(repo, number, newLabels, env.GITHUB_TOKEN);
    }

    return new Response(JSON.stringify({ applied: newLabels }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

```typescript
// src/types.ts
export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_TOKEN: string;
  LABEL_RULES: KVNamespace; // optional: dynamic rules stored in KV
}
```

---

## HMAC Signature Verification

```typescript
// src/verify.ts
export async function verifySignature(
  body: string,
  signatureHeader: string,
  secret: string,
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );

  const [, hexSig] = signatureHeader.split('=');
  if (!hexSig) return false;

  const expected = hexToUint8Array(hexSig);
  const data = encoder.encode(body);

  return crypto.subtle.verify('HMAC', key, expected, data);
}

function hexToUint8Array(hex: string): Uint8Array {
  const arr = new Uint8Array(hex.length / 2);
  for (let i = 0; i < arr.length; i++) {
    arr[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return arr;
}
```

---

## Keyword Classification Logic

```typescript
// src/classify.ts
import { Env } from './types';

interface LabelRule {
  label: string;
  keywords: string[];
}

// Default rules — override with KV for per-repo configuration
const DEFAULT_RULES: LabelRule[] = [
  { label: 'bug', keywords: ['error', 'crash', 'broken', 'fail', 'exception', 'traceback'] },
  { label: 'feature', keywords: ['feature request', 'add support', 'would be nice', 'enhance'] },
  { label: 'documentation', keywords: ['docs', 'readme', 'typo', 'unclear', 'example'] },
  { label: 'security', keywords: ['vulnerability', 'cve', 'exploit', 'injection', 'xss', 'csrf'] },
  { label: 'performance', keywords: ['slow', 'latency', 'memory', 'cpu', 'timeout', 'p99'] },
];

export async function classifyIssue(
  title: string,
  body: string,
  env: Env,
  existingLabels: string[],
): Promise<string[]> {
  const text = `${title} ${body}`.toLowerCase();

  // Try to load per-repo rules from KV; fall back to defaults
  let rules: LabelRule[] = DEFAULT_RULES;
  try {
    const kvRules = await env.LABEL_RULES.get('rules', 'json') as LabelRule[] | null;
    if (kvRules) rules = kvRules;
  } catch {
    // KV unavailable; use defaults
  }

  const matched = new Set<string>();
  for (const { label, keywords } of rules) {
    if (existingLabels.includes(label)) continue;
    if (keywords.some(kw => text.includes(kw))) {
      matched.add(label);
    }
  }

  return [...matched];
}
```

---

## Apply Labels via GitHub REST API

```typescript
// src/github.ts
export async function applyLabels(
  repo: string,
  issueNumber: number,
  labels: string[],
  token: string,
): Promise<void> {
  const url = `https://api.github.com/repos/${repo}/issues/${issueNumber}/labels`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'cf-workers-auto-labeler/1.0',
    },
    body: JSON.stringify({ labels }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GitHub API error ${res.status}: ${err}`);
  }
}
```

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "issue-auto-labeler"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "LABEL_RULES"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
# GITHUB_WEBHOOK_SECRET and GITHUB_TOKEN are in Secrets, not vars
```

```bash
# Deploy and register secrets
wrangler secret put GITHUB_WEBHOOK_SECRET
wrangler secret put GITHUB_TOKEN
wrangler deploy
```

Register the Worker URL (`https://issue-auto-labeler.<account>.workers.dev`) as a GitHub webhook for the `issues` event.

---

## Anti-patterns
- Returning 200 before verifying the HMAC — GitHub retries on non-2xx but a forged payload could apply arbitrary labels.
- Storing `GITHUB_TOKEN` as a `[vars]` plain-text binding — always use `wrangler secret put`.
- Using a classic PAT with full `repo` scope — use a fine-grained PAT with `issues:write` on the specific repository only.
- Blocking the event loop with synchronous regex on large issue bodies — use simple `includes()` or `indexOf()` instead of complex patterns.
- Not idempotently skipping already-applied labels — the GitHub API deduplicates label sets, but checking first avoids unnecessary API calls.

## Gotchas
- GitHub sends the webhook with `Content-Type: application/json`; if `application/x-www-form-urlencoded` is selected in the webhook settings, the body format differs.
- The Worker must consume the request body as text BEFORE verifying, then parse — `request.json()` cannot be called after `request.text()`.
- Labels must already exist in the repository; the API returns 422 if a label name is not pre-created.
- Rate limit: the GitHub REST API allows 5000 requests/hour per token — a high-traffic repo may need a GitHub App installation token for higher limits.
- `crypto.subtle` is synchronous in the Web Crypto API spec but the Workers runtime exposes it as async (`Promise`); always `await`.

## Verification
```bash
# Trigger a test webhook delivery from GitHub UI:
# Settings → Webhooks → (your webhook) → Recent Deliveries → Redeliver

# Or simulate locally with curl:
BODY='{"action":"opened","issue":{"number":1,"title":"App crashes on login","body":"Getting a traceback","labels":[]},"repository":{"full_name":"owner/repo"}}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print "sha256="$2}')
curl -X POST https://issue-auto-labeler.<account>.workers.dev \
  -H "X-GitHub-Event: issues" \
  -H "X-Hub-Signature-256: $SIG" \
  -H "Content-Type: application/json" \
  -d "$BODY"
# Expected: {"applied":["bug"]}
```

## Related
- `github-app-webhook-workers-handler.md`
- `github-labels-automation.md`
- `github-issue-forms-workers-intake-automation.md`
- `github-webhook-signing-verification.md`

## Sources
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
- https://docs.github.com/en/rest/issues/labels#add-labels-to-an-issue
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/workers/configuration/secrets/
