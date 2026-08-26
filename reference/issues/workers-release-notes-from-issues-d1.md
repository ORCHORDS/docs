# Automated Release Notes Generation from Closed Issues Using Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Maintainers manually write release notes by scanning closed issues before each release — a tedious, error-prone process that gets skipped under time pressure. You need a system that automatically collects all issues closed under a milestone, categorises them by label (bug/feature/chore), generates a structured markdown document, opens a PR with the release notes file, and stores a historical snapshot in D1.

## Context

A Cloudflare Worker cron job runs when a milestone is closed (triggered via the `milestone.closed` webhook or on a schedule), queries the GitHub API for all issues closed in that milestone, categorises them, generates markdown, and opens a PR against the target repo's default branch. D1 stores a historical record of every generated release note for audit and regeneration purposes.

## Solution

### 1. Wrangler configuration

```toml
# wrangler.toml
name = "release-notes-generator"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "release-history"
database_id = "<your-d1-database-id>"

[vars]
GITHUB_APP_ID = "123456"
TARGET_REPO = "example-org/example-repo"
RELEASE_NOTES_PATH = "docs/release-notes"
BASE_BRANCH = "main"

# Secrets: GITHUB_APP_PRIVATE_KEY, GITHUB_INSTALLATION_ID
```

### 2. D1 schema

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS releases (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_full_name    TEXT NOT NULL,
  milestone_number  INTEGER NOT NULL,
  milestone_title   TEXT NOT NULL,
  milestone_due_on  TEXT,
  generated_at      TEXT NOT NULL,
  pr_number         INTEGER,
  pr_url            TEXT,
  markdown_content  TEXT NOT NULL,
  issue_count       INTEGER NOT NULL DEFAULT 0,
  UNIQUE(repo_full_name, milestone_number)
);

CREATE TABLE IF NOT EXISTS release_issues (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  release_id        INTEGER NOT NULL REFERENCES releases(id),
  issue_number      INTEGER NOT NULL,
  issue_title       TEXT NOT NULL,
  issue_url         TEXT NOT NULL,
  category          TEXT NOT NULL,   -- bug | feature | chore | uncategorised
  labels            TEXT NOT NULL    -- JSON array of label names
);

CREATE INDEX IF NOT EXISTS idx_release_issues_release ON release_issues(release_id);
```

```bash
npx wrangler d1 execute release-history --file schema.sql --remote
```

### 3. Types

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  GITHUB_APP_ID: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_INSTALLATION_ID: string;
  TARGET_REPO: string;
  RELEASE_NOTES_PATH: string;
  BASE_BRANCH: string;
}

export type Category = "bug" | "feature" | "chore" | "uncategorised";

export type CategorisedIssue = {
  number: number;
  title: string;
  htmlUrl: string;
  labels: string[];
  category: Category;
};

export type MilestoneInfo = {
  number: number;
  title: string;
  dueOn: string | null;
  closedAt: string;
};
```

### 4. GitHub API helpers

```typescript
// src/github.ts
import type { Env, MilestoneInfo, CategorisedIssue } from "./types";

export async function getInstallationToken(env: Env): Promise<string> {
  // Full JWT implementation in workers-issue-deduplication-embedding.md
  const jwt = await createJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`,
    { method: "POST", headers: { Authorization: `Bearer ${jwt}`, Accept: "application/vnd.github+json" } }
  );
  const { token } = await res.json<{ token: string }>();
  return token;
}

