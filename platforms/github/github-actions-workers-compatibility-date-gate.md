# GitHub Actions CI Gate for Workers Compatibility Date Enforcement

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A PR bumps the `compatibility_date` in `wrangler.toml` to a date that enables a new flag — or worse, to a future date that activates unreleased runtime behaviour. The change passes linting and unit tests but breaks at runtime because a compatibility flag silently changes fetch semantics, URL parsing, or crypto APIs. You need CI to catch stale, over-advanced, or flag-introducing compatibility date changes before merge.

## Context

Cloudflare Workers uses `compatibility_date` (YYYY-MM-DD) and optional `compatibility_flags` in `wrangler.toml` to opt into runtime behaviour changes. Each date bundles a set of flags that flip from opt-in to default. CI can enforce:

1. The date is not in the future (no speculative future flags).
2. The date has not regressed below the project's minimum approved date.
3. Any flags listed in `compatibility_flags` are on the project's approved list.
4. When the date changes, the diff is reviewed via a required status check gating merge.

## Step 1 — Extract and Validate Compatibility Date

```typescript
// scripts/check-compat-date.ts
import { readFileSync } from "node:fs";

// Minimal TOML parser for wrangler.toml compatibility fields
function extractField(toml: string, field: string): string | undefined {
  const match = toml.match(new RegExp(`^${field}\\s*=\\s*"([^"]+)"`, "m"));
  return match?.[1];
}

function extractFlags(toml: string): string[] {
  const match = toml.match(/^compatibility_flags\s*=\s*\[([^\]]*)\]/m);
  if (!match) return [];
  return match[1].match(/"([^"]+)"/g)?.map((s) => s.replace(/"/g, "")) ?? [];
}

const toml = readFileSync("wrangler.toml", "utf8");
const compatDate = extractField(toml, "compatibility_date");
const flags = extractFlags(toml);

const today = new Date().toISOString().slice(0, 10);
const MIN_APPROVED_DATE = process.env.MIN_COMPAT_DATE ?? "2024-01-01";
const APPROVED_FLAGS: string[] = (process.env.APPROVED_FLAGS ?? "").split(",").filter(Boolean);

let exitCode = 0;

if (!compatDate) {
  console.error("ERROR: compatibility_date not found in wrangler.toml");
  process.exit(1);
}

if (compatDate > today) {
  console.error(`ERROR: compatibility_date ${compatDate} is in the future (today: ${today})`);
  exitCode = 1;
}

if (compatDate < MIN_APPROVED_DATE) {
  console.error(
    `ERROR: compatibility_date ${compatDate} is older than the minimum approved date ${MIN_APPROVED_DATE}`
  );
  exitCode = 1;
}

const unapproved = flags.filter((f) => !APPROVED_FLAGS.includes(f));
if (unapproved.length > 0) {
  console.error(`ERROR: Unapproved compatibility_flags: ${unapproved.join(", ")}`);
  exitCode = 1;
}

if (exitCode === 0) {
  console.log(`OK: compatibility_date=${compatDate}, flags=[${flags.join(", ")}]`);
}
process.exit(exitCode);
```

## Step 2 — CI Job that Runs on Every PR

```yaml
# .github/workflows/compat-date-gate.yml
name: Workers compatibility date gate
on:
  pull_request:
    paths:
      - "wrangler.toml"
      - "wrangler.*.toml"
      - "**/wrangler.toml"

jobs:
  check-compat-date:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Install tsx
        run: npm install -g tsx

      - name: Validate compatibility date
        env:
          MIN_COMPAT_DATE: "2024-09-23"
          APPROVED_FLAGS: "nodejs_compat,streams_enable_constructors,global_navigator"
        run: npx tsx scripts/check-compat-date.ts
