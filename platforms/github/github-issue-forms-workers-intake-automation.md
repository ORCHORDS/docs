# GitHub Issue Forms: Workers Intake Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A team uses GitHub issue forms (YAML-based `/.github/ISSUE_TEMPLATE/*.yml`) for structured
intake — bug reports, feature requests, incident reports. Once submitted, someone manually reads
the issue, applies labels, assigns it, and routes it to the right team. At scale this bottleneck
delays triage. A Cloudflare Worker consuming the `issues` webhook can parse the structured form
body and automate routing the moment an issue opens.

## Context

GitHub issue forms emit a structured Markdown body in a predictable `### Heading\n\nValue` format:

```
### Category

Bug report

### Affected environment

production
```

When an issue is opened, GitHub fires an `issues` webhook with `action: "opened"`. The Worker:

1. Verifies the webhook signature using `crypto.subtle`.
2. Parses the Markdown body into key-value pairs keyed on heading text.
3. Looks up a routing rule by the `Category` field value.
4. Applies labels and assignees via the GitHub REST API.
5. Posts a triage acknowledgement comment on the issue.

## Worker Entry Point

```typescript
// src/index.ts
import { verifyWebhookSignature } from "./github/verify";
import { parseIssueFormBody } from "./github/parse-issue-form";
import { applyIssueMetadata } from "./github/apply-metadata";
import type { IssuesWebhookPayload } from "./types";

export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_APP_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const signature = request.headers.get("x-hub-signature-256") ?? "";
    const body = await request.text();

    const valid = await verifyWebhookSignature(body, signature, env.GITHUB_WEBHOOK_SECRET);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    const event = request.headers.get("x-github-event");
    if (event !== "issues") return new Response("Ignored", { status: 200 });

    const payload = JSON.parse(body) as IssuesWebhookPayload;
    if (payload.action !== "opened") return new Response("Ignored", { status: 200 });

    // Use waitUntil so GitHub gets a fast 200 before API calls complete
    ctx.waitUntil(applyIssueMetadata(payload, env));
    return new Response("OK", { status: 200 });
  },
} satisfies ExportedHandler<Env>;
```

## Webhook Signature Verification

```typescript
// src/github/verify.ts
export async function verifyWebhookSignature(
  body: string,
  signatureHeader: string,
  secret: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const computed =
    "sha256=" +
    Array.from(new Uint8Array(sig))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

  // Constant-time comparison to prevent timing attacks
  if (computed.length !== signatureHeader.length) return false;
  let mismatch = 0;
  for (let i = 0; i < computed.length; i++) {
    mismatch |= computed.charCodeAt(i) ^ signatureHeader.charCodeAt(i);
  }
  return mismatch === 0;
}
```

## Issue Form Body Parser

```typescript
// src/github/parse-issue-form.ts
export type IssueFormFields = Record<string, string>;

/**
 * Parses a GitHub issue form body into structured key-value pairs.
 *
 * Input format produced by GitHub issue forms:
 *   ### Field Name\n\nValue\n\n### Next Field\n\nValue
 *
 * Returns an object keyed on the heading text with normalised values.
 * "_No response_" (GitHub's placeholder for skipped optional fields) is
 * normalised to an empty string.
 */
export function parseIssueFormBody(body: string): IssueFormFields {
  const fields: IssueFormFields = {};
  const sections = body.split(/^### /m);

  for (const section of sections) {
    if (!section.trim()) continue;
    const newlineIndex = section.indexOf("\n");
    if (newlineIndex === -1) continue;

    const key = section.slice(0, newlineIndex).trim();
    const raw = section.slice(newlineIndex).trim();
    const value = raw === "_No response_" ? "" : raw.replace(/^> /gm, "").trim();
    fields[key] = value;
  }

  return fields;
}
```

## Routing Logic and GitHub API Calls

