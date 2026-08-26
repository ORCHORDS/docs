# Issue Template Enforcement Bot Using Workers + GitHub API

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Issue templates in `.github/ISSUE_TEMPLATE/` guide reporters, but GitHub does not enforce that users fill in required sections — they can submit with placeholder text or empty headings. Maintainers waste time asking for repro steps or environment details. You need a bot that validates template sections immediately on issue creation, comments with specific guidance on what is missing, and labels incomplete issues so they can be filtered or auto-closed by a stale bot.

## Context

A Cloudflare Worker receives the `issues.opened` event from the queue produced by `workers-github-issue-webhook-router`. It fetches the repo's issue template(s), determines which template was used (by matching headings), validates required sections with regex patterns, and uses the GitHub API (via a GitHub App) to post a comment and apply labels. Org admins are detected via the GitHub API and bypass enforcement.

## Solution

### 1. Wrangler configuration

```toml
# wrangler.toml
name = "issue-template-enforcer"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "issues-opened"
max_batch_size = 5
max_batch_timeout = 10

[[kv_namespaces]]
binding = "TEMPLATE_CACHE"
id = "<your-kv-namespace-id>"

[vars]
GITHUB_APP_ID = "123456"
INCOMPLETE_LABEL = "needs-more-info"
TEMPLATE_CACHE_TTL_SECONDS = "3600"

# Secrets: GITHUB_APP_PRIVATE_KEY, GITHUB_INSTALLATION_ID
```

### 2. Types

```typescript
// src/types.ts
export interface Env {
  TEMPLATE_CACHE: KVNamespace;
  GITHUB_APP_ID: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_INSTALLATION_ID: string;
  INCOMPLETE_LABEL: string;
  TEMPLATE_CACHE_TTL_SECONDS: string;
}

export type TemplateSection = {
  heading: string;          // e.g. "## Steps to Reproduce"
  pattern: RegExp;          // pattern the section content must satisfy
  required: boolean;
  guidanceIfMissing: string; // human-readable message for the comment
};

export type ValidationResult = {
  passed: boolean;
  missingSections: TemplateSection[];
};
```

### 3. Template fetching and caching

```typescript
// src/templates.ts
import type { Env } from "./types";

const TEMPLATE_PATH_CANDIDATES = [
  ".github/ISSUE_TEMPLATE/bug_report.md",
  ".github/ISSUE_TEMPLATE/feature_request.md",
  ".github/ISSUE_TEMPLATE.md",
];

export async function fetchTemplate(
  env: Env,
  token: string,
  repoFullName: string,
  templateName: string
): Promise<string | null> {
  const cacheKey = `template:${repoFullName}:${templateName}`;
  const cached = await env.TEMPLATE_CACHE.get(cacheKey);
  if (cached !== null) return cached;

  const [owner, repo] = repoFullName.split("/");
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/contents/${templateName}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } }
  );

  if (!res.ok) return null;

  const data = await res.json<{ content: string; encoding: string }>();
  const content = atob(data.content.replace(/\n/g, ""));

  await env.TEMPLATE_CACHE.put(cacheKey, content, {
    expirationTtl: parseInt(env.TEMPLATE_CACHE_TTL_SECONDS),
  });
  return content;
}

export async function detectUsedTemplate(
  env: Env,
  token: string,
  repoFullName: string,
  issueBody: string
): Promise<string | null> {
  // Try each candidate template; return the one whose headings most overlap with the issue body
  let bestMatch: string | null = null;
  let bestScore = 0;

  for (const path of TEMPLATE_PATH_CANDIDATES) {
    const template = await fetchTemplate(env, token, repoFullName, path);
    if (!template) continue;

    const templateHeadings = [...template.matchAll(/^##+ .+/gm)].map((m) => m[0].trim());
    const issueHeadings = [...issueBody.matchAll(/^##+ .+/gm)].map((m) => m[0].trim());
    const overlap = templateHeadings.filter((h) => issueHeadings.includes(h)).length;
    const score = overlap / Math.max(templateHeadings.length, 1);

    if (score > bestScore) {
      bestScore = score;
      bestMatch = path;
    }
  }

  return bestScore >= 0.5 ? bestMatch : null; // at least 50% heading overlap
}
```

### 4. Validation rules

