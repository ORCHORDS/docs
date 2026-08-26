# esbuild Metafile Bundle Analysis for Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your Cloudflare Worker bundle is unexpectedly large (approaching the 3 MB compressed script limit) and you need to identify which modules are responsible without deploying or guessing.

## Context
esbuild's `--metafile` flag (or `metafile: true` in the JS API) produces a JSON file describing every module in the bundle — sizes before and after tree-shaking, import chains, and which entry point pulled each file in. Analyzing this file with `esbuild.analyzeMetafile()` or the web visualizer at `bundle-buddy.com`/`esbuild.github.io/analyze/` pinpoints large dependencies and dead-code candidates. Wrangler uses esbuild internally; you can replicate the build with the same settings to capture the metafile.

## Generating a Metafile via the esbuild JS API

Rather than relying on Wrangler's opaque internal build, write a standalone build script:

```typescript
// scripts/analyze-bundle.ts
import * as esbuild from "esbuild";
import { writeFileSync } from "node:fs";

const result = await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  target: "es2022",
  platform: "browser",   // Workers run in a browser-like env, not Node.js
  conditions: ["workerd", "worker", "browser"],
  external: ["cloudflare:*", "__STATIC_CONTENT_MANIFEST"],
  metafile: true,         // Enable metafile output
  write: false,           // Don't write the bundle; we only want the metafile
  minify: false,          // Keep readable names for analysis
  outfile: "dist/index.js",
});

if (!result.metafile) {
  throw new Error("No metafile produced");
}

// Write the metafile for offline analysis
writeFileSync("dist/meta.json", JSON.stringify(result.metafile, null, 2));

// Print a human-readable summary to stdout
const text = await esbuild.analyzeMetafile(result.metafile, {
  verbose: false,  // Set true to show full import chains
});
console.log(text);
```

```json
// package.json (add a script)
{
  "scripts": {
    "analyze": "tsx scripts/analyze-bundle.ts"
  }
}
```

## Parsing the Metafile Programmatically

Extract the top-10 largest modules as a CI-friendly report:

```typescript
// scripts/check-bundle-size.ts
import * as esbuild from "esbuild";
import { readFileSync } from "node:fs";

interface MetafileInput {
 bytes: number; imports: Array<{ path: string }> };
}

const metafile: esbuild.Metafile = JSON.parse(
  readFileSync("dist/meta.json", "utf8")
);

const inputs = metafile.inputs as MetafileInput;

const modules = Object.entries(inputs)
  .map(([path, info]) => ({ path, bytes: info.bytes }))
  .sort((a, b) => b.bytes - a.bytes)
  .slice(0, 10);

console.log("Top 10 largest modules:");
for (const mod of modules) {
  const kb = (mod.bytes / 1024).toFixed(1);
  console.log(`  ${kb.padStart(8)} KB  ${mod.path}`);
}

// Fail CI if any single dependency exceeds a threshold
const MAX_MODULE_SIZE_BYTES = 200 * 1024; // 200 KB
const oversized = Object.entries(inputs).filter(
  ([, info]) => info.bytes > MAX_MODULE_SIZE_BYTES
);

if (oversized.length > 0) {
  console.error("\nOversized modules (exceed 200 KB each):");
  for (const [path, info] of oversized) {
    console.error(`  ${path}: ${(info.bytes / 1024).toFixed(1)} KB`);
  }
  process.exit(1);
}
```

## Tracking Total Bundle Size in CI

Check the final output size against Cloudflare's 3 MB compressed script limit:

```typescript
// scripts/assert-bundle-size.ts
import * as esbuild from "esbuild";
import { gzipSync } from "node:zlib";
import { readFileSync } from "node:fs";

const result = await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  target: "es2022",
  platform: "browser",
  conditions: ["workerd", "worker", "browser"],
  external: ["cloudflare:*"],
  minify: true,
  write: false,
  outfile: "dist/index.js",
});

const output = result.outputFiles?.[0];
if (!output) throw new Error("No output produced");

const raw = output.contents;
const compressed = gzipSync(raw);

const rawKB = (raw.byteLength / 1024).toFixed(1);
const gzKB = (compressed.byteLength / 1024).toFixed(1);

console.log(`Bundle size: ${rawKB} KB raw / ${gzKB} KB gzipped`);

const MAX_GZ = 3 * 1024 * 1024; // 3 MB compressed limit
if (compressed.byteLength > MAX_GZ) {
  console.error("ERROR: Bundle exceeds 3 MB compressed Cloudflare Workers limit");
  process.exit(1);
}
```

