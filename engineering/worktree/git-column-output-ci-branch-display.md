# git column Output for Wide CI Branch and Tag Display

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

CI scripts listing branches, tags, or changed packages in a monorepo emit a vertical wall of text—one item per line—making logs hard to scan. Alternatively, a developer running `git branch` locally gets unaligned output that wraps badly in narrow terminals. `git column` reformats arbitrary line-delimited input into multi-column aligned output, similar to the Unix `column` utility but git-native and aware of git colour settings.

The use-case spans CI log readability, release summary steps, and local tooling that surfaces branch lists or changed-package inventories to a human reader.

## Context

`git column` is a low-level plumbing command added in git 1.7.9. It reads lines from stdin and lays them out in columns, optionally with colour and indent. It is also the engine behind `git branch --column` and `git tag --column`.

Configuration is controlled by `column.ui` (for interactive commands) and `column.branch` / `column.tag` (for those specific commands). Values are space-separated flags:

| Flag | Effect |
|---|---|
| `always` | force columns even when not a tty |
| `never` | disable columns |
| `auto` | columns only when stdout is a tty |
| `column` | fill columns left-to-right then wrap |
| `row` | fill rows top-to-bottom (default) |
| `plain` | one item per line |
| `dense` | reduce padding to minimum |
| `nodense` | keep uniform cell width |

## Enabling column output for branch listings in CI

```yaml
# .github/workflows/release-summary.yml
jobs:
  summary:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Show release branches in columns
        run: |
          echo "## Release branches"
          git branch -r --list 'origin/release/*' \
            | sed 's|  origin/||' \
            | git column --mode=always --width=120 --indent="  "
```

## Reformatting changed packages for PR summaries

```typescript
// scripts/pr-summary.ts
import { execSync } from "node:child_process";

function changedPackages(base: string): string[] {
  const diff = execSync(
    `git diff --name-only origin/${base}...HEAD`,
    { encoding: "utf8" },
  );
  const pkgs = new Set<string>();
  for (const line of diff.split("\n").filter(Boolean)) {
    const match = line.match(/^(packages\/[^/]+)\//);
    if (match) pkgs.add(match[1]!);
  }
  return [...pkgs].sort();
}

function columnize(
  items: string[],
  width = 100,
  indent = "  ",
): string {
  // Use git column for consistent output
  const input = items.join("\n");
  return execSync(
    `git column --mode=always --width=${width} --indent="${indent}"`,
    { input, encoding: "utf8" },
  );
}

const base = process.env.GITHUB_BASE_REF ?? "main";
const pkgs = changedPackages(base);

if (pkgs.length === 0) {
  console.log("No package changes detected.");
} else {
  console.log(`Changed packages (${pkgs.length}):\n`);
  console.log(columnize(pkgs));
}
```

## Configuring column output per-repository

```bash
# .git/config or global ~/.gitconfig
[column]
  ui = auto dense
  branch = always column dense
  tag = always column dense
```

```typescript
// scripts/configure-repo-columns.ts
import { execSync } from "node:child_process";

function setConfig(key: string, value: string): void {
  execSync(`git config ${key} "${value}"`);
  console.log(`Set ${key} = ${value}`);
}

// Apply column settings to the local repo
setConfig("column.ui", "auto dense");
setConfig("column.branch", "always column dense");
setConfig("column.tag", "always column dense");

// Verify
const branches = execSync("git branch --column --sort=-committerdate", {
  encoding: "utf8",
});
console.log("Branch listing:\n", branches);
```

## Using git column in Workers-deployed release notes generator

