# Workers Compatibility Date Staged Migration Strategy

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

When a Cloudflare Workers project was pinned to an old `compatibility_date` months or years ago, upgrading to a current date often introduces multiple breaking changes simultaneously. Teams that try to bump the date in a single PR encounter hard-to-diagnose failures in production — behaviors changed by flags they did not know existed now surface together, making root-cause analysis slow.

A staged migration strategy lets you advance the compatibility date one flag group at a time, gating each increment behind a CI smoke test and a canary period in production before merging the next increment.

## Context

Cloudflare's compatibility system works through two mechanisms: `compatibility_date` (which implicitly activates all flags whose activation date falls on or before that date) and `compatibility_flags` (an explicit opt-in/opt-out list). The flags page at developers.cloudflare.com lists every flag, its activation date, and whether it is currently default-on or default-on-by-date.

Because `compatibility_date` is a rolling switch, you cannot upgrade from `2023-01-01` to `2026-01-01` safely in one step if multiple flags changed semantics in between. The strategy below uses `compatibility_flags` to opt into individual flags ahead of their activation date while keeping the base date frozen, then advances the base date once stability is confirmed.

## Audit Current Flag Exposure

Before planning increments, generate a diff of every flag that changed status between your current date and the target date.

```typescript
// scripts/compat-flag-diff.ts
// Run: npx tsx scripts/compat-flag-diff.ts
// Requires: @cloudflare/workers-types for type hints only

const FLAGS_URL =
  "https://raw.githubusercontent.com/cloudflare/workerd/main/src/workerd/io/compatibility-date.capnp";

async function main() {
  const resp = await fetch(FLAGS_URL);
  const text = await resp.text();

  // Extract enableDate lines
  const flagPattern =
    /(\w+)\s*@\d+\s*:Bool\s*=\s*false[^;]*enableDate\s*=\s*"(\d{4}-\d{2}-\d{2})"/g;
  const current = new Date("2023-01-01");
  const target = new Date("2026-01-01");

  const matches = [...text.matchAll(flagPattern)];
  const inRange = matches.filter(([, , date]) => {
    const d = new Date(date);
    return d > current && d <= target;
  });

  console.log(`Flags to review (${inRange.length} total):`);
  for (const [, name, date] of inRange) {
    console.log(`  ${date}  ${name}`);
  }
}

main();
```

## Incremental Flag Adoption via wrangler.toml

For each increment, opt into the next batch of flags explicitly while keeping the base date stable. This lets you test exactly one group of behavioral changes.

```toml
# wrangler.toml — increment #1: fetch_refuses_unknown_protocols + formdata_parser_supports_files
name = "my-worker"
main = "src/index.ts"

# Frozen base date — advance only after all flag increments pass
compatibility_date = "2023-01-01"

# Explicitly enable flags we are testing in this increment
compatibility_flags = [
  "fetch_refuses_unknown_protocols",
  "formdata_parser_supports_files",
]

[env.production]
compatibility_date = "2023-01-01"
compatibility_flags = [
  "fetch_refuses_unknown_protocols",
  "formdata_parser_supports_files",
]

[env.staging]
compatibility_date = "2023-01-01"
compatibility_flags = [
  "fetch_refuses_unknown_protocols",
  "formdata_parser_supports_files",
]
```

Once an increment is stable, move its flags into the `compatibility_date` advance rather than keeping them in the explicit list. This keeps the list small and readable.

## CI Gate Per Increment

Each increment PR triggers a dedicated test suite that probes known behavioral changes for the flags in that increment.

```yaml
# .github/workflows/compat-increment.yml
name: Compatibility Flag Increment

on:
  pull_request:
    paths:
      - "wrangler.toml"
      - "src/**"

jobs:
  compat-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Build Worker
        run: npm run build

      - name: Run Miniflare compatibility tests
        run: npm run test:compat
        env:
          # Pass current increment flags to test harness
          COMPAT_FLAGS: "fetch_refuses_unknown_protocols,formdata_parser_supports_files"

      - name: Deploy to staging
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run staging smoke tests
        run: npm run test:smoke -- --env staging
        timeout-minutes: 5
```

