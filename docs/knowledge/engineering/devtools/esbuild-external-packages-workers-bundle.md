# esbuild External Packages Workers Bundle Optimization

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Workers bundle exceeds the 3 MB compressed limit (or the 10 MB uncompressed script limit) because esbuild is bundling large Node.js-polyfill packages, SDK clients, or shared internal packages that should either be excluded or replaced with Workers-native equivalents. You need to control what esbuild marks as external, use `alias` to swap packages for lean alternatives, and verify the final bundle does not include dead weight.

## Context

Wrangler uses esbuild under the hood to bundle Workers. The bundling pipeline is configurable via `wrangler.toml`'s `[build]` section or a custom `esbuild.config.ts`. Marking packages as `external` tells esbuild to emit an `import` or `require` for them instead of inlining their code, which only makes sense for packages available in the Workers runtime (e.g. `cloudflare:*` and Node.js compatibility modules). For everything else, the goal is to tree-shake aggressively or swap heavy packages for lighter alternatives.

Workers support `nodejs_compat` and `nodejs_compat_v2` compatibility flags, which make certain Node.js built-ins available without bundling polyfills. Marking Node built-ins as external when these flags are active is the primary use of `external` in Workers bundles.

---

## Marking Node Built-ins as External

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]
```

```typescript
// Wrangler automatically treats node:* imports as external
// when nodejs_compat is enabled. You can confirm this by reading
// the Wrangler output during build:
// "[mf:inf] Bundling... external: node:crypto, node:buffer, ..."

import { createHash } from "node:crypto";   // NOT bundled — runtime provides it
import { Buffer } from "node:buffer";        // NOT bundled

export default {
  async fetch(request: Request): Promise<Response> {
    const hash = createHash("sha256")
      .update(await request.text())
      .digest("hex");
    return new Response(hash);
  },
};
```

When `nodejs_compat` is active, Wrangler's esbuild pipeline adds all `node:*` specifiers to its `external` array automatically. You do not need to configure this manually.

---

## Custom esbuild Config via wrangler.toml

```toml
# wrangler.toml
[build]
command = "pnpm build:worker"

[build.upload]
format = "modules"
main = "dist/index.mjs"
```

```typescript
// scripts/build-worker.ts
import * as esbuild from "esbuild";

await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  platform: "browser",    // Workers use browser platform target
  target: "es2022",
  outfile: "dist/index.mjs",
  external: [
    // Packages provided by the Workers runtime — never bundle these
    "cloudflare:*",
    "__STATIC_CONTENT_MANIFEST",
  ],
  alias: {
    // Replace heavy SDK with a lean Workers-native fetch wrapper
    "@aws-sdk/client-s3": "./src/shims/r2-s3-shim.ts",
    // Replace Node crypto with Workers SubtleCrypto wrapper
    "crypto": "./src/shims/crypto-shim.ts",
  },
  minify: true,
  treeShaking: true,
  metafile: true,
});
```

The `platform: "browser"` setting prevents esbuild from including Node-specific shims for `process`, `Buffer`, and `__dirname` that would otherwise be injected.

---

## Alias: Replacing Heavy Packages with Shims

```typescript
// src/shims/r2-s3-shim.ts
// Minimal replacement for @aws-sdk/client-s3 when using R2
export class S3Client {
  constructor(private config: { endpoint: string; region: string }) {}

