# Workers Script Size Limit Exceeded Blocked Production Deploy

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A routine deploy of the example project platform's main orchestration Worker failed with `Script size exceeds the 10 MiB limit` shortly after the team merged a large feature branch that bundled several new AI inference utilities and a vendored WASM binary. The CI pipeline reported a successful build but the Wrangler upload step exited with a non-zero code, blocking the release window. No traffic was affected because the previous Worker version continued serving, but the hotfix for a payment callback race condition that was included in the same bundle could not ship.

## Context

The example project orchestration Worker (`example project-router`) is the primary edge entry point. Over 18 months it had accumulated: a shared crypto library (libsodium-wasm), a WASM-compiled PDF renderer used for receipt generation, two large dependency trees pulled in by an ORM compatibility shim, and locale message bundles for 12 languages bundled as inline JSON strings. The Worker historically sat at around 7.8 MiB compressed. The team treated the size figure as a trailing metric rather than a build gate, so no budget alert existed.

## Timeline

- **09:15 UTC** – Feature branch `feat/ai-summary-cards` is merged to `main`. Bundle includes `@xenova/transformers` tokenizer (partial) and a third-party chart-rendering WASM.
- **09:22 UTC** – CI build completes successfully (esbuild produces output, no size check configured).
- **09:24 UTC** – Wrangler `deploy` step fails: `Error: Script startup exceeded limits. Script size: 11.4 MiB. Limit: 10 MiB.`
- **09:25 UTC** – On-call engineer receives PagerDuty alert from the deploy pipeline webhook.
- **09:31 UTC** – Initial theory: transient Cloudflare API error. Deploy is retried; same failure.
- **09:38 UTC** – Engineer inspects `esbuild --metafile` output; identifies `@xenova/transformers` (1.9 MiB) and chart WASM (0.9 MiB) as the largest new additions.
- **09:55 UTC** – Decision: strip the chart WASM (not yet used in production gating), defer AI tokenizer to a dedicated Worker.
- **10:08 UTC** – Patched bundle measures 8.9 MiB; deploy succeeds. Payment hotfix ships.
- **10:20 UTC** – Post-incident retro scheduled. Size budget alerting added as P1 ticket.

## Root Cause

The esbuild bundler had no configured size limit check. `@xenova/transformers` was added as a top-level dependency in `package.json` without realising that even a tree-shaken import of its tokenizer utilities pulled in a large WASM side-load and substantial JS glue code. The chart WASM binary was committed directly to the repo and imported via a `?raw` loader. Neither addition was flagged during code review because reviewers focused on functionality, not bundle impact. The cumulative script size crossed the Cloudflare Workers 10 MiB compressed limit at upload time.

## Fix: Bundle Size Gate and Worker Splitting

The immediate fix was to remove the two large assets from `example project-router` and move the AI tokenizer work to a dedicated Worker (`example project-ai-summariser`) invoked via Service Bindings, and to serve the chart WASM from R2 rather than bundling it.

Long-term, a mandatory bundle-size check was added to the CI pipeline that fails the build before Wrangler even attempts an upload.

```typescript
// scripts/check-bundle-size.ts
// Run after esbuild: ts-node scripts/check-bundle-size.ts

import { statSync } from "fs";
import { gzipSync } from "zlib";
import { readFileSync } from "fs";

const BUNDLE_PATH = "dist/worker.js";
const WASM_PATHS = ["dist/*.wasm"];
const LIMIT_BYTES = 9_437_184; // 9 MiB — hard stop before Cloudflare's 10 MiB gate

function gzippedSize(filePath: string): number {
  const content = readFileSync(filePath);
  return gzipSync(content).byteLength;
}

const jsSize = gzippedSize(BUNDLE_PATH);
console.log(`Worker JS (gzip): ${(jsSize / 1024 / 1024).toFixed(2)} MiB`);

if (jsSize > LIMIT_BYTES) {
  console.error(
    `❌ Bundle size ${(jsSize / 1024 / 1024).toFixed(2)} MiB exceeds limit ` +
    `${(LIMIT_BYTES / 1024 / 1024).toFixed(2)} MiB. Split large modules into dedicated Workers.`
  );
  process.exit(1);
}

console.log("✅ Bundle size within limit.");
```

For WASM assets that genuinely need to live close to the Worker, load them from R2 at startup and cache in memory rather than bundling:

```typescript
// src/wasm-loader.ts
let wasmModule: WebAssembly.Module | null = null;

export async function getChartWasm(env: Env): Promise<WebAssembly.Module> {
  if (wasmModule) return wasmModule;

  const obj = await env.example project_ASSETS.get("chart-renderer.wasm");
  if (!obj) throw new Error("chart-renderer.wasm not found in R2");

  const buffer = await obj.arrayBuffer();
  wasmModule = await WebAssembly.compile(buffer);
  return wasmModule;
}
```

For the AI tokenizer, move processing to a dedicated Worker and call it via Service Binding:

```typescript
// wrangler.toml (example project-router)
// [[services]]
// binding = "AI_SUMMARISER"
// service = "example project-ai-summariser"

// src/handlers/summary.ts
export async function handleSummaryRequest(
  request: Request,
  env: Env
): Promise<Response> {
  // Delegate to the dedicated AI Worker — keeps example project-router lean
  return env.AI_SUMMARISER.fetch(request);
}
```

## Prevention Checklist

- [ ] Add a bundle-size CI step that fails the build above a configured MiB threshold (set threshold at 90% of platform limit).
- [ ] Configure esbuild `--metafile` output and archive it as a CI artefact so size regressions are visible per-PR.
- [ ] Enforce an `npm install` review checklist item for any new dependency with an unpacked size above 500 KB.
- [ ] Split any WASM binary larger than 1 MiB into an R2-loaded asset or dedicated Worker rather than bundling.
- [ ] Add a Worker splitting ADR: document which example project concerns belong in `example project-router` vs. purpose-specific child Workers.

## Monitoring Gaps Identified

- No build-time size check existed; the first signal of an oversized bundle was a failed Wrangler upload in the deploy step, too late to catch during development.
- No trending dashboard tracked Worker bundle size over time, so the slow accumulation from 7.8 MiB to 11.4 MiB was invisible.

## Anti-patterns

- Treating the Cloudflare 10 MiB limit as a distant concern and only discovering it when a deploy fails in a production release window.
- Importing a large ML inference library (`@xenova/transformers`) as a convenience import without profiling its contribution to the bundle.
- Committing compiled WASM binaries directly to the repository without documenting their size or checking whether they can be loaded at runtime instead.

## Gotchas

- Cloudflare's documented limit is 10 MiB for the compressed (gzip) script; esbuild reports the uncompressed output size, so a script that looks safe at 18 MiB uncompressed may or may not pass — always measure the gzipped size.
- `wrangler deploy --dry-run` still performs the upload step to validate; it will catch the size limit but wastes time. A local size check is faster.
- Service Binding calls between Workers are billed as a new Worker invocation; account for this in cost projections when splitting large Workers.

## Verification

```bash
# Build the Worker and check gzipped size locally before deploying
pnpm run build

# Check gzipped bundle size
gzip -c dist/worker.js | wc -c | awk '{printf "%.2f MiB\n", $1/1024/1024}'

# Run the explicit size-gate script
pnpm run check:bundle-size

# Dry-run deploy to validate against Cloudflare's API without routing traffic
npx wrangler deploy --dry-run --env production

# Inspect the metafile to find the top contributors
npx esbuild src/index.ts --bundle --metafile=meta.json --outfile=/dev/null 2>/dev/null
npx esbuild-visualizer --metadata meta.json --open
```

## Related

- `lessons/workers-cpu-time-premature-optimization.md`
- `lessons/cloudflare-storage-primitive-selection.md`
- `lessons/build-vs-buy-cloudflare-adjacent-tooling.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/workers/configuration/bindings/service-bindings/