```typescript
// src/github/apply-metadata.ts
import { parseIssueFormBody } from "./parse-issue-form";
import type { IssuesWebhookPayload } from "../types";
import type { Env } from "../index";

interface RoutingRule {
  match: (category: string) => boolean;
  addLabels: string[];
  assignees: string[];
  priority: string;
}

const ROUTING_RULES: RoutingRule[] = [
  {
    match: (c) => /bug/i.test(c),
    addLabels: ["bug", "needs-triage"],
    assignees: ["on-call-engineer"],
    priority: "P2",
  },
  {
    match: (c) => /feature/i.test(c),
    addLabels: ["enhancement", "backlog"],
    assignees: [],
    priority: "P3",
  },
  {
    match: (c) => /incident/i.test(c),
    addLabels: ["incident", "P0", "needs-triage"],
    assignees: ["incident-lead", "on-call-engineer"],
    priority: "P0",
  },
];

export async function applyIssueMetadata(
  payload: IssuesWebhookPayload,
  env: Env
): Promise<void> {
  const fields = parseIssueFormBody(payload.issue.body ?? "");
  const category = fields["Category"] ?? fields["Issue Type"] ?? "";
  const environment = fields["Affected environment"] ?? "unknown";

  const rule = ROUTING_RULES.find((r) => r.match(category));
  if (!rule) {
    console.warn(`No routing rule matched category: "${category}"`);
    return;
  }

  const base = `https://api.github.com/repos/${payload.repository.full_name}`;
  const issueUrl = `${base}/issues/${payload.issue.number}`;
  const headers = {
    Authorization: `Bearer ${env.GITHUB_APP_TOKEN}`,
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "intake-worker/1.0",
  };

  const requests: Promise<Response>[] = [];

  if (rule.addLabels.length > 0) {
    requests.push(
      fetch(`${issueUrl}/labels`, {
        method: "POST",
        headers,
        body: JSON.stringify({ labels: rule.addLabels }),
      })
    );
  }

  if (rule.assignees.length > 0) {
    requests.push(
      fetch(`${issueUrl}/assignees`, {
        method: "POST",
        headers,
        body: JSON.stringify({ assignees: rule.assignees }),
      })
    );
  }

  const comment =
    `Thank you for the report. This has been triaged as **${category}** ` +
    `(priority: ${rule.priority}).\n\n` +
    `**Affected environment:** ${environment}\n` +
    `**Labels applied:** ${rule.addLabels.join(", ")}\n\n` +
    `The team will follow up shortly.`;

  requests.push(
    fetch(`${issueUrl}/comments`, {
      method: "POST",
      headers,
      body: JSON.stringify({ body: comment }),
    })
  );

  const results = await Promise.allSettled(requests);
  for (const r of results) {
    if (r.status === "rejected") console.error("GitHub API call failed:", r.reason);
  }
}
```

## Wrangler Configuration

```toml
# wrangler.toml
name        = "issue-intake-worker"
main        = "src/index.ts"
compatibility_date = "2026-01-01"

# Secrets — set via wrangler secret put:
#   GITHUB_WEBHOOK_SECRET
#   GITHUB_APP_TOKEN
```

```typescript
// src/types.ts
export interface IssuesWebhookPayload {
  action: "opened" | "edited" | "closed" | "reopened" | "deleted";
  issue: {
    number: number;
    title: string;
    body: string | null;
  };
  repository: {
    full_name: string;
  };
}
```

## Anti-patterns

- Parsing the issue body with a one-line regex instead of splitting on `### ` headings — the
  heading-split approach handles multiline answers and Markdown within field values; a regex
  does not.
- Skipping webhook signature verification — any client can POST to the Worker's URL and trigger
  automated label changes on arbitrary issues.
- Using a long-lived PAT instead of a GitHub App installation token — PATs are tied to a person's
  account; when that person leaves the org the token stops working.
- Calling GitHub API endpoints synchronously before returning the 200 response — GitHub retries
  webhook deliveries that timeout; use `ctx.waitUntil()` so the 200 lands quickly.

## Gotchas

- GitHub issues created via the API may not follow the form template structure. Guard the parser
  result: if `fields["Category"]` is undefined, fall through to a default label (`needs-triage`)
  rather than routing to the wrong team.
- The `issues` webhook fires for all issue actions including edits. Check `payload.action ===
  "opened"` before routing; routing on edits re-applies labels every time someone corrects a typo.
- GitHub rate-limits the REST API at 5,000 requests/hour per installation token. For high-volume
  repos batch label and assignee calls, or cache the token in Workers KV with its expiry.
- Optional form fields left blank appear as `_No response_` in the body, not as an absent
  heading. The parser normalises this to `""` so routing rules can safely check `!fields["X"]`.

## Verification

```bash
# Send a test payload to a local wrangler dev instance
# First compute the HMAC signature:
PAYLOAD=$(cat fixtures/issue-opened.json)
SIG="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')"

curl -s -X POST http://localhost:8787 \
  -H "x-github-event: issues" \
  -H "x-hub-signature-256: $SIG" \
  -H "content-type: application/json" \
  -d "$PAYLOAD"

# Confirm labels were applied to the issue
gh issue view 42 --repo owner/repo --json labels,assignees
```

## Related

- `github-issue-forms-yaml-schema.md`
- `github-app-webhook-workers-handler.md`
- `github-apps-installation-token-workers-api-client.md`
- `github-webhook-signing-verification.md`
- `github-labels-automation.md`

## Sources

- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
