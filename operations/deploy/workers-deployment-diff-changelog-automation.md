# Workers Deployment Diff and Changelog Automation

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

After a production incident, the on-call engineer cannot determine which
Workers deployment introduced the breaking change because deploy history in
the Cloudflare dashboard shows only version IDs with no human-readable
summary. Correlating a version ID back to a Git commit and understanding
what changed — routes, bindings, D1 schema, KV namespaces — takes 20 minutes
of manual investigation that a changelog artifact would have made instant.

## Context

Cloudflare's Versions API records every Workers upload with a metadata blob
that can hold a `message` field set via `--message` in `wrangler versions
upload`. Combining that message with an automated diff of `wrangler.toml`
changes, D1 migration files added since the last deploy tag, and KV namespace
binding changes produces a structured changelog that CI posts to Slack and
writes as a GitHub release note. The key is tagging each production deploy in
Git so the diff range is always deterministic.

## Setting the Deploy Message and Git Tag

Every deploy pipeline must set `--message` with the Git SHA and a short
description, then tag the commit in Git so future diffs have a clean base.

```yaml
# .github/workflows/deploy.yml  (excerpt — jobs.deploy.steps)
- name: Upload Worker version
  id: upload
  run: |
    VERSION_ID=$(npx wrangler versions upload \
      --env production \
      --message "${{ github.sha }} — ${{ github.event.head_commit.message }}" \
      | grep "Version ID" | awk '{print $NF}')
    echo "version_id=$VERSION_ID" >> "$GITHUB_OUTPUT"
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

- name: Tag deploy in Git
  run: |
    git config user.email "ci@example.com"
    git config user.name "CI"
    git tag "deploy/production/$(date -u +%Y%m%dT%H%M%SZ)"
    git push origin --tags
```

## Generating the Diff Changelog

A TypeScript script computes the diff between the last `deploy/production/*`
tag and `HEAD`, grouping changes by category: code, bindings, crons, D1
migrations.

```typescript
// scripts/generate-deploy-changelog.ts
import { execSync } from "child_process";
import fs from "fs";

interface DeployChangelog {
  fromTag: string;
  toSha: string;
  commitMessages: string[];
  wranglerTomlChanged: boolean;
  d1MigrationsAdded: string[];
  bindingChanges: string[];
  cronChanges: string[];
  generatedAt: string;
}

function git(cmd: string): string {
  return execSync(`git ${cmd}`, { encoding: "utf8" }).trim();
}

function generateChangelog(): DeployChangelog {
  // Find last production deploy tag
  const tags = git(
    "tag --list 'deploy/production/*' --sort=-version:refname"
  ).split("\n");
  const lastTag = tags[0] ?? "HEAD~50";

  const toSha = git("rev-parse HEAD");

  // Commit messages in range
  const log = git(`log ${lastTag}..HEAD --oneline --no-merges`);
  const commitMessages = log ? log.split("\n") : [];

  // Changed files
  const changedFiles = git(`diff --name-only ${lastTag}..HEAD`).split("\n");

  // D1 migration files added
  const d1MigrationsAdded = changedFiles.filter(
    (f) => f.startsWith("migrations/") && f.endsWith(".sql")
  );

  // wrangler.toml changed?
  const wranglerTomlChanged = changedFiles.some((f) =>
    f.match(/wrangler(\.production)?\.toml$/)
  );

  // Parse binding changes from wrangler.toml diff
  const bindingChanges: string[] = [];
  const cronChanges: string[] = [];

  if (wranglerTomlChanged) {
    const diff = git(`diff ${lastTag}..HEAD -- wrangler.toml`);
    const addedLines = diff
      .split("\n")
      .filter((l) => l.startsWith("+") && !l.startsWith("+++"));
    const removedLines = diff
      .split("\n")
      .filter((l) => l.startsWith("-") && !l.startsWith("---"));

    for (const line of addedLines) {
      if (line.includes("binding =")) bindingChanges.push(`+ ${line.slice(1).trim()}`);
      if (line.includes("cron =") || line.includes('"*/')) cronChanges.push(`+ ${line.slice(1).trim()}`);
    }
    for (const line of removedLines) {
      if (line.includes("binding =")) bindingChanges.push(`- ${line.slice(1).trim()}`);
      if (line.includes("cron =") || line.includes('"*/')) cronChanges.push(`- ${line.slice(1).trim()}`);
    }
  }

  return {
    fromTag: lastTag,
    toSha,
    commitMessages,
    wranglerTomlChanged,
    d1MigrationsAdded,
    bindingChanges,
    cronChanges,
    generatedAt: new Date().toISOString(),
  };
}

function formatMarkdown(cl: DeployChangelog): string {
  const lines: string[] = [
    `## Workers Deploy Changelog`,
    `**Range:** \`${cl.fromTag}\` → \`${cl.toSha.slice(0, 8)}\``,
    `**Date:** ${cl.generatedAt}`,
    "",
    "### Commits",
    ...cl.commitMessages.map((m) => `- ${m}`),
  ];

  if (cl.d1MigrationsAdded.length > 0) {
    lines.push("", "### D1 Migrations Applied");
    cl.d1MigrationsAdded.forEach((f) => lines.push(`- \`${f}\``));
  }

  if (cl.bindingChanges.length > 0) {
    lines.push("", "### Binding Changes");
    cl.bindingChanges.forEach((b) => lines.push(`- ${b}`));
  }

  if (cl.cronChanges.length > 0) {
    lines.push("", "### Cron Schedule Changes");
    cl.cronChanges.forEach((c) => lines.push(`- ${c}`));
  }

  return lines.join("\n");
}

const changelog = generateChangelog();
const md = formatMarkdown(changelog);
fs.writeFileSync("deploy-changelog.md", md);
console.log(md);
```

## Posting the Changelog to Slack and GitHub Release

```typescript
// scripts/post-changelog.ts
import fs from "fs";

async function postToSlack(markdown: string, webhookUrl: string) {
  const text = markdown.slice(0, 2900); // Slack block limit
  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      blocks: [
        {
          type: "section",
          text: { type: "mrkdwn", text: `*Workers Deploy*\n${text}` },
        },
      ],
    }),
  });
}

async function createGitHubRelease(
  markdown: string,
  tag: string,
  token: string,
  repo: string
) {
  const [owner, name] = repo.split("/");
  await fetch(`https://api.github.com/repos/${owner}/${name}/releases`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tag_name: tag,
      name: `Production Deploy ${new Date().toISOString().slice(0, 10)}`,
      body: markdown,
      prerelease: false,
    }),
  });
}

const markdown = fs.readFileSync("deploy-changelog.md", "utf8");
const deployTag = `deploy/production/${new Date().toISOString().replace(/[:.]/g, "-")}`;

await postToSlack(markdown, process.env.SLACK_WEBHOOK_URL!);
await createGitHubRelease(
  markdown,
  deployTag,
  process.env.GITHUB_TOKEN!,
  process.env.GITHUB_REPOSITORY!
);
```

## Anti-patterns

- Using commit count or timestamp as the diff base instead of a Git tag;
  timezone differences and force-pushes make the range non-deterministic.
- Including the full diff body in Slack notifications; post a summary with a
  link to the GitHub release for the full changelog.
- Generating the changelog after a failed deploy; always generate it before
  promoting the version so the artifact exists even if the deploy is rolled
  back.

## Gotchas

- `wrangler versions upload --message` has a 100-character limit; truncate
  commit messages before passing them.
- Git tags pushed from CI require the repository to allow tag creation from
  Actions; set `contents: write` on the workflow's permissions block.

## Verification

```bash
# List last 5 production deploy tags
git tag --list 'deploy/production/*' --sort=-version:refname | head -5

# Preview changelog for current branch vs last deploy
npx tsx scripts/generate-deploy-changelog.ts

# Check version message set in Cloudflare
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/api-worker/versions" \
  | jq '.result[0] | {id: .id, message: .metadata.message}'
```

## Related

- `deploy/changelog-generation.md`
- `deploy/deployment-audit-trail-provenance.md`
- `deploy/workers-binding-version-management.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/
- https://docs.github.com/en/rest/releases/releases
