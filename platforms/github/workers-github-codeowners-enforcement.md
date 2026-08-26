# CODEOWNERS Enforcement Bot Using Cloudflare Workers and GitHub Webhooks

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Teams push PRs and forget to add the right reviewers. GitHub's native CODEOWNERS support assigns reviewers automatically but silently fails when the file is malformed, the owner team has no members, or a required reviewer is on PTO. You need an auditable enforcement layer that:

- Parses CODEOWNERS on every `pull_request.opened` / `pull_request.synchronize` event.
- Suggests the correct reviewers via the GitHub API.
- Writes an audit log to D1 for compliance reporting.
- Supports an emergency-bypass label that skips enforcement and still logs the exception.

## Context

GitHub sends webhook payloads to a public HTTPS endpoint. A Cloudflare Worker receives the payload, validates the HMAC-SHA256 signature, parses the CODEOWNERS file for the changed paths, and calls the `POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers` endpoint.

D1 stores every enforcement decision (reviewer assigned, bypass granted, file not found) for audit reports.

## Solution

### Wrangler configuration

```toml
# wrangler.toml
name = "codeowners-enforcer"
main = "src/index.ts"
compatibility_date = "2024-11-01"

[[d1_databases]]
binding = "DB"
database_name = "codeowners-audit"
database_id = "YOUR_D1_DATABASE_ID"
```

### D1 schema

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS enforcement_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  org         TEXT NOT NULL,
  repo        TEXT NOT NULL,
  pr_number   INTEGER NOT NULL,
  sha         TEXT NOT NULL,
  action      TEXT NOT NULL, -- 'assigned' | 'bypass' | 'no_owners' | 'error'
  reviewers   TEXT,          -- JSON array of logins
  reason      TEXT
);

CREATE INDEX idx_repo_pr ON enforcement_log(org, repo, pr_number);
```

### Webhook signature validation

```typescript
// src/signature.ts
export async function validateGitHubSignature(
  request: Request,
  secret: string,
  rawBody: string
): Promise<boolean> {
  const sigHeader = request.headers.get("X-Hub-Signature-256");
  if (!sigHeader) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const mac = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(rawBody)
  );

  const expected =
    "sha256=" +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

  // Constant-time comparison
  if (expected.length !== sigHeader.length) return false;
  let mismatch = 0;
  for (let i = 0; i < expected.length; i++) {
    mismatch |= expected.charCodeAt(i) ^ sigHeader.charCodeAt(i);
  }
  return mismatch === 0;
}
```

### CODEOWNERS parser

```typescript
// src/codeowners.ts
export interface CodeownersRule {
  pattern: string;
  owners: string[];
}

export function parseCodeowners(content: string): CodeownersRule[] {
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => {
      const parts = line.split(/\s+/);
      return { pattern: parts[0], owners: parts.slice(1) };
    })
    .filter((r) => r.owners.length > 0)
    .reverse(); // Last matching rule wins (GitHub behaviour)
}

// Minimal glob match: supports * and ** prefix-style patterns
function globMatch(pattern: string, filePath: string): boolean {
  // Escape regex special chars except * and ?
  const regexStr = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, ".+")
    .replace(/\*/g, "[^/]+")
    .replace(/\?/g, "[^/]");
  return new RegExp(`^${regexStr}$`).test("/" + filePath) ||
         new RegExp(`^${regexStr}`).test("/" + filePath);
}

export function resolveOwners(
  rules: CodeownersRule[],
  changedFiles: string[]
): Set<string> {
  const owners = new Set<string>();
  for (const file of changedFiles) {
    for (const rule of rules) {
      if (globMatch(rule.pattern, file)) {
        rule.owners.forEach((o) => owners.add(o));
        break; // First match in reversed list = last matching rule
      }
    }
  }
  return owners;
}
```

### GitHub API helpers

```typescript
// src/github.ts
const GH = "https://api.github.com";

export async function fetchCodeowners(
  token: string,
  owner: string,
  repo: string,
  ref: string
): Promise<string | null> {
  // GitHub checks .github/CODEOWNERS, then CODEOWNERS, then docs/CODEOWNERS
  const paths = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"];
  for (const path of paths) {
    const resp = await fetch(
      `${GH}/repos/${owner}/${repo}/contents/${path}?ref=${ref}`,
      { headers: ghHeaders(token) }
    );
    if (resp.ok) {
      const data = (await resp.json()) as { content: string };
      return atob(data.content.replace(/\n/g, ""));
    }
  }
  return null;
}

export async function getChangedFiles(
  token: string,
  owner: string,
  repo: string,
  pullNumber: number
): Promise<string[]> {
  const files: string[] = [];
  let page = 1;
  while (true) {
    const resp = await fetch(
      `${GH}/repos/${owner}/${repo}/pulls/${pullNumber}/files?per_page=100&page=${page}`,
      { headers: ghHeaders(token) }
    );
    const items = (await resp.json()) as Array<{ filename: string }>;
    if (!items.length) break;
    files.push(...items.map((f) => f.filename));
    if (items.length < 100) break;
    page++;
  }
  return files;
}

export async function requestReviewers(
  token: string,
  owner: string,
  repo: string,
  pullNumber: number,
  logins: string[],
  teams: string[]
): Promise<void> {
  await fetch(`${GH}/repos/${owner}/${repo}/pulls/${pullNumber}/requested_reviewers`, {
    method: "POST",
    headers: { ...ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ reviewers: logins, team_reviewers: teams }),
  });
}

function ghHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "orchords-codeowners-bot/1.0",
  };
}
```

### Main enforcement handler

```typescript
// src/enforce.ts
import { fetchCodeowners, getChangedFiles, requestReviewers } from "./github";
import { parseCodeowners, resolveOwners } from "./codeowners";
import type { Env } from "./types";

const EMERGENCY_BYPASS_LABEL = "emergency-bypass";

export async function enforceCODEOWNERS(
  env: Env,
  payload: GitHubPRPayload
): Promise<void> {
  const { pull_request: pr, repository: rep, installation } = payload;
  const owner = rep.owner.login;
  const repo = rep.name;
  const prNumber = pr.number;
  const sha = pr.head.sha;

  // Emergency bypass
  const isBypass = pr.labels.some((l: { name: string }) => l.name === EMERGENCY_BYPASS_LABEL);
  if (isBypass) {
    await logAudit(env, owner, repo, prNumber, sha, "bypass", [], "emergency-bypass label present");
    return;
  }

  const token = env.GITHUB_TOKEN; // Or use installation auth from other article

  const [codeownersContent, changedFiles] = await Promise.all([
    fetchCodeowners(token, owner, repo, sha),
    getChangedFiles(token, owner, repo, prNumber),
  ]);

  if (!codeownersContent) {
    await logAudit(env, owner, repo, prNumber, sha, "no_owners", [], "CODEOWNERS file not found");
    return;
  }

  const rules = parseCodeowners(codeownersContent);
  const ownerEntries = resolveOwners(rules, changedFiles);

  const logins: string[] = [];
  const teams: string[] = [];

  for (const entry of ownerEntries) {
    if (entry.startsWith("@")) {
      const stripped = entry.slice(1);
      if (stripped.includes("/")) {
        // @org/team-name -> team_reviewers
        teams.push(stripped.split("/")[1]);
      } else {
        logins.push(stripped);
      }
    }
    // email owners are skipped — GitHub API requires logins/teams
  }

  if (logins.length === 0 && teams.length === 0) {
    await logAudit(env, owner, repo, prNumber, sha, "no_owners", [], "No resolvable owners for changed paths");
    return;
  }

  // Remove the PR author to avoid self-review
  const authorLogin = pr.user.login;
  const filteredLogins = logins.filter((l) => l !== authorLogin);

  await requestReviewers(token, owner, repo, prNumber, filteredLogins, teams);
  await logAudit(env, owner, repo, prNumber, sha, "assigned", [...filteredLogins, ...teams]);
}

async function logAudit(
  env: Env,
  org: string,
  repo: string,
  prNumber: number,
  sha: string,
  action: string,
  reviewers: string[],
  reason?: string
) {
  await env.DB.prepare(
    `INSERT INTO enforcement_log (org, repo, pr_number, sha, action, reviewers, reason)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(org, repo, prNumber, sha, action, JSON.stringify(reviewers), reason ?? null)
    .run();
}
```

### Worker entrypoint

```typescript
// src/index.ts
import { validateGitHubSignature } from "./signature";
import { enforceCODEOWNERS } from "./enforce";
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const rawBody = await request.text();
    const valid = await validateGitHubSignature(request, env.WEBHOOK_SECRET, rawBody);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    const event = request.headers.get("X-GitHub-Event");
    if (event !== "pull_request") return new Response("Ignored", { status: 200 });

    const payload = JSON.parse(rawBody);
    if (!["opened", "synchronize", "reopened"].includes(payload.action)) {
      return new Response("Ignored", { status: 200 });
    }

    await enforceCODEOWNERS(env, payload);
    return new Response("OK", { status: 200 });
  },
};
```

## Implementation Details

- CODEOWNERS last-matching-rule semantics: the file is parsed and reversed before matching so the first hit in the reversed array corresponds to the last matching rule in the original file.
- Teams are specified as `@org/team-name`; the GitHub API requires only the team slug (without the org prefix) in `team_reviewers`.
- `getChangedFiles` paginates using `per_page=100` to handle large PRs correctly.
- The PR author is excluded from the reviewer list because GitHub prevents self-review.

## Anti-patterns

- **Parsing CODEOWNERS with simple line splits** — Patterns can contain spaces escaped with backslashes. The parser here handles common cases; production use should adopt a dedicated CODEOWNERS parser library.
- **Storing the webhook secret in `[vars]`** — Use `wrangler secret put WEBHOOK_SECRET`; secrets are encrypted at rest and not visible in the dashboard source view.
- **Blocking the Worker on audit logging** — Use `ctx.waitUntil(logAudit(...))` to avoid adding latency to the 200 response.

## Gotchas

- GitHub sends the webhook and expects a `2xx` response within 10 seconds. Long-running CODEOWNERS resolution must be offloaded with `ctx.waitUntil`.
- The `@org/team-name` format in CODEOWNERS refers to a GitHub Team. The team must have at least one member, or GitHub silently ignores the review request.
- `pull_request.synchronize` fires on every push to the PR branch, which re-requests reviewers. Deduplicate by checking existing reviewers before calling the API if re-requesting is noisy.

## Verification

```bash
# Query the audit log for a specific PR
wrangler d1 execute codeowners-audit \
  --command "SELECT * FROM enforcement_log WHERE repo='my-repo' AND pr_number=42"

# Tail live Worker logs
wrangler tail codeowners-enforcer
```

## Related

- `documentation/categories/github/workers-github-app-installation-auth.md`
- `documentation/categories/github/workers-github-branch-protection-enforcer.md`

## Sources

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://docs.github.com/en/rest/pulls/review-requests
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request
- https://developers.cloudflare.com/d1/
