# AI-Powered Bug Report Triage with Workers AI + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Bug reports arrive in varying quality: some have clear reproduction steps and severity cues, others are vague. Triaging them manually to assign severity, extract repro steps, and tag components is slow and inconsistent. A Worker can run AI classification on each new bug report, post a structured triage summary as a comment, apply labels, and store the result in D1 for later model improvement analysis.

## Context

Cloudflare Workers AI provides on-device inference via `env.AI.run()`. The `@cf/meta/llama-3.1-8b-instruct` model handles text classification and extraction tasks with good quality at low latency. D1 stores triage history rows that can be exported for fine-tuning or accuracy audits.

Workflow:
1. GitHub fires `issues.opened` webhook.
2. Worker verifies signature.
3. Worker runs two AI tasks in parallel: severity classification and component/repro extraction.
4. Worker computes a priority score from the results.
5. Worker posts a triage comment and applies labels via GitHub API.
6. Worker writes a D1 triage history row.

## Solution

### wrangler.toml

```toml
name = "bug-triage"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "bug-triage"
database_id = "<your-d1-database-id>"

[ai]
binding = "AI"
```

### D1 schema

```sql
-- migrations/0001_schema.sql
CREATE TABLE IF NOT EXISTS triage_history (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  repo            TEXT NOT NULL,
  issue_number    INTEGER NOT NULL,
  severity        TEXT NOT NULL,    -- 'critical' | 'high' | 'medium' | 'low'
  components      TEXT NOT NULL,    -- JSON array
  has_repro       INTEGER NOT NULL, -- 0 | 1
  priority_score  REAL NOT NULL,
  model_used      TEXT NOT NULL,
  triage_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_triage_repo ON triage_history(repo);
CREATE INDEX IF NOT EXISTS idx_triage_severity ON triage_history(severity);
```

### Types

```typescript
export interface Env {
  DB: D1Database;
  AI: Ai;
  GH_TOKEN: string;
  GH_WEBHOOK_SECRET: string;
}

type Severity = "critical" | "high" | "medium" | "low";

interface TriageResult {
  severity: Severity;
  components: string[];
  hasRepro: boolean;
  reproSteps: string | null;
  priorityScore: number;
  reasoning: string;
}

interface IssueEvent {
  action: string;
  issue: {
    number: number;
    title: string;
    body: string | null;
    labels: { name: string }[];
  };
  repository: {
    full_name: string;
    owner: { login: string };
    name: string;
  };
}
```

### Severity classification

```typescript
const SEVERITY_LEVELS: Severity[] = ["critical", "high", "medium", "low"];

async function classifySeverity(ai: Ai, title: string, body: string): Promise<Severity> {
  const prompt = `You are a software bug triage assistant. Classify the severity of the following bug report as exactly one of: critical, high, medium, low.

critical = data loss, security vulnerability, system down, crashes for all users
high = major feature broken, significant user impact, no workaround
medium = feature partially broken, workaround exists
low = cosmetic issue, minor inconvenience

Bug title: ${title}
Bug body:
${body.slice(0, 2000)}

Respond with ONLY the severity word.`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    prompt,
    max_tokens: 10,
  }) as { response: string };

  const raw = response.response.trim().toLowerCase();
  return SEVERITY_LEVELS.find((s) => raw.includes(s)) ?? "medium";
}
```

### Component tagging + repro extraction

```typescript
interface ExtractionOutput {
  components: string[];
  hasRepro: boolean;
  reproSteps: string | null;
  reasoning: string;
}

async function extractDetails(ai: Ai, title: string, body: string): Promise<ExtractionOutput> {
  const prompt = `You are a bug triage assistant. Analyze the bug report and return a JSON object with these fields:
- components: string[] — list of affected system components (e.g. ["auth", "dashboard", "api"]). Max 5 items.
- hasRepro: boolean — true if the report contains reproduction steps.
- reproSteps: string | null — extracted reproduction steps as a numbered list, or null if none present.
- reasoning: string — one sentence explaining your classification.

Bug title: ${title}
Bug body:
${body.slice(0, 2000)}

Respond with ONLY valid JSON.`;

  const response = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    prompt,
    max_tokens: 400,
  }) as { response: string };

  try {
    const jsonMatch = response.response.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("No JSON found");
    const parsed = JSON.parse(jsonMatch[0]);
    return {
      components: Array.isArray(parsed.components) ? parsed.components.slice(0, 5) : [],
      hasRepro: Boolean(parsed.hasRepro),
      reproSteps: typeof parsed.reproSteps === "string" ? parsed.reproSteps : null,
      reasoning: typeof parsed.reasoning === "string" ? parsed.reasoning : "",
    };
  } catch {
    return { components: [], hasRepro: false, reproSteps: null, reasoning: "parse error" };
  }
}
```

### Priority score calculation

```typescript
function calcPriorityScore(severity: Severity, hasRepro: boolean, components: string[]): number {
  const severityWeight: Record<Severity, number> = {
    critical: 100,
    high: 75,
    medium: 40,
    low: 10,
  };
  const reproBonus = hasRepro ? 15 : 0;
  const componentBonus = Math.min(components.length * 5, 20);
  return severityWeight[severity] + reproBonus + componentBonus;
}
```

### Triage comment + label application