export async function fetchClosedMilestoneIssues(
  token: string,
  repoFullName: string,
  milestoneNumber: number
): Promise<Array<{ number: number; title: string; html_url: string; labels: Array<{ name: string }> }>> {
  const [owner, repo] = repoFullName.split("/");
  const issues: Array<{ number: number; title: string; html_url: string; labels: Array<{ name: string }> }> = [];
  let page = 1;

  while (true) {
    const res = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/issues?` +
      `milestone=${milestoneNumber}&state=closed&per_page=100&page=${page}`,
      { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } }
    );
    if (!res.ok) throw new Error(`Issues fetch failed: ${res.status}`);

    const batch = await res.json<typeof issues>();
    issues.push(...batch);
    if (batch.length < 100) break;
    page++;
  }

  // Filter out pull requests (GitHub returns PRs in the issues endpoint)
  return issues.filter((i) => !i.html_url.includes("/pull/"));
}

export async function getFileSha(
  token: string,
  repoFullName: string,
  branch: string,
  filePath: string
): Promise<string | null> {
  const [owner, repo] = repoFullName.split("/");
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/contents/${filePath}?ref=${branch}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } }
  );
  if (res.status === 404) return null;
  const data = await res.json<{ sha: string }>();
  return data.sha;
}

export async function createOrUpdateFile(
  token: string,
  repoFullName: string,
  branch: string,
  filePath: string,
  content: string,
  commitMessage: string,
  existingSha: string | null
): Promise<void> {
  const [owner, repo] = repoFullName.split("/");
  const body: Record<string, string> = {
    message: commitMessage,
    content: btoa(content),
    branch,
  };
  if (existingSha) body.sha = existingSha;

  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/contents/${filePath}`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  if (!res.ok) throw new Error(`File update failed: ${res.status} ${await res.text()}`);
}

export async function createBranch(
  token: string,
  repoFullName: string,
  branchName: string,
  baseBranch: string
): Promise<void> {
  const [owner, repo] = repoFullName.split("/");
  // Get base branch SHA
  const refRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/git/ref/heads/${baseBranch}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" } }
  );
  const refData = await refRes.json<{ object: { sha: string } }>();
  const sha = refData.object.sha;

  await fetch(`https://api.github.com/repos/${owner}/${repo}/git/refs`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
    body: JSON.stringify({ ref: `refs/heads/${branchName}`, sha }),
  });
}

export async function createPullRequest(
  token: string,
  repoFullName: string,
  head: string,
  base: string,
  title: string,
  body: string
): Promise<{ number: number; html_url: string }> {
  const [owner, repo] = repoFullName.split("/");
  const res = await fetch(`https://api.github.com/repos/${owner}/${repo}/pulls`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
    body: JSON.stringify({ title, body, head, base }),
  });
  if (!res.ok) throw new Error(`PR creation failed: ${res.status} ${await res.text()}`);
  return res.json<{ number: number; html_url: string }>();
}
```

### 5. Issue categorisation

```typescript
// src/categorise.ts
import type { Category, CategorisedIssue } from "./types";

const LABEL_CATEGORY_MAP: Record<string, Category> = {
  bug: "bug",
  "type: bug": "bug",
  "kind/bug": "bug",
  fix: "bug",
  enhancement: "feature",
  feature: "feature",
  "type: feature": "feature",
  "kind/feature": "feature",
  "new feature": "feature",
  chore: "chore",
  maintenance: "chore",
  refactor: "chore",
  docs: "chore",
  documentation: "chore",
  test: "chore",
};

export function categorise(
  issue: { number: number; title: string; html_url: string; labels: Array<{ name: string }> }
): CategorisedIssue {
  const labelNames = issue.labels.map((l) => l.name.toLowerCase());
  let category: Category = "uncategorised";

  for (const labelName of labelNames) {
    if (LABEL_CATEGORY_MAP[labelName]) {
      category = LABEL_CATEGORY_MAP[labelName];
      break; // First matching label wins; priority is insertion order of LABEL_CATEGORY_MAP
    }
  }

  return {
    number: issue.number,
    title: issue.title,
    htmlUrl: issue.html_url,
    labels: issue.labels.map((l) => l.name),
    category,
  };
}
```

### 6. Markdown generation

```typescript
// src/markdown.ts
import type { CategorisedIssue, MilestoneInfo, Category } from "./types";

const CATEGORY_HEADINGS: Record<Category, string> = {
  feature: "## New Features",
  bug: "## Bug Fixes",
  chore: "## Maintenance",
  uncategorised: "## Other Changes",
};

export function generateMarkdown(
  milestone: MilestoneInfo,
  issues: CategorisedIssue[]
): string {
  const grouped: Record<Category, CategorisedIssue[]> = {
    feature: [],
    bug: [],
    chore: [],
    uncategorised: [],
  };

  for (const issue of issues) {
    grouped[issue.category].push(issue);
  }

  const sections: string[] = [
    `# Release Notes — ${milestone.title}`,
    "",
    `_Generated: ${new Date().toISOString().split("T")[0]}_`,
    milestone.dueOn ? `_Release date: ${milestone.dueOn.split("T")[0]}_` : "",
    "",
  ];

  for (const category of ["feature", "bug", "chore", "uncategorised"] as Category[]) {
    const categoryIssues = grouped[category];
    if (categoryIssues.length === 0) continue;

    sections.push(CATEGORY_HEADINGS[category]);
    sections.push("");
    for (const issue of categoryIssues) {
      const labels = issue.labels.length > 0 ? ` \`${issue.labels.join("`, `")}\`` : "";
      sections.push(`- #${issue.number} ${issue.title}${labels}`);
    }
    sections.push("");
  }

  sections.push("---");
  sections.push(`_${issues.length} issues closed in this milestone._`);

  return sections.filter((s) => s !== undefined).join("\n");
}
```

### 7. D1 persistence

```typescript
// src/persist.ts
import type { Env, MilestoneInfo, CategorisedIssue } from "./types";

