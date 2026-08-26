# git fsck: object integrity and repo health checks for Cloudflare Workers projects

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

`git pull` returns "object file is empty" or "packfile is corrupt". A CI job fails with "fatal: loose object is damaged". After a forced worktree removal or a container crash mid-pack, the repository's object store has missing or truncated objects. For Cloudflare Workers monorepos where CI runners may be ephemeral or shared, catching corruption early—before it blocks a wrangler deploy—is essential. `git fsck` traverses the entire object graph, reports connectivity problems, and surfaces dangling objects that can be recovered.

## Context

Git stores every file version, tree, commit, and tag as a content-addressed object in `.git/objects/`. Corruption can arise from filesystem errors, incomplete pack operations, disk full conditions, or forceful process termination during `git gc`. `git fsck` verifies SHA-1/SHA-256 integrity of every object and checks that every referenced object exists. In a Cloudflare Workers monorepo, routine fsck runs in CI catch repository health regressions before they reach a developer's local clone.

## Running fsck and interpreting output

```bash
# Basic integrity check (fast, verifies all objects)
git fsck

# Full check including unreachable objects
git fsck --unreachable

# Suppress progress noise, useful in CI
git fsck --no-progress --quiet

# Show dangling commits and blobs (potential recovery targets)
git fsck --lost-found

# Check only connectivity, skip object content hashing
git fsck --connectivity-only

# Strict mode: also reports mismatched timestamps, zero-mode entries
git fsck --strict

# Common output meanings:
# "dangling commit <hash>"     → commit exists but nothing points to it
# "dangling blob <hash>"       → file content exists, no tree references it
# "missing blob <hash>"        → referenced file is gone
# "broken link <hash>"         → parent commit or tree is missing
# "error: object file ... is empty" → disk write was interrupted
```

## TypeScript fsck health check runner for CI

```typescript
// scripts/repo-health-check.ts
// Runs git fsck and emits structured results for CI annotation.

import { execSync, spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

type Severity = "error" | "warning" | "info";

interface FsckFinding {
  severity: Severity;
  kind: string;
  objectHash: string;
  message: string;
}

interface HealthReport {
  clean: boolean;
  findings: FsckFinding[];
  objectCount: number;
  packCount: number;
}

const ERROR_PATTERNS: [RegExp, Severity, string][] = [
  [/^error:/, "error", "object-error"],
  [/^missing (\w+) (.+)$/, "error", "missing-object"],
  [/^broken link from/, "error", "broken-link"],
  [/^dangling commit (.+)$/, "warning", "dangling-commit"],
  [/^dangling blob (.+)$/, "info", "dangling-blob"],
  [/^dangling tag (.+)$/, "info", "dangling-tag"],
];

function runFsck(cwd: string): string {
  const result = spawnSync(
    "git",
    ["fsck", "--no-progress", "--strict", "--unreachable"],
    { cwd, encoding: "utf8" }
  );
  // git fsck writes findings to stderr
  return (result.stdout ?? "") + (result.stderr ?? "");
}

function parseFsckOutput(raw: string): FsckFinding[] {
  const findings: FsckFinding[] = [];
  for (const line of raw.trim().split("\n")) {
    if (!line.trim()) continue;
    for (const [pattern, severity, kind] of ERROR_PATTERNS) {
      const match = line.match(pattern);
      if (match) {
        const hashMatch = line.match(/\b([0-9a-f]{40})\b/);
        findings.push({
          severity,
          kind,
          objectHash: hashMatch?.[1] ?? "unknown",
          message: line.trim(),
        });
        break;
      }
    }
  }
  return findings;
}

function countObjects(cwd: string): { objects: number; packs: number } {
  const objectsDir = join(cwd, ".git/objects");
  const packsDir = join(objectsDir, "pack");

  let objects = 0;
  // Count loose objects (2-char prefix dirs)
  for (const dir of readdirSync(objectsDir)) {
    if (dir.length === 2 && /^[0-9a-f]{2}$/.test(dir)) {
      objects += readdirSync(join(objectsDir, dir)).length;
    }
  }

  const packs = existsSync(packsDir)
    ? readdirSync(packsDir).filter((f) => f.endsWith(".pack")).length
    : 0;

  // Add packed objects (approximate via count-objects)
  try {
    const countOut = execSync("git count-objects -v", {
      cwd,
      encoding: "utf8",
    });
    const inPackMatch = countOut.match(/in-pack: (\d+)/);
    if (inPackMatch) objects += Number(inPackMatch[1]);
  } catch {
    // Non-fatal; proceed without pack count
  }

  return { objects, packs };
}

export function runHealthCheck(cwd = process.cwd()): HealthReport {
  const raw = runFsck(cwd);
  const findings = parseFsckOutput(raw);
  const { objects, packs } = countObjects(cwd);

  const clean = !findings.some((f) => f.severity === "error");
  return { clean, findings, objectCount: objects, packCount: packs };
}

// CLI entry point
const report = runHealthCheck();
console.log(
  JSON.stringify(
    { ...report, timestamp: new Date().toISOString() },
    null,
    2
  )
);
if (!report.clean) {
  console.error(
    `Repository health check FAILED: ${
      report.findings.filter((f) => f.severity === "error").length
    } error(s)`
  );
  process.exit(1);
}
```

## Recovering dangling objects after an interrupted operation