## Identifying Duplicate Dependencies

The same package bundled multiple times (e.g. two versions of `zod`) will appear as distinct paths:

```typescript
// scripts/find-duplicates.ts
import { readFileSync } from "node:fs";
import type { Metafile } from "esbuild";

const metafile: Metafile = JSON.parse(readFileSync("dist/meta.json", "utf8"));

// Extract package names from node_modules paths
const packageCounts = new Map<string, string[]>();

for (const path of Object.keys(metafile.inputs)) {
  const match = path.match(/node_modules\/(@[^/]+\/[^/]+|[^/]+)/);
  if (match) {
    const pkg = match[1];
    const paths = packageCounts.get(pkg) ?? [];
    paths.push(path);
    packageCounts.set(pkg, paths);
  }
}

const duplicates = [...packageCounts.entries()].filter(
  ([, paths]) => new Set(paths.map((p) => p.split(pkg => pkg))).size > 1
);

if (duplicates.length) {
  console.warn("Potential duplicate packages in bundle:");
  for (const [pkg] of duplicates) {
    console.warn(`  ${pkg}`);
  }
}
```

## Integrating with GitHub Actions

```yaml
# .github/workflows/bundle-check.yml
name: Bundle Size Check
on: [pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile

      - name: Build and check bundle size
        run: pnpm tsx scripts/assert-bundle-size.ts

      - name: Generate metafile and check modules
        run: |
          pnpm tsx scripts/analyze-bundle.ts
          pnpm tsx scripts/check-bundle-size.ts

      - name: Upload metafile artifact
        uses: actions/upload-artifact@v4
        with:
          name: bundle-metafile
          path: dist/meta.json
          retention-days: 7
```

## Anti-patterns
- Running analysis only after noticing production slowness; add size assertions to CI from the start.
- Using `minify: true` during analysis; minified names make it harder to identify which library owns large modules.
- Treating raw bytes as the budget; Cloudflare enforces compressed size — always gzip the output before comparing.
- Ignoring import chains; a small entry file can pull in megabytes of transitive deps that appear small individually.
- Not pinning the `conditions` array to `["workerd", "worker", "browser"]`; wrong conditions may resolve the wrong package entry point and give misleading size figures.

## Gotchas
- Wrangler's internal esbuild invocation may differ from a manual one (extra plugins, different conditions); the metafile from your script is an approximation, not Wrangler's exact output — use `wrangler build` and inspect its output for the authoritative size.
- `esbuild.analyzeMetafile()` is async but does not hit the network; it's CPU-only and safe to run in CI without credentials.
- The metafile `inputs` sizes are pre-minification; actual bundle contributions after dead-code elimination will be smaller — don't raise alarms solely on input sizes.
- Source maps add significantly to raw bytes but Cloudflare strips them at upload for the script size budget; don't include source maps when measuring bundle size for the limit.
- Packages using `"exports"` with multiple conditions (e.g. CJS + ESM) may appear differently in the metafile depending on resolution order; set `mainFields: ["module", "main"]` consistently.

## Verification
```bash
pnpm tsx scripts/analyze-bundle.ts
# Output: table of modules sorted by size

pnpm tsx scripts/assert-bundle-size.ts
# Exit 0 = within limits; exit 1 = over limit with details
```

## Related
- `/documentation/categories/devtools/esbuild-workers-plugins-custom-transforms.md`
- `/documentation/categories/devtools/bundle-size-tracking-size-limit-ci.md`
- `/documentation/categories/devtools/knip-dead-code-detection-workers-monorepo.md`
- `/documentation/categories/devtools/typescript-cloudflare-workers-strict.md`

## Sources
- https://esbuild.github.io/api/#metafile
- https://esbuild.github.io/analyze/
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://github.com/nicolo-ribaudo/bundle-buddy
