# git shortlog Contributor Attribution in a Cloudflare Workers Monorepo

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Workers monorepo grows to 8+ services owned by different teams. Engineering leadership asks: who is actively maintaining each service, who are the domain experts for a given Worker or D1 migration, and which contributors have touched authentication logic across the entire repo? Manually hunting through GitHub commit history per-directory is slow and produces inconsistent answers.

`git shortlog` answers all three questions in seconds and integrates cleanly into GitHub Actions to produce living contributor reports.

---

## Context

`git shortlog` summarises `git log` output by author, grouping commits per contributor. Combined with `--` path filters, `--since`/`--until` date windows, and `--mailmap` identity normalisation, it becomes a precise attribution tool for monorepos where a single contributor may appear under multiple email addresses (personal laptop, CI bot, work email).

This is especially valuable in Cloudflare Workers projects where ownership of individual services, D1 schema migrations, KV namespace configs, and Wrangler environment files is often implicit rather than declared in CODEOWNERS.

---

## Basic Usage: Who Owns Which Worker

```bash
# Top contributors to the auth Worker in the last 90 days
git shortlog -sn --since="90 days ago" -- apps/auth-worker/

# -s  = summary (commit count only, no commit messages)
# -n  = sort by commit count descending
# Output:
#   42  alice@example.com
#   18  bob@example.com
#    3  renovate[bot]@users.noreply.github.com

# Show commit messages grouped by author (omit -s)
git shortlog --since="90 days ago" -- apps/auth-worker/
```

Filter bots out of the report:

```bash
git shortlog -sn --since="90 days ago" -- apps/auth-worker/ \
  | grep -v '\[bot\]'
```

---

## .mailmap: Identity Normalisation

Without mailmap, one developer appears under three identities. Create `.mailmap` in the repo root:

```text
# .mailmap
# Format: Canonical Name <canonical@email> Commit Name <commit@email>
Alice Smith <alice@example.com> alice <alice@personal.dev>
Alice Smith <alice@example.com> Alice S <asmith@contractor.io>
Bob Jones <bob@example.com> bjones <bob@olddomain.com>
```

Git automatically applies `.mailmap` to `git shortlog`, `git log --format=%aN`, and `git blame`. No flag required.

Verify normalisation:

```bash
git shortlog -sne --since="1 year ago" | head -20
# -e shows the canonical email after mailmap resolution
```

---

## Per-Service Attribution Script

Generate a machine-readable attribution report for all Workers in the monorepo:

```typescript
// scripts/attribution-report.ts
import { execSync } from "node:child_process";
import { readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const APPS_DIR = "apps";
const SINCE = "180 days ago";

interface Contributor {
  name: string;
  commits: number;
}

interface ServiceReport {
  service: string;
  path: string;
  contributors: Contributor[];
}

function shortlogForPath(path: string): Contributor[] {
  const raw = execSync(
    `git shortlog -sne --since="${SINCE}" -- ${path}`,
    { encoding: "utf8" }
  ).trim();

  if (!raw) return [];

  return raw
    .split("\n")
    .map((line) => {
      const match = line.trim().match(/^(\d+)\s+(.+)\s+<.+>$/);
      if (!match) return null;
      return { commits: parseInt(match[1], 10), name: match[2].trim() };
    })
    .filter((x): x is Contributor => x !== null);
}

const services = readdirSync(APPS_DIR).filter((entry) =>
  statSync(join(APPS_DIR, entry)).isDirectory()
);

const report: ServiceReport[] = services.map((service) => ({
  service,
  path: join(APPS_DIR, service),
  contributors: shortlogForPath(join(APPS_DIR, service)),
}));

writeFileSync(
  "attribution-report.json",
  JSON.stringify({ generated: new Date().toISOString(), services: report }, null, 2)
);

// Print summary table
for (const { service, contributors } of report) {
  const top = contributors[0]?.name ?? "—";
  const count = contributors[0]?.commits ?? 0;
  console.log(`${service.padEnd(30)} top: ${top} (${count} commits)`);
}
```

```bash
npx tsx scripts/attribution-report.ts
```

---

## D1 Migration Ownership

