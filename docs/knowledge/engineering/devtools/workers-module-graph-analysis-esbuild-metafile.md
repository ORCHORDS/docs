# Analyzing Workers Bundle With esbuild Metafile

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers bundle exceeds the 1 MB (free) or 10 MB (paid) compressed size limit, or cold-start latency is higher than expected. Identifying which dependencies are bloating the bundle requires inspecting the module graph — esbuild's metafile and the `esbuild-visualizer` treemap make this actionable without guesswork.

## Context

- Cloudflare Workers (TypeScript, ESM)
- esbuild used directly or via a custom build script (not Wrangler's internal bundler)
- Node 20
- Optional: Wrangler 3.x for deploy step

---

## Step 1 — Custom esbuild Build Script

```typescript
// scripts/build.ts
import esbuild from "esbuild";
import { writeFileSync } from "fs";

const result = await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  outfile: "dist/index.js",
  format: "esm",
  target: "es2022",
  platform: "browser",  // Workers run in a browser-like environment
  minify: true,
  sourcemap: true,
  treeShaking: true,

  // Enable metafile for bundle analysis
  metafile: true,

  define: {
    "process.env.NODE_ENV": '"production"',
  },

  // Externals — do not bundle platform APIs
  external: ["cloudflare:sockets", "node:*"],
});

// Write metafile for offline analysis
if (result.metafile) {
  writeFileSync("dist/meta.json", JSON.stringify(result.metafile));
  console.log("Metafile written to dist/meta.json");

  // Print built-in analysis text
  const analysisText = await esbuild.analyzeMetafile(result.metafile, {
    verbose: false,
  });
  console.log(analysisText);
}
```

```bash
npm install --save-dev esbuild
npx ts-node scripts/build.ts
```

---

## Step 2 — Understanding the Metafile Structure

```typescript
// scripts/inspect-meta.ts
import metafile from "../dist/meta.json" assert { type: "json" };

// List all inputs sorted by byte size descending
const inputs = Object.entries(metafile.inputs)
  .map(([path, info]) => ({ path, bytes: info.bytes }))
  .sort((a, b) => b.bytes - a.bytes);

console.log("Top 20 largest inputs:");
for (const { path, bytes } of inputs.slice(0, 20)) {
  const kb = (bytes / 1024).toFixed(1);
  console.log(`  ${kb.padStart(8)} KB  ${path}`);
}

// Show total output size
for (const [outPath, outInfo] of Object.entries(metafile.outputs)) {
  const kb = (outInfo.bytes / 1024).toFixed(1);
  console.log(`\nOutput: ${outPath}  ${kb} KB`);
}
```

```bash
npx ts-node scripts/inspect-meta.ts
```

Example output:

```
Top 20 largest inputs:
   412.3 KB  node_modules/some-heavy-lib/dist/index.js
   108.7 KB  node_modules/zod/lib/index.mjs
    56.2 KB  node_modules/date-fns/esm/index.js
     4.1 KB  src/index.ts
     1.8 KB  src/lib/validate.ts

Output: dist/index.js  289.4 KB
```

---

## Step 3 — Visual Treemap With esbuild-visualizer

```bash
npm install --save-dev esbuild-visualizer

# Generate an interactive treemap HTML report
npx esbuild-visualizer --metadata dist/meta.json --filename dist/treemap.html --open
```

The treemap shows each module as a proportionally sized rectangle. Hover for exact byte counts. Modules from `node_modules/` that are large candidates for:

- **Replacing** with a lighter alternative (e.g., `date-fns` → `luxon` or native `Intl`)
- **Lazy-loading** via dynamic `import()` (Workers support top-level async handlers)
- **Tree-shaking** by switching to named imports

---

## Step 4 — Identifying Large Dependencies to Lazy-load

```typescript
// src/index.ts — BEFORE: eager import (always bundled)
import { parse } from "some-heavy-parser";

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });
    const result = parse(await request.text());
    return Response.json(result);
  },
};
```

```typescript
// src/index.ts — AFTER: lazy import (code-split)
export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    // Dynamic import — esbuild splits this into a separate chunk
    const { parse } = await import("./lib/heavy-parser.js");
    const result = parse(await request.text());
    return Response.json(result);
  },
};
```

Note: Workers support ES module dynamic `import()` at runtime. Update the esbuild config to allow splitting:

```typescript
const result = await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  outdir: "dist",         // Must use outdir (not outfile) for code splitting
  format: "esm",
  splitting: true,         // Enable code splitting for dynamic imports
  metafile: true,
  // ... rest of config
});
```

---

## Step 5 — Tree-shaking Audit

```typescript
// scripts/audit-tree-shaking.ts
import metafile from "../dist/meta.json" assert { type: "json" };

// Find modules with high bytesIn but low utilisation (many exports unused)
const suspects: Array<{ path: string; bytes: number; exports: number }> = [];

for (const [path, info] of Object.entries(metafile.inputs)) {
  // Modules with > 50 KB that are in node_modules
  if (info.bytes > 50_000 && path.includes("node_modules")) {
    suspects.push({
      path,
      bytes: info.bytes,
      exports: info.imports?.length ?? 0,
    });
  }
}

suspects.sort((a, b) => b.bytes - a.bytes);
console.log("Large node_modules candidates for review:");
for (const s of suspects) {
  console.log(`  ${(s.bytes / 1024).toFixed(1)} KB  ${s.path}`);
}
```

---

## Step 6 — Comparing Bundle Sizes Before and After

```bash
#!/usr/bin/env bash
# scripts/size-compare.sh

set -euo pipefail

BEFORE=$(wc -c < dist/index.js)
echo "Before: ${BEFORE} bytes"

# Apply change (e.g., switch to lighter dep)
npx ts-node scripts/build.ts

AFTER=$(wc -c < dist/index.js)
echo "After:  ${AFTER} bytes"

DELTA=$(( AFTER - BEFORE ))
if [ $DELTA -lt 0 ]; then
  echo "Saved: $(( -DELTA )) bytes"
else
  echo "Grew by: ${DELTA} bytes"
fi

# Gzip comparison (Cloudflare measures compressed size)
BEFORE_GZ=$(gzip -c dist/index.js.bak | wc -c 2>/dev/null || echo 0)
AFTER_GZ=$(gzip -c dist/index.js | wc -c)
echo "Gzipped before: ${BEFORE_GZ} bytes / after: ${AFTER_GZ} bytes"
```

---

## Step 7 — Wrangler Integration

If using Wrangler's built-in bundler but still want metafile output:

```bash
# Wrangler exposes the esbuild metafile via an undocumented flag (Wrangler 3.40+)
wrangler deploy --dry-run --outdir dist --metafile
# Outputs dist/index.js and dist/index.js.map + dist/metafile.json on supported versions

# For earlier Wrangler: use a custom build script and point wrangler.toml to it
```

```toml
# wrangler.toml — custom build command
[build]
command = "npx ts-node scripts/build.ts"
```

---

## Anti-patterns

- Running `esbuild.analyzeMetafile()` without `verbose: true` when debugging transitive deps — verbose mode shows the full import chain.
- Using `platform: "node"` for Workers bundles — Workers run a browser-like V8 environment; use `platform: "browser"` and polyfill carefully.
- Keeping `splitting: false` (default) when using dynamic imports — esbuild will inline the dynamic module, defeating the purpose.
- Adding packages to `external` without verifying the Workers runtime provides them — only `node:*` and `cloudflare:*` namespaces are available.
- Committing `dist/meta.json` — it contains full source paths and should be in `.gitignore`.

## Gotchas

- esbuild metafile `bytes` values are pre-minification; actual bundle size will be smaller after `minify: true`.
- Workers have a CPU time limit (10 ms on free, 30 s on paid); lazy-loading with `import()` can add latency on the first request if the chunk is large.
- `esbuild-visualizer` opens a browser tab by default — pass `--open false` in headless CI environments.
- Workers bundle size limits are measured on the compressed (gzip) bundle, not raw bytes — always check gzip size.

---

## Verification

```bash
# Build and analyse
npx ts-node scripts/build.ts

# Check gzip size against free-plan limit (1 MB compressed)
GZ_SIZE=$(gzip -c dist/index.js | wc -c)
echo "Compressed size: ${GZ_SIZE} bytes (limit: 1048576)"
[ "$GZ_SIZE" -lt 1048576 ] && echo "PASS" || echo "FAIL: exceeds 1 MB limit"

# Generate treemap
npx esbuild-visualizer --metadata dist/meta.json --filename dist/treemap.html
echo "Open dist/treemap.html in a browser to inspect module graph"
```

---

## Related

- `documentation/docs/policies/devtools/workers-source-map-upload-wrangler-debug.md`
- `documentation/docs/policies/devtools/workers-biome-linter-formatter-replace-eslint.md`

## Sources

- https://esbuild.github.io/api/#metafile
- https://esbuild.github.io/api/#analyze
- https://github.com/btd/esbuild-visualizer
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://developers.cloudflare.com/workers/wrangler/bundling/
