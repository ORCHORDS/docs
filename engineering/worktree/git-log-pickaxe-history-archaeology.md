# Git Log Pickaxe: Tracing When and Why Code Changed

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Worker is behaving unexpectedly in production and you need to find the exact commit that introduced, removed, or mutated a specific string, function call, or configuration value — without reading every commit in the log.

## Context
`git log -S` (the "pickaxe") searches for commits where the count of a string *changed* (added or removed), while `git log -G` searches commits whose diff text *matches a regex*. Together they enable surgical history queries across Workers source, `wrangler.jsonc`, D1 migration files, and CI YAML. These flags work across all branches and tags when combined with `--all`, making them the fastest path to answering "who changed this and when?"

## -S pickaxe: finding when a string was added or removed
`-S<string>` reports commits where the number of occurrences of `<string>` in the diff changed. It does not match commits where the string appears in both old and new (i.e., a simple move within a file triggers it, but a rename of a surrounding variable that doesn't affect the count does not).

```bash
# Find when the D1 binding name was changed in any file
git log -S 'DB_BINDING' --all --oneline --source
# 3f2a1bc refs/heads/main  chore: rename D1 binding to ORCHORDS_DB
# a9e4d11 refs/heads/feat/multi-tenant  feat: add per-tenant D1 bindings

# Search only in wrangler config files
git log -S 'ORCHORDS_DB' --all -- '**/wrangler.jsonc' '**/*.toml' --oneline

# Include the actual diff to see context
git log -S 'ORCHORDS_DB' --all --patch -- '**/wrangler.jsonc'
```

## -G pickaxe: regex matching on diff lines
`-G<regex>` matches any commit whose diff (added or removed lines) contains a line matching the pattern. It is broader than `-S` — it fires on commits where the string exists on both sides if the surrounding context lines change.

```bash
# Find every commit that touched a KV namespace ID (UUID-like)
git log -G '[0-9a-f]{32}' --all --oneline -- '**/wrangler.jsonc'

# Find commits that added or removed a specific fetch() call to an external API
git log -G 'fetch\(['"'"'"]https://api\.stripe\.com' --all --oneline -p \
  -- 'workers/src/**/*.ts'

# Find when an env var was first referenced in Worker code
git log -G 'env\.STRIPE_SECRET' --all --oneline --reverse
```

## Combining with --all --follow and date filters
```bash
# Full archaeology: who first introduced rate limiting logic, any branch, any time
git log -S 'rateLimit' \
  --all \
  --reverse \
  --format="%h %ai %an %s" \
  -- 'workers/src/**'

# Narrow to a specific author during an incident window
git log -G 'KV\.put\(' \
  --author="renovate\[bot\]" \
  --after="2026-06-01" \
  --before="2026-06-30" \
  --oneline

# Find the commit that removed a CODEOWNERS entry
git log -S '@example-org/example-repo' \
  --diff-filter=M \
  -- '.github/CODEOWNERS' \
  --format="%h %as %an — %s"
```

## TypeScript script: automated pickaxe queries in CI
```typescript
// scripts/archaeology.ts
// Run as: npx tsx scripts/archaeology.ts "STRIPE_SECRET" workers/src
import { execSync } from "node:child_process";

interface PickaxeResult {
  sha: string;
  date: string;
  author: string;
  subject: string;
  added: number;
  removed: number;
}

function pickaxe(term: string, path: string): PickaxeResult[] {
  const raw = execSync(
    `git log -S ${JSON.stringify(term)} ` +
    `--all --reverse --format="%H%x00%ai%x00%an%x00%s" -- ${JSON.stringify(path)}`,
    { encoding: "utf8" }
  );
  return raw
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const [sha, date, author, subject] = line.split("\x00");
      // Count occurrences added/removed in this commit
      const diff = execSync(
        `git show ${sha} -- ${JSON.stringify(path)}`,
        { encoding: "utf8" }
      );
      const added = (diff.match(/^\+[^+].*\Q${term}\E/gm) ?? []).length;
      const removed = (diff.match(/^-[^-].*\Q${term}\E/gm) ?? []).length;
      return { sha, date, author, subject, added, removed };
    });
}

const [, , term, path] = process.argv;
if (!term || !path) {
  console.error("Usage: archaeology.ts <search-term> <path>");
  process.exit(1);
}

const results = pickaxe(term, path);
console.table(results);
```

## Practical incident response workflow
```bash
#!/usr/bin/env bash
# scripts/incident-archaeology.sh
# Usage: ./incident-archaeology.sh "env.AI_GATEWAY_URL" 2026-07-15 2026-07-22
set -euo pipefail

TERM="$1"
SINCE="$2"
UNTIL="${3:-$(date +%Y-%m-%d)}"

echo "=== Pickaxe: commits changing count of '$TERM' ==="
git log -S "$TERM" \
  --all \
  --after="$SINCE" \
  --before="$UNTIL" \
  --format="%C(yellow)%h%Creset %C(cyan)%as%Creset %an — %s" \
  -- 'workers/**' 'src/**'

echo ""
echo "=== Regex match: diff lines referencing '$TERM' ==="
git log -G "$TERM" \
  --all \
  --after="$SINCE" \
  --before="$UNTIL" \
  --format="%C(yellow)%h%Creset %C(cyan)%as%Creset %an — %s" \
  -- 'workers/**' 'src/**'
```

## -L: line-range history (complementary tool)
When you know the file and approximate line location, `-L` traces a specific line range through history and is more surgical than pickaxe:

```bash
# Trace history of lines 10-25 in the rate limiter module
git log -L 10,25:workers/src/rate-limiter.ts --oneline

# Trace history of a function by name (requires heuristic detection)
git log -L :handleRequest:workers/src/index.ts --oneline
```

## Anti-patterns
- Using `git grep` when you need history — `git grep` searches the working tree or a specific commit, not the diff stream across commits.
- Confusing `-S` and `-G`: `-S 'foo'` finds commits where the *count* of `foo` changed; `-G 'foo'` finds commits whose *diff lines* match. A refactor that moves `foo` to a different line in the same file may not trigger `-S` but will trigger `-G`.
- Running pickaxe without `--all` on a monorepo where the feature branch you're investigating has never been merged to main.
- Omitting `--` path separators when the search term or regex could be misinterpreted as a revision.
- Piping `git log -p` output to grep for manual inspection — use `-G` instead, which is dramatically faster.

## Gotchas
- `-S` is case-sensitive by default. Use `--regexp-ignore-case` (only applies to `-G`; there is no case-insensitive mode for `-S` without wrapping in `-G`).
- `-G` uses POSIX extended regex by default; switch to Perl regex with `-P` on systems with PCRE support: `git log -P -G '(?i)stripe'`.
- The pickaxe operates on the diff, not the file content — a commit that merely reformats a file (e.g., `prettier`) will trigger `-G` for every touched line without changing the logical content.
- `--follow` (for rename tracking) cannot be combined with `-S` or `-G` when a path argument is also given; use separate invocations.
- On very large repos, `-G` with a broad regex can be slow; narrow with a path spec first.

## Verification
```bash
# Confirm pickaxe found the right commit
git show <found-sha> | grep -C3 'ORCHORDS_DB'

# Cross-check: the string count should have changed
git show <found-sha>:wrangler.jsonc | grep -c 'ORCHORDS_DB' || true
git show <found-sha>~1:wrangler.jsonc | grep -c 'ORCHORDS_DB' || true
# The two counts should differ
```

## Related
- [git-blame-code-archaeology.md](git-blame-code-archaeology.md)
- [git-blame-ignore-revs-formatting-commits.md](git-blame-ignore-revs-formatting-commits.md)
- [git-log-follow-file-history-workers.md](git-log-follow-file-history-workers.md)
- [git-bisect-automated-regression-finding.md](git-bisect-automated-regression-finding.md)

## Sources
- https://git-scm.com/docs/git-log#Documentation/git-log.txt--Sltstringgt
- https://www.git-scm.com/book/en/v2/Git-Tools-Searching
- https://lornajane.net/posts/2014/git-log-s-versus-git-log-g
