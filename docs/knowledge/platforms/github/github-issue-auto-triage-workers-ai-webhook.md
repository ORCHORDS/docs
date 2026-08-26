# Automated GitHub Issue Triage with Workers AI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A busy open-source repository receives dozens of new issues daily. Maintainers spend significant time reading, labelling, and routing each one. A Cloudflare Worker handles the GitHub webhook, classifies the issue with Workers AI, applies the right label, assigns it to the right team, and writes a structured record to D1 — all within a few hundred milliseconds of the issue being opened.

## Context

GitHub Apps receive webhook events for repository activity. The `issues.opened` event fires when a new issue is created and includes the issue title, body, labels, and author. A Workers AI model (`@cf/meta/llama-3.1-8b-instruct`) classifies the text into one of four categories (bug, feature, question, docs). The Octokit REST client then applies a label and assigns the issue to the appropriate GitHub team. Triage results are stored in a D1 table for weekly reporting.

## Worker Implementation

```typescript
// src/index.ts
import { Octokit } from "@octokit/rest";
import { createAppAuth } from "@octokit/auth-app";

export interface Env {
  AI: Ai;
  DB: D1Database;
  GITHUB_APP_ID: string;
  GITHUB_PRIVATE_KEY: string;
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_ORG: string;
}

type IssueCategory = "bug" | "feature" | "question" | "docs";

const CATEGORY_LABELS: Record<IssueCategory, string> = {
  bug: "bug",
  feature: "enhancement",
  question: "question",
  docs: "documentation",
};

const CATEGORY_TEAMS: Record<IssueCategory, string> = {
  bug: "engineering",
  feature: "product",
  question: "support",
  docs: "docs",
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Verify GitHub webhook signature
    const signature = request.headers.get("x-hub-signature-256") ?? "";
    const body = await request.text();
    if (!(await verifySignature(body, signature, env.GITHUB_WEBHOOK_SECRET))) {
      return new Response("Unauthorized", { status: 401 });
    }

    const event = request.headers.get("x-github-event");
    if (event !== "issues") return new Response("OK", { status: 200 });

    const payload = JSON.parse(body) as GitHubIssuesPayload;
    if (payload.action !== "opened") return new Response("OK", { status: 200 });

    const { issue, repository, installation } = payload;

    // Classify with Workers AI
    const { category, confidence } = await classifyIssue(
      issue.title,
      issue.body ?? "",
      env.AI
    );

    // Authenticate as GitHub App installation
    const octokit = new Octokit({
      authStrategy: createAppAuth,
      auth: {
        appId: env.GITHUB_APP_ID,
        privateKey: env.GITHUB_PRIVATE_KEY,
        installationId: installation.id,
      },
    });

    const [owner, repo] = repository.full_name.split("/");

    // Apply label
    await octokit.rest.issues.addLabels({
      owner,
      repo,
      issue_number: issue.number,
      labels: [CATEGORY_LABELS[category]],
    });

    // Assign to team (adds team members as assignees)
    const teamSlug = `${env.GITHUB_ORG}-${CATEGORY_TEAMS[category]}`;
    const { data: team } = await octokit.rest.teams.listMembersInOrg({
      org: env.GITHUB_ORG,
      team_slug: CATEGORY_TEAMS[category],
      per_page: 1,
    });
    if (team.length > 0) {
      await octokit.rest.issues.addAssignees({
        owner,
        repo,
        issue_number: issue.number,
        assignees: [team[0].login],
      });
    }

    // Persist triage result to D1
    await env.DB.prepare(
      `INSERT INTO issue_triage
         (issue_number, repo, category, confidence, triaged_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT (issue_number, repo) DO UPDATE SET
         category = excluded.category,
         confidence = excluded.confidence,
         triaged_at = excluded.triaged_at`
    )
      .bind(
        issue.number,
        repository.full_name,
        category,
        confidence,
        new Date().toISOString()
      )
      .run();

    return new Response(
      JSON.stringify({ ok: true, category, confidence }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  },
};

async function classifyIssue(
  title: string,
  body: string,
  ai: Ai
): Promise<{ category: IssueCategory; confidence: number }> {
  const prompt = `Classify this GitHub issue into exactly one category.
Categories: bug, feature, question, docs

Title: ${title}
Body: ${body.slice(0, 1000)}

Respond with JSON only: {"category": "<category>", "confidence": <0.0-1.0>}`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    max_tokens: 64,
  }) as { response: string };

  try {
    const parsed = JSON.parse(response.response.trim());
    const category = ["bug", "feature", "question", "docs"].includes(parsed.category)
      ? (parsed.category as IssueCategory)
      : "question";
    const confidence = typeof parsed.confidence === "number"
      ? Math.min(1, Math.max(0, parsed.confidence))
      : 0.5;
    return { category, confidence };
  } catch {
    return { category: "question", confidence: 0.0 };
  }
}

async function verifySignature(
  body: string,
  signature: string,
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
  const hexSig = "sha256=" + Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, "0")).join("");
  return hexSig === signature;
}

interface GitHubIssuesPayload {
  action: string;
  issue: { number: number; title: string; body: string | null };
  repository: { full_name: string };
  installation: { id: number };
}
```

## D1 Schema

```sql
-- migrations/0001_issue_triage.sql
CREATE TABLE IF NOT EXISTS issue_triage (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_number INTEGER NOT NULL,
  repo        TEXT    NOT NULL,
  category    TEXT    NOT NULL CHECK (category IN ('bug','feature','question','docs')),
  confidence  REAL    NOT NULL,
  triaged_at  TEXT    NOT NULL,
  UNIQUE (issue_number, repo)
);

CREATE INDEX idx_triage_repo_category ON issue_triage (repo, category);
CREATE INDEX idx_triage_triaged_at    ON issue_triage (triaged_at);
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "issue-triage-bot"
main = "src/index.ts"
compatibility_date = "2025-08-01"

[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "issue-triage"
database_id   = "<your-d1-database-id>"

[vars]
GITHUB_ORG = "orchords"

# Secrets (set via `wrangler secret put`):
# GITHUB_APP_ID
# GITHUB_PRIVATE_KEY
# GITHUB_WEBHOOK_SECRET
```

## Reporting from D1

```typescript
// Add a /report endpoint for weekly summaries
if (url.pathname === "/report" && request.method === "GET") {
  const { results } = await env.DB.prepare(
    `SELECT category,
            COUNT(*)              AS total,
            ROUND(AVG(confidence), 2) AS avg_confidence
     FROM issue_triage
     WHERE repo = ?
       AND triaged_at >= datetime('now', '-7 days')
     GROUP BY category
     ORDER BY total DESC`
  ).bind("example-org/example-repo").all();

  return new Response(JSON.stringify(results), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## Anti-patterns

- Skipping webhook signature verification — any internet client could POST fake issue events and trigger label/assignment changes.
- Calling Workers AI synchronously inside the webhook handler without a timeout — set `AbortSignal.timeout(5000)` around the `ai.run()` call to avoid holding the webhook connection open.
- Assigning the issue to the entire team instead of a single on-call member — `addAssignees` with many logins produces notification spam; pick one lead per team.
- Storing the GitHub App private key in wrangler.toml `[vars]` — it must be a secret set with `wrangler secret put GITHUB_PRIVATE_KEY`.

## Gotchas

- Workers AI responses are non-deterministic; always validate and sanitise the JSON output before treating `category` as trusted — fall back to `"question"` on any parse error.
- GitHub webhook delivery has a 10-second timeout. If the Worker takes longer (rare but possible with cold AI inference), GitHub will mark the delivery failed and retry up to 3 times. Make the handler idempotent (the `ON CONFLICT` clause handles duplicate D1 inserts).
- The `@cf/meta/llama-3.1-8b-instruct` model's JSON output mode requires the prompt to explicitly ask for JSON — Workers AI does not have a native `response_format: json_object` like OpenAI.
- GitHub Apps require the `issues:write` and `members:read` (org) permissions to apply labels, add assignees, and list team members.

## Verification

```bash
# Apply D1 migration
wrangler d1 migrations apply issue-triage --remote

# Simulate a webhook event locally
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-Hub-Signature-256: sha256=$(echo -n '{...}' | openssl dgst -sha256 -hmac mysecret -hex | cut -d' ' -f2)" \
  -d '{"action":"opened","issue":{"number":1,"title":"Button not working","body":"Clicking save does nothing"},"repository":{"full_name":"example-org/example-repo"},"installation":{"id":12345}}'

# Query triage results
wrangler d1 execute issue-triage \
  --remote \
  --command "SELECT * FROM issue_triage ORDER BY triaged_at DESC LIMIT 10;"
```

## Related

- `github-merge-queue-workers-ci-validation.md`
- `github-environments-cloudflare-deployment-protection.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app
- https://developers.cloudflare.com/d1/
- https://octokit.github.io/rest.js/
