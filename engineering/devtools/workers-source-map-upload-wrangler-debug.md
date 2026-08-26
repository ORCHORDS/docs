# Source Map Upload and Error Debugging in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a minified Worker bundle, errors in the Cloudflare dashboard show stack traces like `at Object.<anonymous> (index.js:1:24891)` — useless for production debugging. Enabling source map upload translates those into readable TypeScript file paths and line numbers without exposing source to end users.

## Context

- Cloudflare Workers (TypeScript, ESM)
- Wrangler 3.x
- esbuild as the bundler (used by Wrangler internally)
- Cloudflare dashboard Error Tracking or `wrangler tail`

---

## Step 1 — Enable Source Map Upload in wrangler.toml

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# Upload source maps on every `wrangler deploy`
upload_source_maps = true
```

Wrangler generates the source map alongside the bundle and uploads it to the Workers API automatically. Source maps are stored server-side and are never served to clients.

---

## Step 2 — Verify wrangler.toml Is Correct

```bash
# Dry-run to confirm source map generation without deploying
wrangler deploy --dry-run --outdir dist

# Inspect the output
ls -lh dist/
# dist/index.js
# dist/index.js.map   <-- source map should be present

# Confirm the map file references real source paths
jq '.sources | .[0:5]' dist/index.js.map
```

---

## Step 3 — Worker Source Code (Example)

```typescript
// src/index.ts
export interface Env {
  API_TOKEN: string;
}

interface RequestPayload {
  userId: string;
  action: string;
}

async function processAction(payload: RequestPayload, env: Env): Promise<Response> {
  if (!payload.userId) {
    // This line number will appear correctly in stack traces after source maps
    throw new Error("userId is required");
  }

  if (!payload.action) {
    throw new Error("action is required");
  }

  // Simulate downstream call
  const resp = await fetch("https://api.example.com/actions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    throw new Error(`Upstream error: ${resp.status} ${resp.statusText}`);
  }

  return Response.json(await resp.json());
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const payload = await request.json<RequestPayload>();
      return await processAction(payload, env);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      console.error("Worker error:", message, err instanceof Error ? err.stack : "");
      return new Response(JSON.stringify({ error: message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
```

---

## Step 4 — Deploy With Source Maps

```bash
# Standard deploy — source maps are uploaded automatically when upload_source_maps = true
wrangler deploy

# Output will include:
# Uploaded my-worker (2.34 sec)
# Uploaded source map for my-worker
# Published my-worker
```

If source map upload fails (e.g. network timeout), the Worker is still deployed. Re-run `wrangler deploy` to retry the upload.

---

## Step 5 — Reading Mapped Stack Traces in the Dashboard

1. Open **Workers & Pages** → your Worker → **Logs** tab.
2. Filter by **Exceptions** or search for the error message.
3. Click an exception entry — the stack trace pane shows **original source file paths** and line numbers.
4. Source mappings are applied automatically; no toggle required.

The dashboard stores the last 100 unique stack frames per Worker version.

---

## Step 6 — Live Tail With Source Mapping

`wrangler tail` streams live logs. From Wrangler 3.28+ it resolves source maps locally if `dist/` contains the map file:

```bash
# Stream live logs with local source map resolution
wrangler tail my-worker --format pretty

# JSON output for piping to jq
wrangler tail my-worker --format json | jq '.exceptions[].stack'

# Filter to errors only
wrangler tail my-worker --status error
```

For local source map resolution to work, keep the `dist/` directory from the last deploy intact (do not clean it before tailing).

---

## Step 7 — Manual Source Map Resolution (Debugging Script)

When you need to resolve a stack frame offline:

```typescript
// scripts/resolve-stack.ts
import { readFileSync } from "fs";
import { SourceMapConsumer } from "source-map";

async function resolveFrame(
  mapFile: string,
  generatedLine: number,
  generatedColumn: number
): Promise<void> {
  const rawMap = JSON.parse(readFileSync(mapFile, "utf8"));

  await SourceMapConsumer.with(rawMap, null, (consumer) => {
    const pos = consumer.originalPositionFor({
      line: generatedLine,
      column: generatedColumn,
    });
    console.log(`Original position:`);
    console.log(`  File:   ${pos.source}`);
    console.log(`  Line:   ${pos.line}`);
    console.log(`  Column: ${pos.column}`);
    console.log(`  Name:   ${pos.name}`);
  });
}

// Usage: ts-node scripts/resolve-stack.ts
resolveFrame("dist/index.js.map", 1, 24891).catch(console.error);
```

```bash
npm install source-map
npx ts-node scripts/resolve-stack.ts
```

---

## Step 8 — CI: Assert Source Map Is Generated

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Build and deploy
  run: wrangler deploy --dry-run --outdir dist

- name: Assert source map exists
  run: |
    if [ ! -f dist/index.js.map ]; then
      echo "ERROR: source map not generated" && exit 1
    fi
    MAP_SIZE=$(stat -c%s dist/index.js.map)
    echo "Source map size: ${MAP_SIZE} bytes"
    [ "$MAP_SIZE" -gt 1000 ] || (echo "Source map suspiciously small" && exit 1)

- name: Deploy to production
  run: wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Anti-patterns

- Setting `upload_source_maps = false` to save deploy time — the upload is asynchronous and adds < 1 s typically.
- Deleting `dist/` before running `wrangler tail` — removes local source map resolution capability.
- Committing `dist/*.js.map` to the repo — source maps often contain full source; keep them out of git via `.gitignore`.
- Using `//# sourceMappingURL=` pointing to a public URL — Workers source maps must be uploaded, not referenced externally.
- Logging raw `Error` objects with `JSON.stringify` — circular references cause serialisation errors; always log `.message` and `.stack`.

## Gotchas

- Source maps for Workers are per-version; switching to an older Worker version in the dashboard reverts to that version's maps.
- If the Worker uses dynamic `eval()` or `new Function()`, source mapping breaks for those frames.
- `wrangler tail` source map resolution requires that the local `dist/` path matches the paths recorded in the map's `sourceRoot`.
- Free plan Workers do not support Error Tracking in the dashboard; use `wrangler tail` instead.

---

## Verification

```bash
# Confirm source map was uploaded for current version
wrangler deployments list | head -5

# Trigger an intentional error and tail
wrangler tail my-worker --status error &
curl https://my-worker.example.workers.dev/ \
  -d '{"badKey": true}' \
  -H 'Content-Type: application/json'
# Wait for the mapped stack trace to appear in tail output
```

---

## Related

- `documentation/categories/devtools/workers-module-graph-analysis-esbuild-metafile.md`
- `documentation/categories/devtools/workers-biome-linter-formatter-replace-eslint.md`

## Sources

- https://developers.cloudflare.com/workers/observability/source-maps/
- https://developers.cloudflare.com/workers/wrangler/configuration/#source-maps
- https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- https://esbuild.github.io/api/#source-maps
- https://github.com/mozilla/source-map
