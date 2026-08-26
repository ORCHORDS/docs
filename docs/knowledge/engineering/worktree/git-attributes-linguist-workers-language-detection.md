# .gitattributes Linguist Tuning for Cloudflare Workers Monorepos

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

GitHub reports your Cloudflare Workers monorepo as "94% JavaScript" because generated
Wrangler output, vendored `node_modules`-adjacent files, and SQL migration scripts all count
toward the language bar. Your actual authored TypeScript sits at 12% in the stats.
Downstream effects: GitHub's linguist-derived language label controls which Marketplace
actions appear, and security scanners that key off `linguist-language` annotations may skip
your Workers source entirely. A carefully tuned `.gitattributes` file fixes this without
touching the file tree.

## Context

GitHub Linguist classifies files using heuristics and a vendored language list. It respects
three override attributes you can set in `.gitattributes`:

- `linguist-vendored`: marks files as third-party — excluded from stats and code search by
  default.
- `linguist-generated`: marks files as machine-generated — excluded from diffs and stats.
- `linguist-language`: overrides the detected language for a path.
- `linguist-detectable`: set to `false` to exclude entirely, `true` to include files
  normally excluded by their extension or pattern.

Wrangler projects also generate `worker-configuration.d.ts`, `.wrangler/` output, and
Worker bundle output. D1 migrations are SQL. `wrangler.toml` is TOML. Without annotations,
all of these skew the language bar and may confuse code-search tools.

## Base .gitattributes for a Workers Monorepo

```gitattributes
# ─── Wrangler generated output ──────────────────────────────────────────────
.wrangler/**                     linguist-generated=true
**/worker-configuration.d.ts     linguist-generated=true
**/__generated__/**              linguist-generated=true
**/dist/**                       linguist-generated=true
**/build/**                      linguist-generated=true

# ─── D1 SQL migrations — mark as SQL, ensure detectable ─────────────────────
**/migrations/*.sql              linguist-language=SQL
**/migrations/*.sql              linguist-detectable=true

# ─── Wrangler config files — mark as TOML ───────────────────────────────────
wrangler.toml                    linguist-language=TOML
wrangler.*.toml                  linguist-language=TOML
**/wrangler.toml                 linguist-language=TOML

# ─── Vendored / third-party ──────────────────────────────────────────────────
**/vendor/**                     linguist-vendored=true
**/.pnpm/**                      linguist-vendored=true
**/node_modules/**               linguist-vendored=true

# ─── Test fixtures and snapshots ─────────────────────────────────────────────
**/__snapshots__/**              linguist-generated=true
**/fixtures/**                   linguist-vendored=true
**/*.snap                        linguist-generated=true

# ─── Config and tooling (keep detectable for polyglot health checks) ─────────
**/*.json                        linguist-language=JSON
**/tsconfig*.json                linguist-language=JSON with Comments

# ─── Git merge driver assignments (separate concern, same file) ──────────────
package-lock.json                merge=npm-merge-driver
pnpm-lock.yaml                   merge=union
```

## TypeScript Script to Validate Linguist Attributes

```typescript
// scripts/validate-gitattributes.ts
// Ensures key Workers paths are classified correctly before push
import { execSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

interface AttributeExpectation {
  pathGlob: string;
  attribute: string;
  expectedValue: string;
}

// Canonical expectations for a Workers monorepo
const EXPECTATIONS: AttributeExpectation[] = [
  { pathGlob: "workers/api/migrations/0001_init.sql", attribute: "linguist-language", expectedValue: "SQL" },
  { pathGlob: "workers/api/worker-configuration.d.ts", attribute: "linguist-generated", expectedValue: "true" },
  { pathGlob: ".wrangler/state/v3/r2/default.sqlite", attribute: "linguist-generated", expectedValue: "true" },
  { pathGlob: "wrangler.toml", attribute: "linguist-language", expectedValue: "TOML" },
];

function checkAttribute(filePath: string, attribute: string): string | null {
  try {
    const raw = execSync(`git check-attr ${attribute} -- ${filePath}`).toString().trim();
    // Output: "path: attribute: value"
    const match = raw.match(/:\s*(.+)$/);
    return match ? match[1].trim() : null;
  } catch {
    return null;
  }
}

function validateExpectations(): { passed: number; failed: number } {
  let passed = 0;
  let failed = 0;

  for (const exp of EXPECTATIONS) {
    const actual = checkAttribute(exp.pathGlob, exp.attribute);
    if (actual === exp.expectedValue) {
      console.log(`  PASS  ${exp.pathGlob}  [${exp.attribute}=${actual}]`);
      passed++;
    } else {
      console.error(`  FAIL  ${exp.pathGlob}  expected ${exp.attribute}=${exp.expectedValue}, got ${actual}`);
      failed++;
    }
  }
  return { passed, failed };
}

const { passed, failed } = validateExpectations();
console.log(`\nResult: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
```

## CI Step: Linguist Dry-run via github-linguist

When the Ruby `github-linguist` gem is available, you can run a local linguist analysis in
CI to catch regressions before they reach GitHub:

```yaml
# .github/workflows/linguist-check.yml
name: Linguist Attributes Check

