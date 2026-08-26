# git diff-filter Selective Review for Workers Change Sets

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A PR touches 80 files: renamed config files, deleted dead code, added new Worker routes, and genuine logic modifications. Reviewers wade through every file equally. CI jobs lint files that no longer exist.

`git diff --diff-filter` lets you slice a changeset by the status of each file: Added, Copied, Deleted, Modified, Renamed, Type-changed. You can uppercase (include) or lowercase (exclude) each status letter.

## Context

`--diff-filter` applies to any git command that emits per-file diff information: `git diff`, `git diff-tree`, `git log`, `git show`.

| Letter | Status |
|---|---|
| `A` | Added |
| `C` | Copied |
| `D` | Deleted |
| `M` | Modified |
| `R` | Renamed |
| `T` | Type change |

Uppercase = select; lowercase = exclude.

## Listing only added and modified Worker source files

```typescript
// scripts/changed-worker-sources.ts
import { execSync } from "node:child_process";

type DiffStatus = "A" | "C" | "D" | "M" | "R" | "T";

interface ChangedFile {
  status: DiffStatus;
  path: string;
  oldPath?: string;
}

function diffFilter(base: string, head: string, filter: string): ChangedFile[] {
  const raw = execSync(
    `git diff --diff-filter=${filter} --name-status -z ${base}...${head}`,
    { encoding: "utf8" },
  );

  const files: ChangedFile[] = [];
  const parts = raw.split("\0").filter(Boolean);
  let i = 0;
  while (i < parts.length) {
    const statusField = parts[i]!;
    const status = statusField[0] as DiffStatus;
    if (status === "R" || status === "C") {
      files.push({ status, oldPath: parts[i + 1], path: parts[i + 2]! });
      i += 3;
    } else {
      files.push({ status, path: parts[i + 1]! });
      i += 2;
    }
  }
  return files;
}

const base = process.env.GITHUB_BASE_REF ?? "main";
const head = process.env.GITHUB_SHA ?? "HEAD";

const lintable = diffFilter(`origin/${base}`, head, "AM").filter((f) => f.path.endsWith(".ts"));
console.log("Files to lint:");
lintable.forEach((f) => console.log(` ${f.status}  ${f.path}`));
```

## Driving selective Wrangler deployment from diff-filter output

```typescript
// scripts/selective-deploy.ts
const WORKERS = [
  { name: "api", dir: "workers/api", wranglerConfig: "workers/api/wrangler.toml" },
  { name: "auth", dir: "workers/auth", wranglerConfig: "workers/auth/wrangler.toml" },
];

function touchedWorkers(base: string) {
  const raw = execSync(
    `git diff --diff-filter=MAR --name-only origin/${base}...HEAD`,
    { encoding: "utf8" },
  );
  const changed = new Set(raw.split("\n").filter(Boolean));
  return WORKERS.filter((w) => [...changed].some((f) => f.startsWith(w.dir + "/")));
}

const base = process.env.GITHUB_BASE_REF ?? "main";
const env = process.env.DEPLOY_ENV ?? "staging";

for (const w of touchedWorkers(base)) {
  console.log(`Deploying ${w.name} to ${env}...`);
  execSync(`npx wrangler deploy --config ${w.wranglerConfig} --env ${env}`, { stdio: "inherit" });
}
```

## Excluding deleted files from ESLint in GitHub Actions

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Compute files to lint (no deletes)
        id: files
        run: |
          FILES=$(git diff --diff-filter=d --name-only \
            origin/${{ github.base_ref }}...HEAD \
            | grep -E '\.(ts|tsx)$' \
            | tr '\n' ' ')
          echo "files=$FILES" >> "$GITHUB_OUTPUT"

      - name: Run ESLint on changed files only
        if: steps.files.outputs.files != ''
        run: npx eslint ${{ steps.files.outputs.files }}
```

## Anti-patterns

- **Using `--diff-filter=AM` without `-z`** — paths with spaces split incorrectly.
- **Deploying on `--diff-filter=M` only** — misses renamed-and-modified files; use `MAR`.
- **Comparing working tree to HEAD in CI** — always compare a commit range.

## Gotchas

- `--diff-filter` is case-sensitive: `--diff-filter=am` excludes Added and Modified.
- The `C` (Copied) status is only reported when `--find-copies` or `-C` is also passed.

## Verification

```bash
git diff --diff-filter=AM --name-only origin/main...HEAD | grep '\.ts$'
git diff --diff-filter=D --name-only origin/main...HEAD
git diff --diff-filter=R --name-status -M origin/main...HEAD
```

## Related

- `git-diff-stat-deploy-artifact-size-tracking.md`
- `monorepo-wrangler-selective-deploy.md`
- `github-actions-wrangler-deploy-pipeline.md`

## Sources

- https://git-scm.com/docs/git-diff#Documentation/git-diff.txt---diff-filterACDMRTUXB82308203
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
