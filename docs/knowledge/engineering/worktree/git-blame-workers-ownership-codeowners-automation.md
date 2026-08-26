# git blame Data for Automated CODEOWNERS Generation in Workers Monorepos

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Workers monorepo has grown to 30+ packages and the `CODEOWNERS` file is perpetually
stale. The team that created `workers/payments` no longer owns it; the infra team added
workers they never recorded in `CODEOWNERS`. PR reviews land on the wrong people and merge
without the right sign-off. Running `git blame` across the recent commit history reveals the
actual ownership distribution — who has been committing to each package in the past 90 days
— and that data should drive `CODEOWNERS`, not human memory.

## Context

`git log --format` and `git blame` both expose authorship at line and commit granularity.
Aggregating commit frequency per directory per author gives an empirical ownership signal
that does not depend on org chart accuracy. The output is a ranked list of likely owners
per package, which a script can diff against the current `CODEOWNERS` and open a PR when
there is drift.

GitHub CODEOWNERS syntax: one pattern per line, followed by one or more `@owner` handles.
The last matching rule wins, so ordering matters. An automated script should place narrower
package-level rules after the broad fallback.

This pattern complements (not replaces) `codeowners-advanced-2026.md`, which documents the
governance model. This article covers the data pipeline.

## Commit-frequency Ownership Analysis

```typescript
// scripts/ownership-analysis.ts
import { execSync } from "node:child_process";

interface PackageOwnership {
  package: string;
  authors: { email: string; commits: number; percentage: number }[];
}

function getCommitsByAuthorForPath(
  dirPath: string,
  sinceDays = 90
): Map<string, number> {
  const since = new Date();
  since.setDate(since.getDate() - sinceDays);
  const sinceStr = since.toISOString().slice(0, 10);

  const raw = execSync(
    `git log --format="%ae" --since="${sinceStr}" -- "${dirPath}" 2>/dev/null || true`
  ).toString().trim();

  if (!raw) return new Map();

  const counts = new Map<string, number>();
  for (const email of raw.split("\n").filter(Boolean)) {
    counts.set(email, (counts.get(email) ?? 0) + 1);
  }
  return counts;
}

function analyzeWorkerPackages(
  workersDir = "workers",
  sinceDays = 90
): PackageOwnership[] {
  const { execSync: exec } = require("node:child_process");
  const fs = require("node:fs");
  const path = require("node:path");

  const root = execSync("git rev-parse --show-toplevel").toString().trim();
  const packagesPath = path.join(root, workersDir);

  if (!fs.existsSync(packagesPath)) return [];

  const packages = fs
    .readdirSync(packagesPath, { withFileTypes: true })
    .filter((d: { isDirectory: () => boolean }) => d.isDirectory())
    .map((d: { name: string }) => d.name);

  return packages.map((pkg: string) => {
    const relPath = `${workersDir}/${pkg}`;
    const commitsByAuthor = getCommitsByAuthorForPath(relPath, sinceDays);
    const total = [...commitsByAuthor.values()].reduce((a, b) => a + b, 0);

    const authors = [...commitsByAuthor.entries()]
      .map(([email, commits]) => ({
        email,
        commits,
        percentage: total > 0 ? Math.round((commits / total) * 100) : 0,
      }))
      .sort((a, b) => b.commits - a.commits);

    return { package: relPath, authors };
  });
}

export { analyzeWorkerPackages, PackageOwnership };
```

## Email-to-GitHub-Handle Mapping

```typescript
// scripts/email-to-github-handle.ts
// Resolves committer emails to GitHub handles via git mailmap and a local map
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

type EmailHandleMap = Record<string, string>;

function loadMailmap(root: string): EmailHandleMap {
  const mailmapPath = path.join(root, ".mailmap");
  if (!fs.existsSync(mailmapPath)) return {};

  const map: EmailHandleMap = {};
  for (const line of fs.readFileSync(mailmapPath, "utf8").split("\n")) {
    // Format: Proper Name <proper@email.com> <commit@email.com>
    const match = line.match(/^.*?<([^>]+)>\s+<([^>]+)>/);
    if (match) {
      map[match[2].toLowerCase()] = match[1].toLowerCase();
    }
  }
  return map;
}

function loadGithubHandleMap(mapPath: string): EmailHandleMap {
  if (!fs.existsSync(mapPath)) return {};
  return JSON.parse(fs.readFileSync(mapPath, "utf8"));
}

function resolveHandle(
  email: string,
  mailmap: EmailHandleMap,
  handleMap: EmailHandleMap
): string | null {
  const canonical = mailmap[email.toLowerCase()] ?? email.toLowerCase();
  return handleMap[canonical] ?? null;
}

export { loadMailmap, loadGithubHandleMap, resolveHandle };
```

## CODEOWNERS Generation Script