```typescript
// scripts/recover-lost-found.ts
// After git fsck --lost-found, inspects .git/lost-found/ for recoverable content.

import { execSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

interface RecoverableObject {
  hash: string;
  type: "commit" | "blob" | "tree";
  size: number;
  preview: string;
}

function inspectLostFound(repoRoot: string): RecoverableObject[] {
  // git fsck --lost-found writes dangling objects to .git/lost-found/
  execSync("git fsck --lost-found --no-progress", {
    cwd: repoRoot,
    stdio: "pipe",
  });

  const lostFoundDir = join(repoRoot, ".git/lost-found");
  const recoverable: RecoverableObject[] = [];

  for (const subdir of ["commit", "other"]) {
    const dir = join(lostFoundDir, subdir);
    let files: string[];
    try {
      files = readdirSync(dir);
    } catch {
      continue;
    }

    for (const file of files) {
      const hash = file;
      const type = subdir === "commit" ? "commit" : "blob";
      const size = statSync(join(dir, file)).size;

      let preview = "";
      try {
        preview = execSync(`git cat-file -p ${hash}`, {
          cwd: repoRoot,
          encoding: "utf8",
        }).slice(0, 120);
      } catch {
        preview = "(unreadable)";
      }

      recoverable.push({ hash, type, size, preview });
    }
  }

  return recoverable.sort((a, b) => b.size - a.size);
}

const objects = inspectLostFound(process.cwd());
if (objects.length === 0) {
  console.log("No dangling objects found.");
} else {
  console.log(`Found ${objects.length} dangling object(s):\n`);
  for (const obj of objects) {
    console.log(`[${obj.type}] ${obj.hash} (${obj.size} bytes)`);
    console.log(`  Preview: ${obj.preview.slice(0, 80).replace(/\n/g, "↵")}`);
    if (obj.type === "commit") {
      console.log(
        `  Restore: git branch recovered/${obj.hash.slice(0, 8)} ${obj.hash}`
      );
    } else {
      console.log(
        `  Restore: git cat-file -p ${obj.hash} > recovered-blob.txt`
      );
    }
    console.log();
  }
}
```

## Integrating fsck into the CI pre-flight

```yaml
# .github/workflows/repo-health.yml
name: Repository Health

on:
  schedule:
    - cron: "0 4 * * 1"   # Weekly on Monday at 04:00 UTC
  workflow_dispatch:

jobs:
  fsck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4

      - run: pnpm install --frozen-lockfile

      - name: Run repository health check
        id: health
        run: |
          pnpm tsx scripts/repo-health-check.ts | tee health-report.json
          echo "clean=$(jq .clean health-report.json)" >> $GITHUB_OUTPUT

      - name: Upload health report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: repo-health-report
          path: health-report.json
          retention-days: 90

      - name: Fail on errors
        if: steps.health.outputs.clean == 'false'
        run: |
          echo "::error::Repository object integrity errors detected."
          exit 1
```

## Anti-patterns

- **Running `git fsck` only after problems are reported** — by then, CI may be blocked and developers affected. Schedule it weekly as a background job.
- **Ignoring dangling blobs and dangling commits** — they often contain uncommitted work from interrupted operations; inspect them before pruning.
- **Running `git gc --prune=now` to "fix" fsck warnings** — pruning unreachable objects removes the recovery targets. Inspect first, prune only after confirming nothing valuable was dangling.
- **Skipping fsck after `git filter-repo` runs** — history rewrites invalidate cached pack integrity metadata; always fsck after rewriting history.

## Gotchas

- `git fsck` exits with code 0 even when it finds dangling objects (only truly fatal errors produce non-zero). Parse stderr to detect warnings.
- `git fsck --lost-found` writes its output to `.git/lost-found/`, which is **not** cleaned up between runs. Old runs accumulate; add a cleanup step.
- In large monorepos with thousands of objects, `git fsck` can take several minutes. Use `--connectivity-only` for quick checks and full fsck only in the scheduled job.
- SHA-256 repositories (created with `git init --object-format=sha256`) require git ≥ 2.29 on the fsck runner; older versions will refuse to open them.
- Corrupt pack index files (`.idx`) cause fsck to error before it can check objects. Delete the `.idx` and run `git index-pack` to regenerate it, then re-run fsck.

## Verification

```bash
# Baseline check
git fsck --no-progress 2>&1 | grep -E "^(error|missing|broken)"

# Full check with lost-found
git fsck --lost-found --no-progress
ls .git/lost-found/other/ 2>/dev/null | wc -l  # count dangling blobs

# Count objects and packs
git count-objects -v

# Verify pack integrity
git verify-pack -v .git/objects/pack/*.idx | tail -5

# Run the TypeScript health check
pnpm tsx scripts/repo-health-check.ts
```

## Related

- `git-fsck-skiplist-governance.md` — whitelisting known-bad objects
- `git-reflog-workers-accidental-commit-recovery.md` — reflog-based commit recovery
- `git-multi-pack-index-verification-and-compaction.md` — pack integrity
- `git-background-maintenance-for-large-worktrees.md` — scheduled maintenance
- `git-maintenance-scheduled-background-pack-optimization.md` — gc scheduling

## Sources

- Git documentation: `git help fsck`, `git help gc`, `git help verify-pack`
- Git source: `fsck.c` — object verification logic
- GitHub Engineering blog: "How we store millions of lines of code" (github.blog)
- Cloudflare Workers: CI runner environment documentation (developers.cloudflare.com)
