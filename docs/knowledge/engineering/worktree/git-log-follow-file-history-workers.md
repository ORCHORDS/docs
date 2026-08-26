# git log --follow File History Across Renames in Cloudflare Workers Projects

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker file is renamed or moved — `src/handler.ts` becomes `src/routes/api-handler.ts`, or an entire service is restructured from `services/auth/` to `apps/auth-worker/`. Standard `git log src/routes/api-handler.ts` only shows commits after the rename. The original bug-introduction commit, the architect who designed the file, and the rollback history are all invisible. `git log --follow` restores the full timeline.

---

## Context

Git tracks content by blob hash, not by path. When a file is renamed, git can detect the rename heuristically by comparing blob similarity above a threshold (default 50%). `git log --follow` applies this rename detection retroactively, walking back through history even when the path changed. This is especially important in Cloudflare Workers projects where:

- Workers are refactored from single-file scripts into modular routers.
- D1 migration files are moved between `db/migrations/` and `migrations/`.
- KV namespace wrappers are extracted into shared packages.
- Wrangler config files are split from monolithic `wrangler.toml` into per-service files.

---

## Basic --follow Usage

```bash
# Full commit history of a file, including before any renames
git log --follow --oneline src/routes/api-handler.ts

# With diff patches (shows exactly what changed at each point)
git log --follow -p src/routes/api-handler.ts

# Summary statistics per commit
git log --follow --stat src/routes/api-handler.ts

# Show author, date, and rename events
git log --follow --format="%h %ad %an — %s" --date=short \
  src/routes/api-handler.ts
```

---

## Tuning the Rename Detection Threshold

The default similarity threshold is 50%. Heavily edited files that were also renamed may not be tracked across the rename. Lower the threshold to catch them:

```bash
# Require only 30% similarity to detect a rename
git log --follow -M30 -- src/routes/api-handler.ts

# Show all detected renames in the history
git log --follow --diff-filter=R --name-status \
  -- src/routes/api-handler.ts

# Example output:
# R095  src/handler.ts  src/routes/api-handler.ts
# (R = rename, 095 = 95% similarity)
```

---

## Investigating D1 Migration File History

D1 migration files must never be edited after they run in production. Use `--follow` to audit whether a migration was touched post-creation:

```bash
# Full history of a specific migration
git log --follow --stat -- migrations/0015_create_sessions.sql

# If more than one commit appears, investigate every subsequent commit:
git log --follow -p -- migrations/0015_create_sessions.sql

# Check if a migration was ever renamed (schema directory restructuring)
git log --follow --diff-filter=R --name-status \
  -- migrations/0015_create_sessions.sql
```

An ideal migration shows exactly one commit (the one that added it). Any additional commits are a red flag.

---

## Scripted History Audit for All Worker Source Files

```typescript
// scripts/file-history-audit.ts
import { execSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

interface FileAudit {
  path: string;
  commitCount: number;
  firstCommitHash: string;
  firstCommitDate: string;
  renames: string[];
}

function auditFile(filePath: string): FileAudit {
  const logOutput = execSync(
    `git log --follow --format="%H %ad" --date=short -- "${filePath}"`,
    { encoding: "utf8" }
  ).trim();

  const commits = logOutput ? logOutput.split("\n") : [];
  const last = commits[commits.length - 1] ?? "";
  const [firstHash = "", firstDate = ""] = last.split(" ");

  const renameOutput = execSync(
    `git log --follow --diff-filter=R --name-status --format="" -- "${filePath}"`,
    { encoding: "utf8" }
  ).trim();

  const renames = renameOutput
    ? renameOutput
        .split("\n")
        .filter((l) => l.startsWith("R"))
        .map((l) => l.replace(/^R\d+\s+/, ""))
    : [];

  return {
    path: filePath,
    commitCount: commits.length,
    firstCommitHash: firstHash,
    firstCommitDate: firstDate,
    renames,
  };
}

// Audit all TypeScript source files in a Worker
function collectFiles(dir: string, ext: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) results.push(...collectFiles(full, ext));
    else if (entry.name.endsWith(ext)) results.push(full);
  }
  return results;
}

const files = collectFiles("src", ".ts");
const audits = files.map(auditFile);

// Flag files with renames in their history
const renamed = audits.filter((a) => a.renames.length > 0);
console.log("\nFiles with rename history:");
for (const a of renamed) {
  console.log(`  ${a.path}`);
  for (const r of a.renames) console.log(`    was: ${r}`);
}

console.log(`\nTotal source files: ${files.length}`);
console.log(`Files renamed at least once: ${renamed.length}`);
```