```

## Step 3 — Detect When Compatibility Date Changed (PR Diff Check)

```yaml
      - name: Detect compatibility_date change in PR
        id: compat_changed
        run: |
          BASE_DATE=$(git show origin/${{ github.base_ref }}:wrangler.toml \
            | grep -oP '(?<=compatibility_date = ")[^"]+' || echo "not-found")
          HEAD_DATE=$(grep -oP '(?<=compatibility_date = ")[^"]+' wrangler.toml || echo "not-found")
          echo "base=${BASE_DATE}" >> "$GITHUB_OUTPUT"
          echo "head=${HEAD_DATE}" >> "$GITHUB_OUTPUT"
          if [ "$BASE_DATE" != "$HEAD_DATE" ]; then
            echo "changed=true" >> "$GITHUB_OUTPUT"
          else
            echo "changed=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Post PR comment on compatibility date bump
        if: steps.compat_changed.outputs.changed == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const base = '${{ steps.compat_changed.outputs.base }}';
            const head = '${{ steps.compat_changed.outputs.head }}';
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.pull_request.number,
              body: `## Workers Compatibility Date Changed\n\n` +
                    `- **Before:** \`${base}\`\n` +
                    `- **After:** \`${head}\`\n\n` +
                    `Review the [changelog](https://developers.cloudflare.com/workers/configuration/compatibility-dates/) ` +
                    `for flags activated between these dates and confirm no breaking changes.`
            });
```

## Step 4 — Enforce Minimum Date Advancement Policy

```typescript
// scripts/check-compat-lag.ts
// Warn if compatibility_date is more than 180 days behind today (stale runtime risk)
import { readFileSync } from "node:fs";

const toml = readFileSync("wrangler.toml", "utf8");
const match = toml.match(/^compatibility_date\s*=\s*"([^"]+)"/m);
if (!match) process.exit(1);

const compatDate = new Date(match[1]);
const today = new Date();
const lagDays = Math.floor((today.getTime() - compatDate.getTime()) / 86_400_000);
const MAX_LAG_DAYS = Number(process.env.MAX_LAG_DAYS ?? "180");

console.log(`Compatibility date lag: ${lagDays} days`);
if (lagDays > MAX_LAG_DAYS) {
  console.warn(`WARN: compatibility_date is ${lagDays} days old (max: ${MAX_LAG_DAYS}). Consider advancing it.`);
  // Non-fatal: emit as workflow annotation, not a failure
  console.log(`::warning file=wrangler.toml::compatibility_date is ${lagDays} days old`);
}
```

## Step 5 — Require Status Check on Branch Protection

```bash
# Via GitHub CLI — add the job name as a required status check
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["check-compat-date"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews=null \
  --field restrictions=null
```

## Anti-patterns

- **Running the gate only on main push**: By then the change is already merged. Gate on `pull_request` with `paths: wrangler.toml` so it only triggers when the file changes, reducing noise.
- **Hardcoding the minimum date in the workflow YAML**: Store it in a repository variable (`vars.MIN_COMPAT_DATE`) so it can be updated without a workflow file PR.
- **Blocking on lag with a hard failure**: Stale dates should be a warning annotation, not a required gate — teams may intentionally stay on a pinned date while evaluating a new flag.
- **Not checking `wrangler.*.toml` environment overrides**: An override file can silently set an earlier date that takes precedence for a specific environment.

## Gotchas

- `wrangler.toml` uses TOML format; regex extraction is fragile with multi-line arrays or inline tables. Use a proper TOML parser (`@iarna/toml` or `smol-toml`) for production scripts.
- The `compatibility_date` in a `[env.production]` stanza overrides the top-level value for production deploys; check all stanzas.
- Future-dated compatibility dates are **accepted by Cloudflare** — they activate no additional flags beyond today's set, but the intent is ambiguous and should be blocked in CI.
- Some `compatibility_flags` can only be set alongside a minimum compatibility date; Wrangler validates this at deploy time, not at upload time.

## Verification

```bash
# Manually test the script against main branch wrangler.toml
MIN_COMPAT_DATE="2024-09-23" \
APPROVED_FLAGS="nodejs_compat,streams_enable_constructors" \
npx tsx scripts/check-compat-date.ts
# Expected: OK: compatibility_date=2025-01-01, flags=[nodejs_compat]
```

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-wrangler-pages-functions-deploy-pipeline.md`
- `github-actions-required-status-checks-branch-gates.md`
- `github-actions-workflow-dispatch-input-validation.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/workers/wrangler/configuration/#compatibility-flags
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/#change-history
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging
