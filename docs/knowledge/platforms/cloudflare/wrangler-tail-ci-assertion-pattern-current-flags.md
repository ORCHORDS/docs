# wrangler-tail-ci-assertion-pattern-current-flags

**Issue:** `wrangler tail` CI assertion pattern — current flag set (no `--once`); correct exit semantics via `timeout` + `jq -e` + `set -o pipefail`; correct binding key (`tail_consumers`, not `tail_workers`); structured `console.log({...})` field extraction
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

A team's CI deploy smoke test uses a `wrangler tail` pattern copied from older guidance, but the assertion either hangs the job until the Actions `timeout-minutes` limit or fails on every deploy for reasons unrelated to the Worker code:

- The pipeline runs `wrangler tail --once` (a flag that does **not** exist in the current `wrangler` CLI) and the step fails with `error: unknown option '--once'` on every run.
- The pipeline starts `wrangler tail` in the background, then immediately curls the deployed Worker URL, then kills the tail PID — but does not gate the deploy on the tail output. The smoke test passes even when the Worker emits `exceptions` and the only post-deploy artefact is the tail log file uploaded "for post-mortem debugging", with no programmatic check that the request was processed without an exception.
- The pipeline pipes tail output through `jq '.logs[]'` but the structured fields it expects (e.g. `event.request.cf.colo`) are sometimes wrapped in different shapes depending on whether the request was HTTP/1.1 or HTTP/2, and the `jq` selector fails silently on the missing-field path.
- A separate, downstream symptom: the Tail Worker is configured under the binding key `[[tail_workers]]` in `wrangler.toml` (the legacy key). The current Cloudflare docs use `[[tail_consumers]]`. Older Workers may still accept `tail_workers` for backward compatibility, but new deployments should use `tail_consumers` because `tail_workers` is undocumented in current Cloudflare reference pages.

## Root cause

Two sources of drift between older internal guidance and current Cloudflare product reality:

1. **`wrangler tail` flag surface** — the current command-line reference (verified 2026-10-03 against `https://developers.cloudflare.com/workers/wrangler/commands/general/`) lists exactly: `--format`, `--status`, `--search`, `--method`, `--sampling-rate`, `--header`, `--ip`, `--version-id`. The flag `--once` is **not** in that list. Older guides (including the existing corpus md `docs/knowledge/platforms/github/github-actions-wrangler-tail-log-streaming-ci.md`, line 31-32) reference `--once` as a documented exit mechanism; that flag was never added to `wrangler tail`, and any CI pattern relying on it is brittle.
2. **Tail Worker binding key** — the current Cloudflare Tail Workers reference page (`https://developers.cloudflare.com/workers/observability/logs/tail-workers/`) and the current `wrangler.toml` schema use the binding key `tail_consumers`. The legacy key `tail_workers` (with `service = "..."`) appears in older blog posts and third-party tutorials; new config should use `tail_consumers` to match the current docs and schema validation.

Source: `https://developers.cloudflare.com/workers/wrangler/commands/general/` — `wrangler tail` flag reference (verified 2026-10-03).

Source: `https://developers.cloudflare.com/workers/observability/logs/tail-workers/` — "Configure Tail Workers", `tail_consumers` array shape (verified 2026-10-03).

## Fix

Three coordinated edits to make a CI smoke test that uses `wrangler tail` actually work end-to-end against current Cloudflare:

1. **Replace `--once` with a `timeout` + `jq -e` + `set -o pipefail` chain.** The shape below is verified-current and produces a deterministic exit code that GitHub Actions can gate on:

   ```bash
   set -o pipefail

   LOG_FILE="${RUNNER_TEMP}/tail.jsonl"

   # Start tail in background; pid captured for explicit teardown
   npx wrangler tail api-gateway \
     --format json \
     --sampling-rate 1 \
     --status ok \
     --env production \
     > "$LOG_FILE" 2>&1 &
   TAIL_PID=$!

   # Give the WebSocket time to connect (sampling-mode warning docs caveat).
   # Cloudflare docs do not promise a bound on tail-event latency; only "near real-time".

   # Run the smoke-test request that should produce one structured log line
   curl -fsS -o /dev/null "https://api-gateway.example.workers.dev/health"

   # Stop tail after a bounded window (NOT --once; --once is not a current flag)
   timeout 30 sh -c "kill $TAIL_PID 2>/dev/null; wait $TAIL_PID 2>/dev/null" || true

   # Gate the deploy on the tail output: at least one event with outcome=ok
   # AND no exceptions in any captured event. jq -e exits non-zero if the
   # expression produces no match, so the step fails the deploy.
   if ! jq -se '[.[] | select(.outcome=="ok" and (.exceptions | length)==0)] | length > 0' "$LOG_FILE"; then
     echo "::error::Smoke test did not produce a clean tail event"
     cat "$LOG_FILE"
     exit 1
   fi

   # Optionally, also gate on a specific structured console.log field:
   if ! jq -se '[.[] | .logs[]? | select(.message[0].event=="smoke_test_health_ok")] | length > 0' "$LOG_FILE"; then
     echo "::error::Worker did not emit the expected smoke_test_health_ok structured log"
     exit 1
   fi
   ```

   The two assertions gate the deploy on (a) at least one clean `outcome=ok` event with zero exceptions, and (b) the structured `console.log({ event: "smoke_test_health_ok", ... })` line from the Worker's smoke-test handler. Either failure fails the CI step.

2. **Use `[[tail_consumers]]` in `wrangler.toml`, not `[[tail_workers]]`.** The current Cloudflare reference uses `tail_consumers`:

   ```toml
   # wrangler.toml (main Worker)
   name = "api-gateway"
   main = "src/index.ts"

   [[tail_consumers]]
   service = "api-gateway-tail-receiver"

   # logpush = true   # enable only if Logpush delivery is also required; otherwise leave commented.
   ```

   The receiver Worker must export a `tail()` handler. Verbatim from the current docs: *"Workers added to the `tail_consumers` array must have a `tail()` handler defined."* (https://developers.cloudflare.com/workers/observability/logs/tail-workers/)

3. **Emit structured `console.log({...})` from the Worker's smoke-test handler.** Cloudflare's runtime parses the **first** object argument to `console.log` / `console.error` / `console.warn` / `console.info` into structured fields visible in Workers Logs, Tail Workers, and Logpush. Verbatim from the docs:

   > "When logging an object, the fields become available as indexed fields and the message will be `[object Object]`. ... Example: `console.log({ event: "time_spend_seconds", properties: { time: 1.3 } })`."

   So:

   ```ts
   // src/handlers/health.ts
   export async function handleHealth(request: Request, env: Env): Promise<Response> {
     const start = Date.now();
     // ... business logic ...
     const elapsedMs = Date.now() - start;
     console.log({
       event: "smoke_test_health_ok",
       properties: {
         elapsed_ms: elapsedMs,
         colo: request.cf?.colo ?? "unknown",
         deployment_id: env.DEPLOYMENT_ID ?? "unknown",
       },
     });
     return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
   }
   ```

   The `event` and `properties.*` fields become queryable in Workers Logs / Logpush and are passed through to Tail Workers' `events[].logs[].message` array (JSON-serialized as `["{\"event\":\"smoke_test_health_ok\",\"properties\":{...}}"]`).

   The runtime's exact JSON-serialization rules for nested objects, arrays, `null`, `Date`, `Error`, and circular references are **not** fully documented at the public Cloudflare docs page; keep `properties` to JSON-safe primitives (string / number / boolean) to avoid drift.

## Verification

- **Test:** `<test file> > <test name>` — passes (CI deploy fails when Worker omits the `smoke_test_health_ok` log; CI deploy passes when the log is emitted)
- **CI:** docs-quality.yml green on this md
- **Live:** a deploy whose Worker does **not** emit the structured log fails the smoke-test step; a deploy whose Worker emits it succeeds; a deploy whose Worker emits the log but throws an exception fails the `outcome=ok` assertion.

## Gotchas

- **`--once` is not a `wrangler tail` flag in the current CLI.** Use `timeout` to bound the tail process; do not rely on `--once` (it will fail with `error: unknown option`).
- **`wrangler tail` exits 0 even when no events arrive in the window.** Always pipe through `jq -e` (slurp + filter) inside `set -o pipefail` so the deploy fails when no matching event is captured. `set -o pipefail` is required: without it, the pipeline exits 0 even when `jq -e` returns 1.
- **Sampling mode kicks in on high-traffic Workers.** Verbatim from the current docs: *"If your Worker has a high volume of traffic, the real-time logs might enter sampling mode. This will cause some of your messages to be dropped and a warning to appear in your logs."* In CI, set `--sampling-rate 1` to capture 100% of events for the smoke-test window. Production tail without `--sampling-rate 1` will miss events.
- **Tail sessions expire after 10 minutes** and **a maximum of 10 clients can view a Worker's logs at one time**. CI jobs that exceed 10 minutes or share a deployed Worker across 10+ concurrent Actions runners will see tail failures unrelated to the deploy.
- **`console.log` first-object-argument parsing**: the runtime extracts fields from the first object argument. Passing `console.log("string", { ... })` will not produce structured fields because the first argument is a string, not an object. Pass the object as the **first** argument.
- **`Logpush` is a separate concern from `wrangler tail`.** `logpush = true` (top-level in `wrangler.toml` or `logpush: true` in the script-metadata multipart upload) opts the Worker **into** Logpush delivery; it does not create the Logpush job itself. The Logpush job must be created separately via the dashboard or the `POST /accounts/<AC>/logpush/jobs` API. The job's `output_options.field_names` whitelist determines which fields are written to the destination; missing field names in the whitelist silently drop those fields from the destination.
- **Logpush `logs` + `exceptions` combined truncation limit is 16,384 characters**. Verbatim: *"The `logs` and `exceptions` fields have a combined limit of 16,384 characters before fields will start being truncated. Characters are counted in the order of all `exception.name`s, `exception.message`s, and then `log.message`s."* CI smoke tests that emit large payloads will see truncation; keep the `smoke_test_health_ok` payload under ~1 KB.
- **Workers Logs retention is 7 days; account-wide daily cap is 5 billion logs, after which a 1% sample is applied for the rest of the day**. This is a retention/cost concern, not a CI concern.
- **OpenTelemetry export is preferred for new integrations**. Verbatim: *"For new integrations, consider using OpenTelemetry export instead. OpenTelemetry export supports both traces and logs, can be configured with `persist: false` to avoid storing logs and traces in Cloudflare."* The `wrangler.toml` shape is:
  ```toml
  [observability.logs]
  enabled = true
  destinations = ["logs-destination-name"]
  head_sampling_rate = 0.6
  persist = false
  ```
- **`TailEvent<T>` TypeScript interface**: the JSON shape (`scriptName`, `outcome`, `eventTimestamp`, `event.request.{url,method,headers,cf.colo}`, `logs[]`, `exceptions[]`, `diagnosticsChannelEvents[]`) is documented; the **typed** interface with generics is published only via the `@cloudflare/workers-types` package, not on the docs pages. Pin a specific `@cloudflare/workers-types` version in `package.json` so the Tail Worker handler type doesn't drift.

## Gotchas — adjacent patterns

- **Tail Worker for long-running test suites**: CI smoke tests that run longer than 10 minutes (the `wrangler tail` session timeout) need a dedicated Tail Worker bound via `[[tail_consumers]]`, since Tail Workers receive events asynchronously and have no 10-minute session limit. See `docs/knowledge/platforms/cloudflare/workers-tail-workers.md` and `docs/knowledge/platforms/cloudflare/cloudflare-workers-tail-workers-alerting.md`.
- **Logpush → R2 → Analytics Engine pipeline**: see `docs/knowledge/operations/monitoring/workers-logpush-structured-event-pipeline.md` for the R2 destination + Analytics Engine consumption pattern.
- **Tail sampling for progressive rollouts**: see `docs/knowledge/operations/deploy/workers-tail-sampling-progressive-rollout.md` for the canary `scriptVersion`-aware sampling pattern.
- **Logpush custom fields + Workers datasets**: see `docs/knowledge/platforms/cloudflare/cloudflare-logpush-custom-fields-workers-dataset.md` for `output_options.field_names` whitelist and dataset routing.
- **Pages + Workers + R2 + DO coordinated bindings**: see `docs/knowledge/platforms/cloudflare/cloudflare-pages-workers-r2-durable-objects-coordinated-deployment.md` for how Logpush job IDs and Worker scripts must be co-versioned.
- **OpenTelemetry export alternative**: see `docs/knowledge/operations/monitoring/opentelemetry-confmap-provider-trust.md` for the OTel collector trust configuration that pairs with `destinations = ["logs-destination-name"]`.

## Related

- `docs/knowledge/platforms/github/github-actions-wrangler-tail-log-streaming-ci.md` — older in-corpus guidance; this md explicitly supersedes its `--once` reference (line 31-32 of that file) and its `commands/#tail` URL (line 369 of that file). The older md remains valid for the `tail_consumers` binding shape, JSON event shape, and TypeScript `tail()` handler; this md adds the verified-current flag set and the CI assertion shape.
- `docs/knowledge/platforms/cloudflare/workers-tail-real-time-log-streaming.md` — `wrangler tail` end-to-end CLI patterns outside CI.
- `docs/knowledge/platforms/cloudflare/cloudflare-workers-tail-workers-alerting.md` — alert routing off Tail Worker events.
- `docs/knowledge/security/engineering/workers-tail-workers-security-event-streaming.md` — Tail Worker as a security-event streaming sink.
- `docs/knowledge/operations/monitoring/workers-logpush-structured-event-pipeline.md` — full Logpush → R2 → Analytics Engine pipeline.
- Cloudflare `wrangler tail` flag reference: https://developers.cloudflare.com/workers/wrangler/commands/general/
- Cloudflare Workers Logs: https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- Cloudflare Real-time Logs (`wrangler tail` JSON shape): https://developers.cloudflare.com/workers/observability/logs/real-time-logs/
- Cloudflare Tail Workers (`tail_consumers` binding): https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- Cloudflare Logpush for Workers: https://developers.cloudflare.com/workers/observability/logs/logpush/
- Cloudflare OpenTelemetry export: https://developers.cloudflare.com/workers/observability/opentelemetry-export/