---

## Recovering the Original Author After a File Move

When a Worker is moved between directories, `git blame` on the new path only shows who did the move. Combine `--follow` with blame:

```bash
# See the original blame (before any renames)
ORIGINAL_PATH=$(
  git log --follow --diff-filter=R --name-only --format="" \
    -- src/routes/api-handler.ts \
  | tail -1
)

echo "Original path: $ORIGINAL_PATH"

# Blame at the commit just before the rename
RENAME_COMMIT=$(
  git log --follow --diff-filter=R --format="%H" \
    -- src/routes/api-handler.ts \
  | head -1
)

git blame "${RENAME_COMMIT}^" -- "$ORIGINAL_PATH"
```

---

## Wrangler Config Rename Archaeology

When `wrangler.toml` is split into per-environment files (`wrangler.production.toml`, `wrangler.staging.toml`), trace how a specific environment binding evolved:

```bash
# Find all commits that touched any wrangler config, including renames
git log --follow --stat --diff-filter=ACRMD -- "wrangler*.toml"

# See when ENVIRONMENT_NAME binding was first added
git log --follow -S 'ENVIRONMENT_NAME' -p -- "wrangler*.toml" \
  | head -60
```

`-S` (the "pickaxe") searches for commits that added or removed a specific string — even across renames when combined with `--follow`.

---

## Anti-patterns

- **Using `git log <path>` without `--follow`** — misses all history before a rename. Always use `--follow` for source-file investigation.
- **Relying on GitHub's file history UI** — GitHub's web UI does not always follow renames automatically. Use the CLI for authoritative history.
- **Setting `--follow` with multiple paths** — `git log --follow` only works with a single file path. For multi-path history, run separate commands or use `git log --diff-filter=R --name-status` without `--follow` to map renames manually.
- **Not checking for renames before `git blame`** — blaming a file that was renamed gives misleading authorship for lines that existed before the rename.

---

## Gotchas

- `--follow` only detects renames within a single linear history. Renames that occurred on a different branch before merging may not be detected — inspect the merge commit explicitly with `git show <merge-commit> --stat`.
- Similarity detection compares entire file contents. Files with auto-generated sections (e.g., Wrangler-generated binding stubs) may exceed or fail the threshold unexpectedly. Adjust with `-M<percentage>`.
- `git log --follow` and `git log --all` cannot be combined. `--follow` only works against the current branch's history. To search across branches, iterate branch by branch.
- In a PNPM workspace monorepo, packages are sometimes moved by Turborepo scaffolding. The move commit often has no meaningful message — use `git log --follow --name-status` to find the commit hash, then `git show <hash>` to see the full context.

---

## Verification

```bash
# Verify --follow is working (commit count should be higher than without it)
git log --oneline -- src/routes/api-handler.ts | wc -l
git log --follow --oneline -- src/routes/api-handler.ts | wc -l
# Second count should be >= first

# Confirm renames are detected
git log --follow --diff-filter=R --name-status -- src/routes/api-handler.ts

# Test pickaxe across renames
git log --follow -S 'DB_BINDING' -p -- "wrangler*.toml" | head -30
```

---

## Related

- `git-blame-code-archaeology.md`
- `git-shortlog-contributor-attribution-workers-monorepo.md`
- `git-filter-repo-sensitive-data-removal.md`
- `wrangler-environments-staging-production.md`
- `workers-d1-migration-ci-pipeline.md`

---

## Sources

- git-log documentation: https://git-scm.com/docs/git-log
- git rename detection: https://git-scm.com/docs/gitdiffcore#_diffcore_rename_detection
- Cloudflare Wrangler config: https://developers.cloudflare.com/workers/wrangler/configuration/
- Cloudflare D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