```typescript
// scripts/generate-codeowners.ts
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { analyzeWorkerPackages } from "./ownership-analysis";
import { loadMailmap, loadGithubHandleMap, resolveHandle } from "./email-to-github-handle";

const ROOT = execSync("git rev-parse --show-toplevel").toString().trim();
const CODEOWNERS_PATH = path.join(ROOT, ".github", "CODEOWNERS");
const HANDLE_MAP_PATH = path.join(ROOT, "scripts", "github-handles.json");
const GENERATED_HEADER = "# ─── AUTO-GENERATED SECTION — do not edit below this line ───";

const MINIMUM_COMMITS = 3;        // ignore drive-by authors
const MAX_OWNERS_PER_PACKAGE = 2; // avoid review-by-committee

function generateSection(handleMapPath: string): string {
  const mailmap = loadMailmap(ROOT);
  const handleMap = loadGithubHandleMap(handleMapPath);
  const ownerships = analyzeWorkerPackages("workers", 90);

  const lines: string[] = [GENERATED_HEADER, ""];

  for (const pkg of ownerships) {
    const owners = pkg.authors
      .filter((a) => a.commits >= MINIMUM_COMMITS)
      .slice(0, MAX_OWNERS_PER_PACKAGE)
      .map((a) => resolveHandle(a.email, mailmap, handleMap))
      .filter((h): h is string => h !== null)
      .map((h) => `@${h}`);

    if (owners.length === 0) continue;
    lines.push(`/${pkg.package}/   ${owners.join(" ")}`);
  }

  return lines.join("\n") + "\n";
}

function updateCodeowners(): void {
  const current = fs.existsSync(CODEOWNERS_PATH)
    ? fs.readFileSync(CODEOWNERS_PATH, "utf8")
    : "";

  const manual = current.split(GENERATED_HEADER)[0] ?? "";
  const generated = generateSection(HANDLE_MAP_PATH);

  fs.mkdirSync(path.dirname(CODEOWNERS_PATH), { recursive: true });
  fs.writeFileSync(CODEOWNERS_PATH, manual + generated);
  console.log(`CODEOWNERS updated at ${CODEOWNERS_PATH}`);
}

updateCodeowners();
```

## CI Drift Detection Workflow

```yaml
# .github/workflows/codeowners-drift.yml
name: CODEOWNERS Drift Check

on:
  schedule:
    - cron: "0 9 * * 1"   # every Monday at 09:00 UTC
  workflow_dispatch:

jobs:
  detect-drift:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0    # full history for blame analysis

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Regenerate CODEOWNERS
        run: npx tsx scripts/generate-codeowners.ts

      - name: Check for drift
        id: drift
        run: |
          if git diff --quiet .github/CODEOWNERS; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Open PR for drift
        if: steps.drift.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "chore: update CODEOWNERS from ownership analysis"
          title: "chore: CODEOWNERS drift detected — update ownership"
          body: |
            Automated CODEOWNERS update based on commit activity over the last 90 days.
            Review the diff and merge if the new owners reflect current team reality.
          branch: "chore/codeowners-update"
          labels: "maintenance,codeowners"
```

## Anti-patterns

- **Sole reliance on commit count**: a developer who bulk-formatted an entire package has
  hundreds of commits but zero domain ownership. Combine commit count with a recency weight
  or filter out commits that touch only non-logic files (`.md`, formatting-only diffs).
- **Overwriting the manual section**: the script above preserves everything above the
  `GENERATED_HEADER` line. Never write a script that replaces the entire file — the top of
  `CODEOWNERS` typically holds global fallback rules and security-team overrides.
- **Missing `github-handles.json`**: if the email-to-handle map is incomplete, the script
  silently omits owners. Log unmapped emails so they can be added.

## Gotchas

- `git log` counts merge commits. If your repo merges PRs into `main`, the PR author
  appears as a committer for the merge commit. Use `--no-merges` in the log command to
  measure only meaningful commits.
- GitHub evaluates `CODEOWNERS` on push to the default branch. A newly opened PR that
  introduces a new worker package will not have CODEOWNERS coverage until the generation
  script runs and the result is merged.
- The generated section must stay after global wildcard rules (`* @org/everyone`), or the
  narrow package rules will never match due to last-rule-wins semantics.

## Verification

```bash
# Dry-run: see what the script would generate without writing
npx tsx scripts/generate-codeowners.ts 2>&1 | head -40

# Confirm file structure is valid (GitHub validates on push)
cat .github/CODEOWNERS | grep -v "^#" | grep -v "^$" | head -20

# Check which owners a specific path resolves to
# (requires github CLI with owners extension or manual inspection)
grep "workers/payments" .github/CODEOWNERS
```

## Related

- `codeowners-advanced-2026.md`
- `git-blame-code-archaeology.md`
- `git-blame-ignore-revs-formatting-commits.md`
- `git-mailmap-blob-governance.md`
- `monorepo-package-boundary-enforcement-workers.md`

## Sources

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://git-scm.com/docs/git-log
- https://git-scm.com/docs/git-blame
- https://git-scm.com/docs/gitmailmap