```typescript
// src/rules.ts
import type { TemplateSection, ValidationResult } from "./types";

// These rules apply to the default bug report template.
// Extend or load per-template rules from KV/D1 for multi-template repos.
export const BUG_REPORT_SECTIONS: TemplateSection[] = [
  {
    heading: "## Describe the bug",
    pattern: /\S{20,}/,  // at least 20 non-whitespace chars of content
    required: true,
    guidanceIfMissing:
      "**Describe the bug** section is empty or too short. Please describe what went wrong in at least one sentence.",
  },
  {
    heading: "## Steps to Reproduce",
    pattern: /\d+\.\s|\*\s|- /,  // must contain a numbered or bulleted list item
    required: true,
    guidanceIfMissing:
      "**Steps to Reproduce** section must contain numbered or bulleted steps so maintainers can replicate the issue.",
  },
  {
    heading: "## Expected behavior",
    pattern: /\S{10,}/,
    required: true,
    guidanceIfMissing:
      "**Expected behavior** section must describe what you expected to happen.",
  },
  {
    heading: "## Environment",
    pattern: /[A-Za-z]+[:\-]\s*\S+/, // key: value pair pattern
    required: false,
    guidanceIfMissing:
      "**Environment** section is helpful — please include OS, runtime version, and package version if possible.",
  },
];

export function validateIssueBody(
  body: string,
  sections: TemplateSection[]
): ValidationResult {
  const missingSections: TemplateSection[] = [];

  for (const section of sections) {
    if (!section.required) continue;

    // Find the section in the body
    const headingIndex = body.indexOf(section.heading);
    if (headingIndex === -1) {
      missingSections.push(section);
      continue;
    }

    // Extract content between this heading and the next ## heading
    const afterHeading = body.slice(headingIndex + section.heading.length);
    const nextHeadingMatch = afterHeading.match(/\n##+ /);
    const sectionContent = nextHeadingMatch
      ? afterHeading.slice(0, nextHeadingMatch.index).trim()
      : afterHeading.trim();

    if (!section.pattern.test(sectionContent)) {
      missingSections.push(section);
    }
  }

  return {
    passed: missingSections.length === 0,
    missingSections,
  };
}
```

### 5. Admin bypass check

```typescript
// src/admin.ts
import type { Env } from "./types";

export async function isOrgAdmin(
  token: string,
  orgName: string,
  username: string
): Promise<boolean> {
  const res = await fetch(
    `https://api.github.com/orgs/${orgName}/memberships/${username}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } }
  );
  if (!res.ok) return false; // 404 = not a member, 403 = token lacks org scope
  const data = await res.json<{ role: string; state: string }>();
  return data.role === "admin" && data.state === "active";
}
```

### 6. Comment and label helpers

```typescript
// src/github.ts
import type { Env } from "./types";
import type { TemplateSection } from "./types";

export async function getInstallationToken(env: Env): Promise<string> {
  // See workers-issue-deduplication-embedding.md for the full JWT implementation
  // Abbreviated here for clarity
  const jwt = await createJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`,
    { method: "POST", headers: { Authorization: `Bearer ${jwt}`, Accept: "application/vnd.github+json" } }
  );
  const { token } = await res.json<{ token: string }>();
  return token;
}

export async function postValidationComment(
  token: string,
  repoFullName: string,
  issueNumber: number,
  missing: TemplateSection[]
): Promise<void> {
  const [owner, repo] = repoFullName.split("/");
  const items = missing.map((s) => `- ${s.guidanceIfMissing}`).join("\n");
  const body = [
    "Hi there! This issue is missing some required information. Please update the following sections:",
    "",
    items,
    "",
    "Once updated, a maintainer will review. Thank you!",
  ].join("\n");

  await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/comments`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    }
  );
}

export async function applyLabel(
  token: string,
  repoFullName: string,
  issueNumber: number,
  label: string
): Promise<void> {
  const [owner, repo] = repoFullName.split("/");
  await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/labels`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify({ labels: [label] }),
    }
  );
}

export async function ensureLabelExists(
  token: string,
  repoFullName: string,
  label: string,
  color = "e4e669"
): Promise<void> {
  const [owner, repo] = repoFullName.split("/");
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/labels/${encodeURIComponent(label)}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } }
  );
  if (res.status === 404) {
    await fetch(`https://api.github.com/repos/${owner}/${repo}/labels`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify({ name: label, color }),
    });
  }
}
```

### 7. Main queue consumer

```typescript
// src/index.ts
import type { Env } from "./types";
import { getInstallationToken, postValidationComment, applyLabel, ensureLabelExists } from "./github";
import { detectUsedTemplate } from "./templates";
import { BUG_REPORT_SECTIONS, validateIssueBody } from "./rules";
import { isOrgAdmin } from "./admin";
import type { IssueQueueMessage } from "./router-types";