```typescript
// tests/compat/fetch-refuses-unknown-protocols.test.ts
import { describe, it, expect } from "vitest";

describe("fetch_refuses_unknown_protocols", () => {
  it("should reject ftp:// URLs", async () => {
    // In Workers, fetch('ftp://...') throws with this flag enabled
    const worker = await import("../../src/index");
    const req = new Request("https://example.com/proxy?url=ftp://malicious.com");
    const env = getMiniflareBindings();
    const ctx = new ExecutionContext();

    await expect(worker.default.fetch(req, env, ctx)).rejects.toThrow(
      /unsupported protocol/i
    );
  });
});
```

## Canary Period and Date Advancement

After a flag-increment PR is merged and has run in production for a soak period (recommended: 24-72 hours with no error-rate regression), advance the base `compatibility_date` to the earliest date that includes those flags. Remove the flags from the explicit list.

```bash
# Helper script: advance-compat-date.sh
# Usage: ./advance-compat-date.sh 2024-03-01
set -euo pipefail

NEW_DATE="$1"
WRANGLER_FILE="wrangler.toml"

# Validate date format
if ! date -d "$NEW_DATE" &>/dev/null; then
  echo "Invalid date: $NEW_DATE"
  exit 1
fi

# Sed replace compatibility_date lines (base and envs)
sed -i "s/^compatibility_date = \"[0-9-]*\"/compatibility_date = \"$NEW_DATE\"/" "$WRANGLER_FILE"

echo "Updated compatibility_date to $NEW_DATE in $WRANGLER_FILE"
echo "Remember to remove flags now included in the base date from compatibility_flags."
```

## Rollback

If an increment causes production errors, roll back by removing the new flags from `compatibility_flags` and redeploying. Since the base `compatibility_date` did not advance, the Worker reverts to its previous behavior immediately.

```bash
# Emergency rollback: remove all pending compat flags
npx wrangler versions upload \
  --compatibility-flag "" \
  --message "compat-rollback: remove increment-3 flags" \
  --tag rollback

# Promote rolled-back version to 100% traffic
npx wrangler versions deploy --version-id <PREV_VERSION_ID> --percentage 100
```

## Anti-patterns

- Bumping `compatibility_date` by a year or more in a single commit without first testing individual flags
- Relying only on unit tests that mock `fetch` — compatibility changes affect the runtime, not userland mocks
- Leaving flags in `compatibility_flags` indefinitely instead of advancing the base date, creating an ever-growing explicit list
- Skipping the staging canary and deploying flag increments directly to 100% production
- Using `compatibility_flags = []` (empty explicit list) to clear flags — this has no effect; you must use `no_<flag_name>` to opt out

## Gotchas

- `compatibility_date` in `[env.production]` overrides the top-level value; both must be updated
- `wrangler dev` picks up `compatibility_flags` from the top-level block, not env blocks — always test with `--env production` locally when flags differ per env
- Some flags only take effect at runtime after a cold start; a warm Worker may appear unaffected until it restarts
- The `nodejs_compat` meta-flag enables multiple Node.js compatibility flags at once; audit which individual flags it activates before using it in incremental migration
- Workers deployed via Pages Functions inherit `compatibility_date` from the Pages project settings, not `wrangler.toml` — update both locations

## Verification

1. After each increment deploy, run `wrangler tail --env production` and monitor for new exception types for at least 15 minutes.
2. Query Analytics Engine or Logpush for error-rate change: `error_rate = errors / requests` should stay within ±0.1% of baseline.
3. Confirm the active flags on a live Worker: `curl https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name} -H "Authorization: Bearer $TOKEN"` — the response includes `compatibility_date` and `compatibility_flags`.
4. After advancing the base date, verify `compatibility_flags` is empty or contains only intentional overrides.

## Related

- `wrangler-config-validation-pre-deploy-ci-hook.md` — validating wrangler.toml before deploy
- `worker-versioning-gradual-rollout.md` — gradual rollout of new Worker versions
- `workers-d1-pre-deploy-migration-safety.md` — pre-deploy safety checks for D1
- `rollback-strategies-workers-pages.md` — general rollback patterns for Workers

## Sources

- Cloudflare Workers Compatibility Dates: https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- Cloudflare workerd compatibility-date.capnp: https://github.com/cloudflare/workerd/blob/main/src/workerd/io/compatibility-date.capnp
- Wrangler configuration reference: https://developers.cloudflare.com/workers/wrangler/configuration/
