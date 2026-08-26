# Git Log Graph Visualization as CI Artifacts

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

After a series of hotfixes, cherry-picks, and rebase operations on a Cloudflare Workers monorepo, no one can tell at a glance which commits are on which branch or how the release tags relate to `main`. The team wants a visual commit graph attached to each CI run so deploy reviewers can audit branch topology without running git locally.

## Context

`git log --graph` produces an ASCII art DAG that is useful in a terminal but unreadable in CI log output and impossible to share with non-engineers. Generating an HTML or SVG graph from the git object database — using tools like `git-graph` (npm), `git log` with a custom pretty-format piped into a D3 renderer, or the lightweight `gitgraph.js` library — and uploading it as a GitHub Actions artifact turns branch topology into a shareable, linkable document. This is especially valuable in Workers monorepos where multiple deployment tracks (`workers-api`, `workers-auth`, release tags) create a complex DAG.

## Generating a Plain-Text and HTML Graph from git log

Start with the classic ASCII graph as a baseline. A well-formatted pretty-print can be processed by a small script into structured JSON:

```bash
#!/usr/bin/env bash
# scripts/generate-git-graph.sh
set -euo pipefail

OUTPUT_DIR="${1:-dist/git-graph}"
mkdir -p "$OUTPUT_DIR"

# 1. ASCII graph to a plain-text file (useful for quick diffs)
git log \
  --graph \
  --oneline \
  --decorate \
  --all \
  --date=short \
  --pretty=format:'%h|%ad|%an|%s|%D' \
  -n 150 \
  > "$OUTPUT_DIR/graph.txt"

echo "ASCII graph written to $OUTPUT_DIR/graph.txt"

# 2. Machine-readable JSON for the HTML renderer
git log \
  --all \
  -n 150 \
  --pretty=format:'{"sha":"%H","short":"%h","date":"%ad","author":"%an","message":"%s","refs":"%D","parents":"%P"},' \
  --date=short \
  | sed '$ s/,$//' \
  | sed '1s/^/[/' \
  | sed '$s/$/]/' \
  > "$OUTPUT_DIR/commits.json"

echo "JSON commit data written to $OUTPUT_DIR/commits.json"
```

## Building the HTML Visualization Artifact

Use a self-contained HTML file with inline JavaScript to render the graph. The file embeds the JSON produced above so it works offline and in the GitHub Actions artifact viewer:

```typescript
// scripts/build-graph-html.ts
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

interface Commit {
  sha: string;
  short: string;
  date: string;
  author: string;
  message: string;
  refs: string;
  parents: string;
}

const outputDir = resolve("dist/git-graph");
const commits: Commit[] = JSON.parse(
  readFileSync(resolve(outputDir, "commits.json"), "utf-8")
);

const workerBranchColors: Record<string, string> = {
  "workers-api": "#f6a800",
  "workers-auth": "#2563eb",
  main: "#16a34a",
  HEAD: "#dc2626",
};

function branchColor(refs: string): string {
  for (const [name, color] of Object.entries(workerBranchColors)) {
    if (refs.includes(name)) return color;
  }
  return "#6b7280";
}

const rows = commits
  .map(
    (c) => `
  <tr style="border-left: 4px solid ${branchColor(c.refs)}">
    <td><code>${c.short}</code></td>
    <td>${c.date}</td>
    <td>${c.author}</td>
    <td>${c.message.replace(/</g, "&lt;")}</td>
    <td><small>${c.refs.replace(/</g, "&lt;")}</small></td>
    <td><small><code>${c.parents.split(" ").map((p) => p.slice(0, 7)).join(" ")}</code></small></td>
  </tr>`
  )
  .join("\n");

const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Git Graph — Workers Monorepo</title>
  <style>
    body { font-family: ui-monospace, monospace; font-size: 13px; background: #0f172a; color: #e2e8f0; margin: 1rem; }
    h1 { color: #f1f5f9; font-size: 1.1rem; }
    table { border-collapse: collapse; width: 100%; }
    th { text-align: left; padding: 6px 8px; background: #1e293b; color: #94a3b8; }
    td { padding: 5px 8px; border-bottom: 1px solid #1e293b; vertical-align: top; }
    tr:hover td { background: #1e293b; }
    code { color: #7dd3fc; }
  </style>
</head>
<body>
<h1>Git Commit Graph — last 150 commits</h1>
<p>Generated: ${new Date().toISOString()}</p>
<table>
  <thead>
    <tr><th>SHA</th><th>Date</th><th>Author</th><th>Message</th><th>Refs</th><th>Parents</th></tr>
  </thead>
  <tbody>${rows}</tbody>
</table>
</body>
</html>`;

writeFileSync(resolve(outputDir, "index.html"), html, "utf-8");
console.log(`Graph HTML written to ${outputDir}/index.html`);
```

## Uploading the Graph as a GitHub Actions Artifact

Wire the generation and upload steps into the CI pipeline so every run produces a browsable graph:

```yaml
# .github/workflows/git-graph-artifact.yml
name: Git Graph Artifact

on:
  push:
    branches:
      - main
      - 'release/**'
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  build-graph:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Fetch full history so the graph includes all branches and tags
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - run: pnpm install --frozen-lockfile

      - name: Generate ASCII + JSON graph
        run: bash scripts/generate-git-graph.sh dist/git-graph

      - name: Build HTML artifact
        run: npx tsx scripts/build-graph-html.ts

      - name: Upload graph artifact
        uses: actions/upload-artifact@v4
        with:
          name: git-graph-${{ github.run_number }}
          path: dist/git-graph/
          retention-days: 30

      - name: Post graph link to PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `📊 **Git graph artifact** for this PR: View graph → Artifacts → git-graph-${context.runNumber}`
            });
```

## Anti-patterns

- Using `--depth=1` shallow clones in the CI job that generates the graph — the graph will show only one commit and no branch topology.
- Generating the graph only on `push` to `main` — the graph is most valuable during PR review to show the rebase or merge structure before landing.
- Embedding the full `git log --all` output with no `-n` limit in a large repo — graphs with tens of thousands of commits produce multi-megabyte artifacts and time out the renderer.
- Using a third-party graph service that sends commit metadata to an external server — commit messages often contain ticket numbers and internal context.

## Gotchas

- `actions/checkout@v4` defaults to `fetch-depth: 1` (shallow clone); always set `fetch-depth: 0` in the graph job or branch refs beyond HEAD will be missing.
- The `--decorate` output from `git log` includes `HEAD ->` references that change on every commit — do not use the ASCII graph output for diffing between runs.
- JSON output from `git log --pretty=format:...` will break if commit messages contain double quotes; escape with `--pretty=format` using `%f` (sanitized subject) or post-process with `jq --raw-input`.
- GitHub artifact URLs are scoped to the authenticated user's session; share the Actions run URL rather than the direct artifact download link with stakeholders.

## Verification

```bash
# Generate locally and open in browser
bash scripts/generate-git-graph.sh /tmp/git-graph
npx tsx scripts/build-graph-html.ts
open /tmp/git-graph/index.html   # macOS
xdg-open /tmp/git-graph/index.html  # Linux

# Confirm full history is available in CI clone
git log --oneline --all | wc -l
# Should be > 1 (fails if shallow clone was used)

# Validate JSON output
node -e "JSON.parse(require('fs').readFileSync('/tmp/git-graph/commits.json','utf8')); console.log('JSON valid');"
```

## Related

- `worktree/ci-cd-pipeline-2026.md`
- `worktree/github-actions-wrangler-deploy-pipeline.md`
- `worktree/git-worktree-parallel-ci-patterns.md`
- `worktree/git-range-diff-review-after-rebase.md`

## Sources

- https://git-scm.com/docs/git-log
- https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts
- https://gitgraph.js.org/