```typescript
// workers/release-notes/src/index.ts
import { Hono } from "hono";

const app = new Hono<{ Bindings: { RELEASES_KV: KVNamespace } }>();

interface ReleaseEntry {
  version: string;
  branch: string;
  deployedAt: string;
  environment: string;
}

function columnizeEntries(entries: ReleaseEntry[]): string {
  // Format as fixed-width columns without git (Workers has no git binary)
  const headers = ["Version", "Branch", "Environment", "Deployed"];
  const rows = entries.map((e) => [
    e.version,
    e.branch,
    e.environment,
    new Date(e.deployedAt).toISOString().slice(0, 16).replace("T", " "),
  ]);

  const widths = headers.map((h, i) =>
    Math.max(h.length, ...rows.map((r) => r[i]!.length)),
  );

  const header = headers.map((h, i) => h.padEnd(widths[i]!)).join("  ");
  const separator = widths.map((w) => "-".repeat(w)).join("  ");
  const body = rows
    .map((r) => r.map((cell, i) => cell.padEnd(widths[i]!)).join("  "))
    .join("\n");

  return [header, separator, body].join("\n");
}

app.get("/releases", async (c) => {
  const list = await c.env.RELEASES_KV.list({ prefix: "release:" });
  const entries: ReleaseEntry[] = [];

  for (const key of list.keys.slice(0, 50)) {
    const val = await c.env.RELEASES_KV.get(key.name);
    if (val) entries.push(JSON.parse(val) as ReleaseEntry);
  }

  entries.sort(
    (a, b) =>
      new Date(b.deployedAt).getTime() - new Date(a.deployedAt).getTime(),
  );

  const accept = c.req.header("Accept") ?? "";
  if (accept.includes("text/plain")) {
    return c.text(columnizeEntries(entries));
  }
  return c.json(entries);
});

app.post("/releases", async (c) => {
  const entry = (await c.req.json()) as ReleaseEntry;
  const key = `release:${entry.version}`;
  await c.env.RELEASES_KV.put(key, JSON.stringify(entry), {
    expirationTtl: 60 * 60 * 24 * 90,
  });
  return c.json({ ok: true, key });
});

export default app;
```

## Controlling column width dynamically in CI scripts

```bash
#!/usr/bin/env bash
# scripts/list-worktrees-columns.sh
# List all worktrees in multi-column format adjusted to terminal width

set -euo pipefail

# In CI, COLUMNS is not set; fall back to 120
WIDTH="${COLUMNS:-120}"

git worktree list --porcelain \
  | awk '/^worktree / { print $2 }' \
  | xargs -I{} basename {} \
  | git column --mode=always --width="$WIDTH" --indent="  "
```

## Anti-patterns

- **Using `git column --mode=always` in scripts that pipe output to other commands**: column adds padding spaces that break downstream `awk` / `grep` field parsing. Use `plain` mode or remove column formatting before piping.
- **Hardcoding `--width=80`**: terminal and CI log widths vary. Use `$COLUMNS` in interactive scripts and `120` as a CI default.
- **Relying on column output being stable across git versions**: column wrapping is layout-dependent; do not parse column output programmatically—parse the original list and columnize only for display.
- **Applying column formatting to data written to files**: only format for human-readable log output or terminals.

## Gotchas

- `git column` is a porcelain-adjacent command; its output is not part of git's stable plumbing contract and may change between git releases.
- The `--nl` flag controls the record separator (default `\n`); if your items contain spaces, ensure they are newline-separated before piping.
- Colour codes count toward string length in some terminal emulators, causing misaligned columns; use `--no-color` when feeding coloured input.
- `column.branch = always` affects `git branch` output everywhere, including scripts that parse branch names—override per-invocation with `--no-column` when needed.

## Verification

```bash
# Test column formatting locally
printf 'alpha\nbeta\ngamma\ndelta\nepsilon\nzeta\n' \
  | git column --mode=always --width=40

# Verify branch column config
git config column.branch
# Expected: always column dense

# Check git column is available
git column --help 2>&1 | head -3
```

## Related

- `git-foreachref-startafter-pagination.md`
- `git-log-graph-visualization-ci-artifacts.md`
- `git-worktree-porcelain-nul-safe-inventory-automation.md`
- `git-shortlog-contributor-attribution-workers-monorepo.md`

## Sources

- https://git-scm.com/docs/git-column
- https://git-scm.com/docs/git-config#Documentation/git-config.txt-columnui
- https://git-scm.com/docs/git-branch (--column flag)