  async send(command: GetObjectCommand): Promise<{ Body: ReadableStream }> {
    const url = `${this.config.endpoint}/${command.input.Bucket}/${command.input.Key}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`R2 fetch failed: ${res.status}`);
    return { Body: res.body as ReadableStream };
  }
}

export class GetObjectCommand {
  constructor(public readonly input: { Bucket: string; Key: string }) {}
}
```

The `alias` map intercepts every `import` from `@aws-sdk/client-s3` across the entire bundle and points it at the shim. The full AWS SDK (≈400 KB gzipped) is replaced by a few hundred bytes.

---

## Analysing the Metafile to Find Bundle Bloat

```typescript
// scripts/build-worker.ts (continued)
import { writeFileSync } from "node:fs";

const result = await esbuild.build({ ...options, metafile: true });

// Write metafile for analysis
writeFileSync("dist/meta.json", JSON.stringify(result.metafile));

// Print top 10 largest inputs
const inputs = Object.entries(result.metafile!.inputs)
  .sort(([, a], [, b]) => b.bytes - a.bytes)
  .slice(0, 10);

console.log("\nTop 10 largest bundle inputs:");
inputs.forEach(([path, { bytes }]) => {
  console.log(`  ${(bytes / 1024).toFixed(1)} KB  ${path}`);
});
```

```bash
# Alternatively, use esbuild's online analyser
open https://esbuild.github.io/analyze/
# Drag dist/meta.json into the page
```

The metafile maps every input file to its compressed byte contribution. Use it to identify unexpectedly large transitive dependencies before they ship to production.

---

## Tree-shaking SDK Clients with Barrel Exports

```typescript
// BAD: imports the entire client package including all command classes
import * as S3 from "@aws-sdk/client-s3";

// GOOD: import only what is used; esbuild can tree-shake named imports
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
```

For packages that use barrel `index.ts` files re-exporting everything, tree-shaking depends on the package having `"sideEffects": false` in its `package.json`. Without it, esbuild conservatively includes all re-exported modules. Check with:

```bash
cat node_modules/@aws-sdk/client-s3/package.json | grep sideEffects
```

If `sideEffects` is missing or `true`, the only option is aliasing to a shim or using a purpose-built Workers SDK like `aws4fetch`.

---

## Anti-patterns

- **Marking npm packages as `external` unless they are runtime-provided** — if a package is in `external` and not available in the Workers runtime, the Worker will throw `Cannot find module 'X'` at runtime.
- **Using `platform: "node"` for Workers** — this injects heavy Node polyfills (`process`, `Buffer`, etc.) that are either unnecessary with `nodejs_compat` or actively harmful.
- **Depending on `__dirname` or `__filename`** — these do not exist in Workers ESM modules; esbuild injects stubs with `platform: "browser"` but they return empty strings.
- **Not setting `treeShaking: true` explicitly** — esbuild tree-shakes by default only with `bundle: true` and `format: "esm"`; mixed CJS/ESM packages may bypass tree-shaking silently.

---

## Gotchas

- `cloudflare:*` specifiers (e.g. `cloudflare:email`) must be in `external`; esbuild does not know about them and will error if they appear in source without being externalized.
- `alias` in esbuild resolves before `external`. If a package appears in both, `alias` wins and the replacement is bundled.
- Wrangler's built-in esbuild invocation does not expose all esbuild options. Complex aliasing or custom plugins require a custom build script with `[build] command`.
- The Workers compressed script size limit (3 MB) applies to the gzipped Worker bundle. Run `gzip -c dist/index.mjs | wc -c` locally to verify before deploying.
- `esbuild.build()` does not emit a `*.d.ts` for the output; if the Worker is also a library (imported by other packages), use `tsc --declaration` separately.

---

## Verification

```bash
# Check uncompressed bundle size
ls -lh dist/index.mjs

# Check gzipped size (must be < 3 MB)
gzip -c dist/index.mjs | wc -c

# Confirm no unexpected node_modules in the bundle
cat dist/meta.json | node -e "
  const meta = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));
  const externals = Object.entries(meta.inputs)
    .filter(([p]) => p.includes('node_modules'))
    .map(([p, {bytes}]) => p + ' ' + bytes);
  console.log(externals.join('\n'));
"

# Dry-run deploy to validate bundle
pnpm wrangler deploy --dry-run --outdir dist/dry
```

---

## Related

- `esbuild-metafile-bundle-analysis-workers.md` — deep-dive metafile analysis workflow
- `esbuild-workers-plugins-custom-transforms.md` — custom esbuild plugins for Workers
- `wrangler-config-validation-ci.md` — validating wrangler.toml in CI
- `bundle-size-tracking-size-limit-ci.md` — CI gates on bundle size regressions

---

## Sources

- https://esbuild.github.io/api/#external
- https://esbuild.github.io/api/#alias
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://developers.cloudflare.com/workers/platform/limits/#script-size