export default {
  async queue(batch: MessageBatch<IssueQueueMessage>, env: Env): Promise<void> {
    const token = await getInstallationToken(env);

    for (const msg of batch.messages) {
      const { payload } = msg.body;
      if (payload.action !== "opened") { msg.ack(); continue; }

      const { issue, repository, sender } = payload;
      const body = issue.body ?? "";

      try {
        // Bypass for org admins
        const orgName = repository.full_name.split("/")[0];
        if (await isOrgAdmin(token, orgName, sender.login)) {
          console.log(`Skipping enforcement for org admin ${sender.login}`);
          msg.ack();
          continue;
        }

        // Detect which template was used
        const usedTemplate = await detectUsedTemplate(env, token, repository.full_name, body);
        if (!usedTemplate) {
          // No template detected — skip or apply a different rule set
          msg.ack();
          continue;
        }

        // Validate the issue body against the bug report template rules
        // (extend with per-template rule selection based on `usedTemplate`)
        const { passed, missingSections } = validateIssueBody(body, BUG_REPORT_SECTIONS);

        if (!passed) {
          await ensureLabelExists(token, repository.full_name, env.INCOMPLETE_LABEL);
          await postValidationComment(token, repository.full_name, issue.number, missingSections);
          await applyLabel(token, repository.full_name, issue.number, env.INCOMPLETE_LABEL);
          console.log(
            `Flagged ${repository.full_name}#${issue.number} as incomplete — missing: ` +
            missingSections.map((s) => s.heading).join(", ")
          );
        }

        msg.ack();
      } catch (err) {
        console.error(`Enforcement failed for ${repository.full_name}#${issue.number}:`, err);
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

**Template caching:** Templates change rarely; caching in KV for 1 hour is safe and avoids repeated GitHub API calls for busy repos. Invalidate by calling `TEMPLATE_CACHE.delete()` from a management endpoint if you push a template change.

**Template detection heuristic:** Counting heading overlap is simple and works for the common case where reporters retain the template structure. It fails for issues with highly custom headings or no headings at all. In the latter case, fall back to validating the full body against a generic minimum-length rule.

**Regex validation tradeoffs:** Regex patterns are intentionally permissive — they check for presence of content structure, not semantic correctness. Overly strict patterns (e.g., requiring specific version formats) generate false positives and frustrate reporters.

**Admin bypass scope:** The bypass checks org membership with the `admin` role. Adjust to `member` if you want all org members to bypass enforcement, or remove the bypass entirely for public repos.

## Anti-patterns

- **Do not validate every issue regardless of template.** Issues filed without a template (e.g., internal team issues) should not be penalised.
- **Do not close issues automatically for incomplete templates.** Comment and label first; auto-close after N days of inactivity should be done by a separate stale-bot configuration.
- **Do not cache templates indefinitely.** Template changes would not take effect until the Worker is redeployed; TTL-based expiry handles this gracefully.
- **Do not call `ensureLabelExists` on every message.** Cache the result in a module-level `Set` or in KV to avoid a redundant API call per issue.
- **Do not post the comment and apply the label in separate try/catch blocks without coordination.** If one fails, the other may succeed, leaving the issue in an inconsistent state.

## Gotchas

- GitHub's `issue.body` is `null` (not an empty string) if the reporter submits with no body. Always coerce with `?? ""`.
- Template heading detection (`body.indexOf(section.heading)`) is case-sensitive. Ensure the rules match the exact heading capitalisation in your template file.
- The GitHub App must have `Issues: Write` permission to post comments and apply labels.
- If the `needs-more-info` label does not exist in the repo, `POST /labels` will create it. Idempotent as long as `ensureLabelExists` is called first.
- Org membership endpoint returns 404 for users who are not org members and for organisations that have made membership private to non-admin tokens. Handle both gracefully (default to non-admin).

## Verification

```bash
# Deploy
npx wrangler deploy

# Open a test issue with an incomplete body in the target repo
# via GitHub UI or:
gh issue create --repo example-org/example-repo --title "Test: empty bug" --body "## Describe the bug\n\n## Steps to Reproduce\n\n## Expected behavior\n"

# Within ~30 seconds the bot should post a comment and apply the label
gh issue view <number> --repo example-org/example-repo --comments

# Tail logs
npx wrangler tail --format pretty
```

## Related

- `workers-github-issue-webhook-router.md` — upstream queue producer
- `workers-issue-deduplication-embedding.md` — companion consumer on the same event

## Sources

- https://docs.github.com/en/rest/issues/comments
- https://docs.github.com/en/rest/issues/labels
- https://docs.github.com/en/rest/orgs/members
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/kv/