on:
  pull_request:
    paths:
      - ".gitattributes"
      - "workers/**/*.ts"
      - "workers/**/*.sql"
      - "**/wrangler.toml"

jobs:
  linguist:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install github-linguist
        run: |
          sudo apt-get install -y cmake pkg-config libicu-dev ruby-full
          gem install github-linguist

      - name: Run linguist analysis
        run: |
          linguist --breakdown | tee linguist-report.txt
          # Fail if TypeScript drops below 60% of attributed files
          TS_PCT=$(linguist --json | jq -r '.TypeScript // 0')
          echo "TypeScript percentage: $TS_PCT"

      - name: Validate gitattributes
        run: npx tsx scripts/validate-gitattributes.ts
```

## Programmatic .gitattributes Generation for Large Monorepos

In a monorepo with dozens of Workers, maintaining `.gitattributes` by hand drifts. This
script walks the packages and writes the generated section:

```typescript
// scripts/generate-gitattributes.ts
import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";

const ROOT = execSync("git rev-parse --show-toplevel").toString().trim();
const ATTRS_PATH = path.join(ROOT, ".gitattributes");
const GENERATED_HEADER = "# ─── AUTO-GENERATED: Workers Packages ───────────────────────────────────────";
const GENERATED_FOOTER = "# ─── END AUTO-GENERATED ────────────────────────────────────────────────────";

function findWorkerDirs(): string[] {
  return fs
    .readdirSync(path.join(ROOT, "workers"), { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
}

function buildGeneratedBlock(workerDirs: string[]): string {
  const lines: string[] = [GENERATED_HEADER];
  for (const w of workerDirs) {
    lines.push(`workers/${w}/worker-configuration.d.ts    linguist-generated=true`);
    lines.push(`workers/${w}/migrations/*.sql              linguist-language=SQL`);
    lines.push(`workers/${w}/migrations/*.sql              linguist-detectable=true`);
    lines.push(`workers/${w}/dist/**                       linguist-generated=true`);
    lines.push(`workers/${w}/.wrangler/**                  linguist-generated=true`);
  }
  lines.push(GENERATED_FOOTER);
  return lines.join("\n");
}

function updateGitattributes(): void {
  const current = fs.existsSync(ATTRS_PATH) ? fs.readFileSync(ATTRS_PATH, "utf8") : "";
  const before = current.split(GENERATED_HEADER)[0] ?? "";
  const after = current.split(GENERATED_FOOTER)[1] ?? "";
  const block = buildGeneratedBlock(findWorkerDirs());
  const updated = `${before}${block}${after}`.replace(/\n{3,}/g, "\n\n");
  fs.writeFileSync(ATTRS_PATH, updated);
  console.log(`.gitattributes updated for ${findWorkerDirs().length} workers`);
}

updateGitattributes();
```

## Anti-patterns

- **Setting `linguist-vendored=true` on your own source**: vendored files are excluded from
  code search on GitHub. Accidentally marking `workers/` as vendored means your TypeScript
  is unsearchable.
- **Using `linguist-detectable=false` on SQL migrations**: if you want Dependabot or
  security scanning to cover your D1 schema, you need those files detectable.
- **Forgetting `.wrangler/` in `.gitignore`**: `.wrangler/` is already gitignored by
  Wrangler's default template, but if it ends up tracked, it inflates JavaScript stats
  massively. Check with `git ls-files .wrangler`.

## Gotchas

- `git check-attr` resolves attributes against the working tree `.gitattributes`. The file
  must be committed (or staged) for GitHub Linguist to see it — a local-only file change
  does not affect the language bar until merged.
- GitHub Linguist runs on the default branch, not on PRs. Language stats only update after
  merging.
- `linguist-language` overrides detection but does not affect syntax highlighting on
  GitHub's file view if the extension is unambiguous — that is determined by a different
  lookup.

## Verification

```bash
# Check attributes on a specific path
git check-attr linguist-generated linguist-language -- workers/api/worker-configuration.d.ts

# List all files that are marked generated
git ls-files | xargs git check-attr linguist-generated -- | grep "set$"

# Confirm .wrangler is not tracked
git ls-files .wrangler
```

## Related

- `git-attributes-merge-drivers.md`
- `monorepo-workspace-cloudflare-workers.md`
- `workers-d1-migration-ci-pipeline.md`
- `git-blame-ignore-revs-formatting-commits.md`

## Sources

- https://github.com/github-linguist/linguist/blob/master/docs/overrides.md
- https://git-scm.com/docs/gitattributes
- https://developers.cloudflare.com/workers/wrangler/configuration/