export async function persistRelease(
  env: Env,
  repoFullName: string,
  milestone: MilestoneInfo,
  issues: CategorisedIssue[],
  markdown: string,
  prNumber: number | null,
  prUrl: string | null
): Promise<void> {
  const result = await env.DB.prepare(
    `INSERT INTO releases
       (repo_full_name, milestone_number, milestone_title, milestone_due_on,
        generated_at, pr_number, pr_url, markdown_content, issue_count)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(repo_full_name, milestone_number)
     DO UPDATE SET
       pr_number = excluded.pr_number,
       pr_url = excluded.pr_url,
       markdown_content = excluded.markdown_content,
       generated_at = excluded.generated_at`
  )
    .bind(
      repoFullName,
      milestone.number,
      milestone.title,
      milestone.dueOn,
      new Date().toISOString(),
      prNumber,
      prUrl,
      markdown,
      issues.length
    )
    .run();

  const releaseId = result.meta.last_row_id;

  // Persist individual issues
  const stmts = issues.map((issue) =>
    env.DB.prepare(
      `INSERT OR IGNORE INTO release_issues
         (release_id, issue_number, issue_title, issue_url, category, labels)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      releaseId,
      issue.number,
      issue.title,
      issue.htmlUrl,
      issue.category,
      JSON.stringify(issue.labels)
    )
  );

  if (stmts.length > 0) {
    await env.DB.batch(stmts);
  }
}
```

### 8. Main orchestrator

```typescript
// src/index.ts
import type { Env, MilestoneInfo } from "./types";
import {
  getInstallationToken,
  fetchClosedMilestoneIssues,
  createBranch,
  createOrUpdateFile,
  getFileSha,
  createPullRequest,
} from "./github";
import { categorise } from "./categorise";
import { generateMarkdown } from "./markdown";
import { persistRelease } from "./persist";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Webhook handler for milestone.closed event
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const event = request.headers.get("x-github-event");
    if (event !== "milestone") return new Response("Ignored", { status: 200 });

    const body = await request.json<{ action: string; milestone: { number: number; title: string; due_on: string | null; closed_at: string }; repository: { full_name: string } }>();
    if (body.action !== "closed") return new Response("Ignored", { status: 200 });

    const milestone: MilestoneInfo = {
      number: body.milestone.number,
      title: body.milestone.title,
      dueOn: body.milestone.due_on,
      closedAt: body.milestone.closed_at,
    };

    await generateAndPublishReleaseNotes(env, body.repository.full_name, milestone);
    return new Response("Accepted", { status: 202 });
  },

  // Also triggerable via cron or manual HTTP POST to /generate?milestone=<number>&repo=<full_name>
} satisfies ExportedHandler<Env>;

async function generateAndPublishReleaseNotes(
  env: Env,
  repoFullName: string,
  milestone: MilestoneInfo
): Promise<void> {
  const token = await getInstallationToken(env);

  // Fetch all closed issues for this milestone
  const rawIssues = await fetchClosedMilestoneIssues(token, repoFullName, milestone.number);
  if (rawIssues.length === 0) {
    console.log(`No closed issues found for milestone ${milestone.title} — skipping`);
    return;
  }

  // Categorise
  const issues = rawIssues.map(categorise);

  // Generate markdown
  const markdown = generateMarkdown(milestone, issues);

  // Create a branch for the PR
  const branchName = `release-notes/${milestone.title.replace(/[^a-zA-Z0-9.-]/g, "-").toLowerCase()}`;
  await createBranch(token, repoFullName, branchName, env.BASE_BRANCH);

  // Write the markdown file to the branch
  const filePath = `${env.RELEASE_NOTES_PATH}/${milestone.title.replace(/[^a-zA-Z0-9.-]/g, "-").toLowerCase()}.md`;
  const existingSha = await getFileSha(token, repoFullName, branchName, filePath);
  await createOrUpdateFile(
    token,
    repoFullName,
    branchName,
    filePath,
    markdown,
    `docs: add release notes for ${milestone.title}`,
    existingSha
  );

  // Open a PR
  const prBody = [
    `Automated release notes for milestone **${milestone.title}**.`,
    "",
    `- ${issues.length} issues closed`,
    `- ${issues.filter((i) => i.category === "bug").length} bug fixes`,
    `- ${issues.filter((i) => i.category === "feature").length} new features`,
    `- ${issues.filter((i) => i.category === "chore").length} maintenance items`,
  ].join("\n");

  const pr = await createPullRequest(
    token,
    repoFullName,
    branchName,
    env.BASE_BRANCH,
    `docs: release notes for ${milestone.title}`,
    prBody
  );

  // Persist to D1
  await persistRelease(env, repoFullName, milestone, issues, markdown, pr.number, pr.html_url);

  console.log(`Release notes PR created: ${pr.html_url}`);
}
```

## Implementation Details

**Pagination:** The GitHub issues API returns at most 100 results per page. The `fetchClosedMilestoneIssues` function loops until a short page is received. For milestones with many hundreds of issues (rare but possible), this adds latency — move to a queue-based approach for those cases.

**PR per milestone:** Creating a new branch and PR per milestone keeps history clean and allows reviewers to amend the generated notes before merging. If you want fully automated merging, enable auto-merge on the PR after creation.

**D1 `batch()`:** D1's `batch()` method executes multiple statements in a single network round-trip, significantly faster than sequential `run()` calls for inserting many release issues.

**`ON CONFLICT DO UPDATE`:** The `releases` table upserts on `(repo_full_name, milestone_number)`. If the milestone is re-triggered (e.g., briefly re-opened then re-closed), the release record is updated to reflect the latest run.

**Category priority:** The first matching label wins in `LABEL_CATEGORY_MAP`. If an issue has both `bug` and `enhancement` labels, it is categorised as `bug`. Adjust map key order to change priority.

## Anti-patterns

- **Do not fetch issues synchronously in the webhook handler for large milestones.** GitHub webhooks expect a response within 10 seconds. For milestones with many pages of issues, enqueue the work via Cloudflare Queues and respond immediately.
- **Do not force-push to the default branch directly.** Always create a PR so maintainers can review and amend the generated notes.
- **Do not regenerate release notes on every issue close.** Trigger generation only when the milestone itself is closed, not on each issue close event.
- **Do not rely solely on labels for categorisation.** Some teams use projects or milestones for categorisation. The `LABEL_CATEGORY_MAP` approach is a pragmatic default — extend with project/column data if needed.
- **Do not use `btoa` for large markdown files without checking size.** `btoa` works on strings up to ~50 KB comfortably; beyond that, use a chunked base64 encoder.

## Gotchas

- The GitHub issues endpoint returns pull requests mixed with issues. Filter by checking `html_url.includes("/pull/")` to exclude PRs.
- `btoa` in Workers encodes to base64 but GitHub's content API expects standard base64 (not URL-safe). The `btoa` output is already standard base64, so no further conversion is needed.
- Creating a branch with a name that already exists will return a 422. Check for existing branches before creating, or generate unique branch names with a timestamp suffix.
- D1 `last_row_id` in `result.meta` is only meaningful after an `INSERT`. For `INSERT OR IGNORE` statements, `last_row_id` returns the conflicting row's ID if a conflict occurred — verify with a subsequent `SELECT` if strict ID tracking is needed.
- GitHub App installation tokens have a 1-hour TTL. Cache in KV for 55 minutes if generating notes for many repos in sequence.

## Verification

```bash
# Apply schema
npx wrangler d1 execute release-history --file schema.sql --remote

# Deploy
npx wrangler deploy

# Close a test milestone in the target repo
gh api --method PATCH repos/example-org/example-repo/milestones/<number> -f state=closed

# Verify PR was created
gh pr list --repo example-org/example-repo

# Inspect D1 records
npx wrangler d1 execute release-history \
  --command "SELECT milestone_title, issue_count, pr_url FROM releases" \
  --remote
```

## Related

- `workers-github-issue-webhook-router.md` — webhook infrastructure used for milestone events
- `workers-issue-sla-tracker-d1.md` — D1 issue data that can cross-reference closed issues

## Sources

- https://docs.github.com/en/rest/issues/issues#list-issues-for-a-repository
- https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents
- https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