```typescript
async function postTriageComment(
  owner: string,
  repo: string,
  issueNumber: number,
  result: TriageResult,
  ghToken: string
): Promise<void> {
  const severity_emoji: Record<Severity, string> = {
    critical: "🔴",
    high: "🟠",
    medium: "🟡",
    low: "🟢",
  };

  const body = [
    `## 🤖 Automated Triage`,
    ``,
    `**Severity:** ${severity_emoji[result.severity]} ${result.severity.toUpperCase()} (score: ${result.priorityScore})`,
    `**Components:** ${result.components.length ? result.components.join(", ") : "unknown"}`,
    `**Reproduction steps present:** ${result.hasRepro ? "Yes" : "No"}`,
    ``,
    result.reproSteps ? `**Extracted repro steps:**\n${result.reproSteps}` : "",
    ``,
    `*Reasoning: ${result.reasoning}*`,
    ``,
    `---`,
    `*This triage was generated automatically. A human reviewer should confirm severity.*`,
  ].filter((l) => l !== null).join("\n");

  const commentRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/comments`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body }),
    }
  );
  if (!commentRes.ok) console.error(`Comment failed: ${commentRes.status}`);

  // Apply severity label
  const labelRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/labels`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ labels: [`severity:${result.severity}`] }),
    }
  );
  if (!labelRes.ok) console.error(`Label failed: ${labelRes.status}`);
}
```

### D1 history write

```typescript
async function saveTriageHistory(
  db: D1Database,
  repo: string,
  issueNumber: number,
  result: TriageResult
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO triage_history
         (repo, issue_number, severity, components, has_repro, priority_score, model_used, triage_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      repo,
      issueNumber,
      result.severity,
      JSON.stringify(result.components),
      result.hasRepro ? 1 : 0,
      result.priorityScore,
      "@cf/meta/llama-3.1-8b-instruct",
      new Date().toISOString()
    )
    .run();
}
```

### Worker entry point

```typescript
async function verifySignature(request: Request, secret: string): Promise<boolean> {
  const sig = request.headers.get("X-Hub-Signature-256") ?? "";
  const body = await request.clone().arrayBuffer();
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, body);
  const expected = "sha256=" + Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  if (sig.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    if (!(await verifySignature(request, env.GH_WEBHOOK_SECRET)))
      return new Response("Unauthorized", { status: 401 });

    const payload: IssueEvent = await request.json();
    if (payload.action !== "opened") return new Response("ignored", { status: 200 });
    if (!payload.issue.labels.some((l) => l.name === "bug"))
      return new Response("not a bug report", { status: 200 });

    const { issue, repository } = payload;
    const owner = repository.owner.login;
    const repoName = repository.name;
    const body = issue.body ?? "";

    // Run classification and extraction in parallel
    const [severity, details] = await Promise.all([
      classifySeverity(env.AI, issue.title, body),
      extractDetails(env.AI, issue.title, body),
    ]);

    const priorityScore = calcPriorityScore(severity, details.hasRepro, details.components);

    const result: TriageResult = {
      severity,
      components: details.components,
      hasRepro: details.hasRepro,
      reproSteps: details.reproSteps,
      priorityScore,
      reasoning: details.reasoning,
    };

    await Promise.all([
      postTriageComment(owner, repoName, issue.number, result, env.GH_TOKEN),
      saveTriageHistory(env.DB, repository.full_name, issue.number, result),
    ]);

    return Response.json({ ok: true, severity, priorityScore });
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

- Two AI calls run in `Promise.all` to keep total latency to a single model round-trip instead of two sequential calls.
- The JSON extraction uses a regex to find the first `{...}` block — LLMs sometimes prefix the JSON with explanation text despite instructions.
- Severity label names (`severity:critical` etc.) must be pre-created in the GitHub repository. The label `POST` call returns 422 if the label does not exist; create labels with a one-time setup script.
- Store `model_used` in D1 so you can segment accuracy analysis by model version when you upgrade.

## Anti-patterns

- **Do not triage every issue.** Only process issues with the `bug` label (or some equivalent gate). Feature requests and discussions do not need severity classification.
- **Do not trust AI output as final.** Always append a human-review disclaimer in the comment.
- **Do not use `max_tokens: 10` for the extraction call.** The JSON output needs enough room; use at least 400 tokens.

## Gotchas

- `env.AI` is only available when the `[ai]` binding is declared in `wrangler.toml` and the account has Workers AI enabled.
- Workers AI model names use `@cf/` prefix. Do not omit it.
- The `issues.opened` event fires before any labels are applied if the issue author adds labels while opening. Check `payload.issue.labels` — it may be empty even if labels appear on the issue shortly after. Use a small delay or handle `issues.labeled` as a secondary trigger.

## Verification

```bash
# Apply schema
npx wrangler d1 migrations apply bug-triage --local

# Test AI locally (wrangler dev supports Workers AI)
npx wrangler dev

# Simulate a webhook
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=<computed>" \
  --data '{"action":"opened","issue":{"number":7,"title":"App crashes on login","body":"Steps: 1. Open app 2. Click login 3. App crashes\nExpected: Should log in\nActual: Crash","labels":[{"name":"bug"}]},"repository":{"full_name":"example-org/example-repo","owner":{"login":"orchords"},"name":"api"}}'

# Check D1 history
npx wrangler d1 execute bug-triage --local \
  --command "SELECT * FROM triage_history ORDER BY id DESC LIMIT 5"
```

## Related

- workers-issue-deduplication-embedding
- workers-issue-template-enforcement
- workers-github-issue-webhook-router

## Sources

- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/d1/
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