D1 migration files live under `migrations/` and represent high-risk schema changes. Find who has authored each migration:

```bash
# Who has touched any D1 migration in the last year?
git shortlog -sn --since="1 year ago" -- migrations/

# Which contributor wrote a specific migration?
git log --format="%an <%ae>" -- "migrations/0012_add_sessions_table.sql"

# Full authorship audit of all migration files
git shortlog -sne -- migrations/*.sql
```

Surface expert reviewers for migration PRs by piping into a GitHub CLI command:

```bash
EXPERT=$(git shortlog -sne --since="1 year ago" -- migrations/ \
  | grep -v '\[bot\]' \
  | head -1 \
  | sed 's/.*<\(.*\)>/\1/')

echo "Suggested migration reviewer: $EXPERT"
# Use in CI to auto-request review:
# gh pr edit $PR_NUMBER --add-reviewer "$EXPERT"
```

---

## GitHub Actions: Weekly Attribution Report

```yaml
# .github/workflows/attribution-report.yml
name: Weekly Attribution Report

on:
  schedule:
    - cron: "0 9 * * 1"   # Monday 09:00 UTC
  workflow_dispatch:

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0    # full history required for shortlog

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - run: npm ci

      - name: Generate attribution report
        run: npx tsx scripts/attribution-report.ts

      - name: Upload report artifact
        uses: actions/upload-artifact@v4
        with:
          name: attribution-report-${{ github.run_id }}
          path: attribution-report.json
          retention-days: 90
```

Note: `fetch-depth: 0` is mandatory. A shallow clone (`fetch-depth: 1`) causes `git shortlog` to see only one commit and return misleading results.

---

## Anti-patterns

- **Running `git shortlog` on a shallow clone** — GitHub Actions checks out with `fetch-depth: 1` by default. Always set `fetch-depth: 0` for any history-based analysis.
- **Using raw commit emails without `.mailmap`** — one person appears as 3–4 distinct contributors, distorting ownership metrics.
- **Treating commit count as the only ownership signal** — a developer who wrote 2 critical security patches owns more context than one who wrote 40 dependency bumps. Combine shortlog with `git log --diff-filter=A` (file creations) for a fuller picture.
- **Not excluding bots** — Renovate, Dependabot, and wrangler-action appear as top contributors in many repos. Always filter `[bot]` entries from stakeholder-facing reports.

---

## Gotchas

- `git shortlog` respects `.mailmap` automatically but only if the file is in the repository root — a `.mailmap` in a subdirectory is ignored.
- The `--since` flag is relative to the current clock, not to any commit's date. CI jobs running at different times will produce subtly different counts; use explicit ISO dates for reproducible snapshots: `--since="2026-01-01" --until="2026-07-01"`.
- In a monorepo where the same service was previously at a different path (e.g., renamed from `services/auth` to `apps/auth-worker`), `git shortlog -- apps/auth-worker/` misses all history before the rename. Use `git log --follow` (see related article) first to identify renames, then pass both paths.
- Commit squash-merge strategies (common in GitHub) attribute all work to the PR author who pressed "Merge". If the team uses squash merges, shortlog reflects PR mergers, not individual committers.

---

## Verification

```bash
# Verify mailmap is applied
git shortlog -sne HEAD~50..HEAD | head -10

# Confirm full history is available (non-shallow)
git rev-parse --is-shallow-repository
# Should print: false

# Quick sanity check on a known-active directory
git shortlog -sn --since="30 days ago" -- apps/ | head -5

# Validate the TypeScript report script without committing
npx tsx scripts/attribution-report.ts 2>&1 | head -20
```

---

## Related

- `git-blame-code-archaeology.md`
- `git-log-follow-file-history-workers.md`
- `monorepo-workspace-cloudflare-workers.md`
- `codeowners-advanced-2026.md`
- `documentation-ownership-model.md`

---

## Sources

- git-shortlog documentation: https://git-scm.com/docs/git-shortlog
- git-mailmap documentation: https://git-scm.com/docs/gitmailmap
- Cloudflare D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- GitHub Actions checkout action: https://github.com/actions/checkout
