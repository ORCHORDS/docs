# Wrangler Tail Log Streaming Across Multiple Environments in a Worktree Setup

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You maintain several Cloudflare Workers across staging, production, and canary environments. When a bug is reported you must simultaneously stream logs from multiple environments to correlate request timings, error rates, and sampling differences. Doing this from a single checkout means switching `wrangler.toml` environments or running several terminal tabs pointing at the same directory — both are fragile. You need clean per-environment log streams without interfering with each other or with ongoing development work.

---

## Context

`wrangler tail` attaches a WebSocket connection to the Cloudflare Tail Workers API and streams real-time log events (console output, exceptions, request metadata) to your terminal. Each invocation opens one connection per Worker name + environment pair. When you run two `wrangler tail` processes from the same worktree they share the same `wrangler.toml` and the same `.wrangler/` state directory, which can cause config reads to race and `wrangler.state` writes to collide on Windows (less common on Linux but still a risk with concurrent TOML merges).

A git worktree gives each environment its own isolated filesystem tree rooted at a different path, so each `wrangler tail` process reads its own config and writes its own state with no shared mutable files.

Wrangler environments (the `[env.staging]` blocks) let a single `wrangler.toml` describe multiple deployment targets. The tail command honours `--env` to select one of these blocks. The worktree pattern adds a layer of filesystem isolation on top, which is useful when you need custom `wrangler.toml` overrides per environment or when you want to pin different Wrangler versions per environment.

---

## Setting Up the Worktrees

```bash
# from the main repository root
git worktree add ../my-worker-staging main   # or the same branch
git worktree add ../my-worker-canary  main
git worktree add ../my-worker-prod    main
```

Each directory now has an independent working tree. Because `wrangler tail` is read-only (it does not deploy), all three worktrees can sit on the same commit; the isolation benefit is purely about config and state files.

---

## Wrangler Config Per Worktree

If environments share a single `wrangler.toml` this step is optional. It becomes necessary when:
- Different environments need different `compatibility_date` pins.
- You want to override `tail_consumers` or sampling rates per environment.
- You pin a different `wrangler` version in each package.json for backward compatibility.

```toml
# ../my-worker-staging/wrangler.toml  (or a wrangler.staging.toml)
name = "my-worker"
compatibility_date = "2025-11-01"

[env.staging]
name = "my-worker-staging"
workers_dev = false
route = { pattern = "staging.example.com/*", zone_name = "example.com" }
```

```toml
# ../my-worker-prod/wrangler.toml
name = "my-worker"
compatibility_date = "2025-09-01"

[env.production]
name = "my-worker-production"
workers_dev = false
route = { pattern = "example.com/*", zone_name = "example.com" }
```

---

## Streaming Logs: Shell Script

```bash
#!/usr/bin/env bash
# scripts/tail-all.sh
# Usage: ./scripts/tail-all.sh [--filter-level error]
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREES=(
  "${REPO_ROOT}/../my-worker-staging:staging"
  "${REPO_ROOT}/../my-worker-canary:canary"
  "${REPO_ROOT}/../my-worker-prod:production"
)
EXTRA_ARGS=("$@")

cleanup() {
  echo "Stopping all tail processes…"
  kill 0
}
trap cleanup EXIT INT TERM

for spec in "${WORKTREES[@]}"; do
  dir="${spec%%:*}"
  env="${spec##*:}"
  (
    cd "$dir"
    # prefix each line with the environment name for easy grepping
    wrangler tail --env "$env" "${EXTRA_ARGS[@]}" 2>&1 \
      | sed "s/^/[$env] /"
  ) &
done

wait
```

Run it:

```bash
chmod +x scripts/tail-all.sh
./scripts/tail-all.sh --format pretty
# or filter to errors only:
./scripts/tail-all.sh --filter-level error --format json
```

---

## TypeScript Tail Consumer Filter (Advanced)

For programmatic filtering, deploy a Tail Worker that consumes events from multiple source Workers and fans them out to a shared destination such as Cloudflare Logpush or an R2 bucket:

```typescript
// tail-consumer/src/index.ts
export interface Env {
  LOG_BUCKET: R2Bucket;
  ENVIRONMENT: string;
}

interface TailItem {
  scriptName: string;
  outcome: "ok" | "exception" | "exceededCpu" | "exceededMemory" | "canceled";
  exceptions: Array<{ name: string; message: string; timestamp: number }>;
  logs: Array<{ message: unknown[]; level: string; timestamp: number }>;
  eventTimestamp: number;
  event: {
    request?: {
      method: string;
      url: string;
      headers: Record<string, string>;
    };
  };
}

export default {
  async tail(events: TailItem[], env: Env): Promise<void> {
    const errors = events.filter(
      (e) => e.outcome !== "ok" || e.exceptions.length > 0
    );

    if (errors.length === 0) return;

    const key = `${env.ENVIRONMENT}/${new Date().toISOString()}-${crypto.randomUUID()}.json`;

    await env.LOG_BUCKET.put(
      key,
      JSON.stringify({ environment: env.ENVIRONMENT, events: errors }),
      { httpMetadata: { contentType: "application/json" } }
    );
  },
} satisfies ExportedHandler<Env>;
```

Bind this Tail Worker to each source Worker via `wrangler.toml`:

```toml
# in each environment's wrangler.toml
[[tail_consumers]]
service = "my-tail-consumer"
environment = "production"
```

---

## Multiplexed JSON Output

When you need machine-readable output from the shell script, switch to `--format json` and pipe to `jq` with a filter:

```bash
# real-time error stream from all environments, coloured by env
./scripts/tail-all.sh --format json | jq -r '
  if .outcome != "ok" then
    "\(.scriptName // "?") | \(.outcome) | \(.exceptions[0].message // "-")"
  else empty end
'
```

To persist structured logs:

```bash
./scripts/tail-all.sh --format json \
  | tee >(grep '"outcome":"exception"' >> /tmp/errors.jsonl) \
  | jq -r '"[\(.scriptName)] \(.outcome)"'
```

---

## Anti-patterns

- **Single worktree, multiple `wrangler tail` processes** — They share `.wrangler/state` and any in-flight config writes can corrupt state. Use isolated worktrees or at minimum isolated `WRANGLER_HOME` values.
- **`--format pretty` in CI or scripts** — Pretty output uses ANSI codes that break `grep` and JSON parsers. Always use `--format json` for automation.
- **Tailing without a sampling strategy** — High-traffic Workers emit thousands of events per second. Use `--sampling-rate 0.01` in production to avoid exceeding the Tail API rate limit (10 MB/s per account).
- **Hardcoding environment names in the script** — Derive them dynamically from `wrangler.toml` to stay in sync with config changes.
- **Running `tail` as the same Cloudflare account token across environments** — Works but complicates audit logs. Prefer per-environment API tokens scoped to `Workers Tail` with `Zone:Read` only.

---

## Gotchas

- `wrangler tail` requires the Worker to have at least one active deployment. Tailing a Worker that has never been deployed returns a 404-like error.
- Tail sessions automatically disconnect after 60 minutes of inactivity. The shell script's `wait` loop will then exit silently. Add a reconnect loop if you need persistent tailing.
- The `--filter-level` flag filters by `console.*` log level but does NOT filter by `outcome`. An `exception` outcome with no console output still appears unless you add `--filter-status 500` for HTTP Workers.
- Worktrees on the same machine share the same `~/.wrangler/` global config (OAuth tokens, telemetry). Only the project-local `.wrangler/` directory is isolated. Set `WRANGLER_HOME` per process if you need full isolation.
- On macOS inotify is unavailable; `wrangler tail` uses polling for config file changes. Linux workers with `inotify` will pick up config edits live.

---

## Verification

```bash
# 1. Confirm each worktree resolves the correct wrangler env
for dir in ../my-worker-{staging,canary,prod}; do
  echo "=== $dir ==="
  (cd "$dir" && wrangler whoami)
done

# 2. Dry-run the tail connection without streaming (exits after first event)
(cd ../my-worker-staging && wrangler tail --env staging --format json | head -1 | jq .)

# 3. Validate no shared state collisions during concurrent tail
lsof +D ~/.wrangler/ | grep wrangler | awk '{print $1, $2, $9}' | sort | uniq -d
# should be empty (no duplicate file handles to the same path from different pids)
```

---

## Related

- `git-worktree-parallel-wrangler-environments.md`
- `cloudflare-workers-observability-tail-workers.md`
- `wrangler-environments-staging-production.md`
- `wrangler-config-inheritance-environments-workers.md`
- `github-actions-matrix-workers-environments.md`

---

## Sources

- Cloudflare Docs — [wrangler tail](https://developers.cloudflare.com/workers/wrangler/commands/#tail)
- Cloudflare Docs — [Tail Workers](https://developers.cloudflare.com/workers/observability/tail-workers/)
- Cloudflare Docs — [Wrangler environments](https://developers.cloudflare.com/workers/wrangler/environments/)
- Git SCM — [git-worktree(1)](https://git-scm.com/docs/git-worktree)
