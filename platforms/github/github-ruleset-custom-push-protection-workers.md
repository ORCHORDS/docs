# GitHub Ruleset Custom Push Protection via Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your organization needs push protection rules beyond what GitHub's built-in
secret scanning patterns cover — for example, blocking commits that include
proprietary API key formats, internal IP ranges, or employee badge numbers.
GitHub Rulesets support a "Custom Push Protection" hook (via a repository or
organization custom deployment protection rule) that calls an external HTTP
endpoint. A Cloudflare Worker is the ideal host: globally distributed, sub-5ms
cold start, no infrastructure to manage.

## Context

GitHub's custom push protection calls a user-supplied HTTPS endpoint when a
push is attempted. The endpoint receives a JSON payload describing the pushed
commits and files and must respond within 10 seconds with `{ "pass": true }` or
`{ "pass": false, "message": "..." }`. The endpoint URL is registered as a
Repository Rule (type `push`) with `parameters.restrict_file_pushes` or via
the "Custom push protection" rule type in Organization Rulesets (GA in 2025).

## Worker Handler

```typescript
// src/index.ts
export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  BLOCKED_PATTERNS_KV: KVNamespace; // patterns stored in KV
}

interface PushProtectionPayload {
  installation: { id: number };
  repository: { full_name: string };
  pusher: { login: string };
  commits: Array<{
    id: string;
    message: string;
    added: string[];
    modified: string[];
    removed: string[];
  }>;
  blobs: Array<{ path: string; content: string }>;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await req.text();
    if (!(await verifyHmac(env.GITHUB_WEBHOOK_SECRET, body, req.headers.get("X-Hub-Signature-256")))) {
      return new Response("Unauthorized", { status: 401 });
    }

    const payload: PushProtectionPayload = JSON.parse(body);
    const violation = await checkViolations(payload, env);

    if (violation) {
      return Response.json({ pass: false, message: violation }, { status: 200 });
    }
    return Response.json({ pass: true }, { status: 200 });
  },
};
```

## Pattern Matching Against Blobs

```typescript
// src/checker.ts
export interface PatternConfig {
  id: string;
  pattern: string;   // regex string
  message: string;
  severity: "block" | "warn";
}

export async function checkViolations(
  payload: PushProtectionPayload,
  env: Env,
): Promise<string | null> {
  const rawPatterns = await env.BLOCKED_PATTERNS_KV.get("patterns", "json") as PatternConfig[] | null;
  const patterns: PatternConfig[] = rawPatterns ?? DEFAULT_PATTERNS;

  for (const blob of payload.blobs ?? []) {
    const content = atob(blob.content); // blobs arrive base64-encoded
    for (const { id, pattern, message, severity } of patterns) {
      if (severity !== "block") continue;
      const re = new RegExp(pattern, "gm");
      if (re.test(content)) {
        return `Push blocked by rule '${id}': ${message} (file: ${blob.path})`;
      }
    }
  }
  return null;
}

const DEFAULT_PATTERNS: PatternConfig[] = [
  {
    id: "internal-api-key",
    pattern: "INT-[A-Z0-9]{32}",
    message: "Internal API key detected — rotate and remove before pushing.",
    severity: "block",
  },
  {
    id: "internal-ip-range",
    pattern: "10\\.0\\.\\d{1,3}\\.\\d{1,3}",
    message: "Internal IP address detected in source code.",
    severity: "block",
  },
];
```

## KV Pattern Management Script

```typescript
// scripts/update-patterns.ts
// Run locally: CLOUDFLARE_API_TOKEN=... npx tsx scripts/update-patterns.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const KV_NAMESPACE_ID = process.env.KV_NAMESPACE_ID!;

const patterns = [
  { id: "internal-api-key", pattern: "INT-[A-Z0-9]{32}", message: "Internal key", severity: "block" },
  { id: "badge-number",     pattern: "EMP-\\d{6}",       message: "Employee badge number", severity: "block" },
];

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/patterns`,
  {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(patterns),
  },
);
console.log(res.status, await res.json());
```

## HMAC Verification Helper

```typescript
// src/verify.ts
export async function verifyHmac(secret: string, body: string, sig: string | null): Promise<boolean> {
  if (!sig?.startsWith("sha256=")) return false;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expected = "sha256=" + [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  if (expected.length !== sig.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0;
}
```

## Registering the Rule in GitHub

```bash
# Register as an Organization custom push protection rule
gh api /orgs/MY_ORG/rulesets \
  --method POST \
  --field name="custom-push-protection" \
  --field target="push" \
  --field enforcement="active" \
  --field bypass_actors='[]' \
  --field rules='[{"type":"custom_push_protection","parameters":{"endpoint":"https://my-worker.workers.dev"}}]' \
  --field conditions='{"repository_name":{"include":["~ALL"]}}'
```

## Anti-patterns

- **Returning a non-200 status to block a push** — the GitHub push protection hook interprets any non-2xx as a transient error and may allow the push through after retries. Always return 200 with `{ "pass": false }`.
- **Fetching patterns from D1 synchronously on every push** — use KV for read-heavy pattern lookup; KV reads are O(1) from global edge cache, D1 reads add ~10 ms of latency that compounds under push load.
- **Scanning binary blobs with regex** — filter blobs by extension before applying regex to avoid false positives in compiled artifacts.
- **Blocking all pushes during a Worker cold start** — if the Worker errors, GitHub treats it as a bypass-allowed failure. Instrument with `wrangler tail` to catch startup failures early.

## Gotchas

- GitHub sends blob content base64-encoded; always `atob()` before applying regex.
- The custom push protection endpoint must be reachable over the public internet — Workers custom domains work; `*.workers.dev` is also accessible.
- Pattern updates in KV propagate within 60 seconds globally due to KV eventual consistency; critical pattern changes may take up to 60s to enforce everywhere.
- The 10-second timeout is strict: if your Worker's HMAC + pattern scan exceeds 10s, GitHub logs a timeout and the push is either allowed or blocked per your ruleset's `bypass_actors` configuration.

## Verification

```bash
# Test the endpoint locally with a sample payload
echo '{"blobs":[{"path":"config.ts","content":"'$(echo -n 'const key = "INT-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";' | base64 -w0)'"}]}' \
  | curl -s -X POST http://localhost:8787 \
    -H "Content-Type: application/json" \
    -H "X-Hub-Signature-256: $(echo -n '...' | openssl dgst -sha256 -hmac 'secret' -hex | awk '{print "sha256="$2}')" \
    -d @- | jq .
# Expected: {"pass":false,"message":"Push blocked by rule 'internal-api-key': ..."}

# List org rulesets to confirm registration
gh api /orgs/MY_ORG/rulesets --jq '.[].name'
```

## Related

- `github-rulesets-2026.md`
- `github-push-protection-delegated-bypass-review.md`
- `github-secret-scanning-custom-patterns.md`
- `github-app-webhook-workers-handler.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
- https://docs.github.com/en/code-security/secret-scanning/using-advanced-secret-scanning-and-push-protection-features/custom-patterns
- https://developers.cloudflare.com/kv/
