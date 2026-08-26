# Custom esbuild Plugins for Cloudflare Workers Builds

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The default Wrangler build pipeline covers most use-cases, but occasionally you need to: inject a git commit hash into the bundle at build time, strip 3 MB of locale data from a date library, replace a Node.js built-in (`path`, `crypto`) with a Worker-compatible polyfill, or validate that no `.node` native modules are accidentally referenced. Custom esbuild plugins make these transforms repeatable and auditable.

---

## Context

Wrangler uses esbuild internally. Since Wrangler 3 you can supply custom esbuild plugins via the `esbuild_plugins` array in `wrangler.toml`, or by calling esbuild directly in a custom build script and pointing Wrangler at the output with `main`. The esbuild plugin API exposes two hook namespaces:

- **`onResolve`** — intercepts module resolution; lets you redirect imports to a different path or mark them as external.
- **`onLoad`** — intercepts file loading; lets you synthesise or transform module source before it reaches esbuild's parser.

Plugins run in the Node.js process that drives the build, not inside the Worker runtime, so they have full access to the filesystem, `child_process`, and environment variables.

---

## Solution

```typescript
// build/plugins/inject-build-metadata.ts
// Replaces the virtual module `__BUILD_META__` with a JSON object
// containing the current git commit hash, build timestamp, and version.
import type { Plugin } from 'esbuild';
import { execSync } from 'child_process';
import * as fs from 'fs';

export function injectBuildMetadata(): Plugin {
  const gitHash = (() => {
    try {
      return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim();
    } catch {
      return 'unknown';
    }
  })();

  const version = (() => {
    try {
      return (JSON.parse(fs.readFileSync('package.json', 'utf8')) as { version: string }).version;
    } catch {
      return '0.0.0';
    }
  })();

  const meta = {
    gitHash,
    version,
    builtAt: new Date().toISOString(),
    env: process.env.ENVIRONMENT ?? 'development',
  };

  return {
    name: 'inject-build-metadata',
    setup(build) {
      build.onResolve({ filter: /^__BUILD_META__$/ }, (args) => ({
        path: args.path,
        namespace: 'build-meta',
      }));

      build.onLoad({ filter: /.*/, namespace: 'build-meta' }, () => ({
        contents: `export default ${JSON.stringify(meta, null, 2)} as const;`,
        loader: 'ts',
      }));
    },
  };
}
```

```typescript
// build/plugins/strip-locale-data.ts
// Tree-shakes heavy locale JSON from date-fns / @formatjs by redirecting
// locale imports that are not in the allow-list to an empty module.
import type { Plugin } from 'esbuild';

const ALLOWED_LOCALES = new Set(['en-US', 'en-GB', 'fr', 'de', 'es', 'ja']);

export function stripLocaleData(packageName: string = 'date-fns'): Plugin {
  return {
    name: 'strip-locale-data',
    setup(build) {
      // Match imports like: date-fns/locale/zh-CN or @formatjs/intl/locale-data/zh
      build.onResolve(
        { filter: new RegExp(`^${packageName}/locale/`) },
        (args) => {
          const localeName = args.path.split('/locale/')[1]?.replace('/', '-');
          if (localeName && ALLOWED_LOCALES.has(localeName)) {
            return null; // let esbuild resolve normally
          }
          return { path: args.path, namespace: 'empty-module' };
        },
      );

      build.onLoad({ filter: /.*/, namespace: 'empty-module' }, () => ({
        contents: 'export default {};',
        loader: 'js',
      }));
    },
  };
}
```

```typescript
// build/plugins/node-builtins-shim.ts
// Replaces Node.js built-ins with Worker-compatible alternatives.
// The Workers runtime supports a subset via nodejs_compat but some
// APIs need explicit polyfills or no-op stubs.
import type { Plugin } from 'esbuild';
import * as path from 'path';

/** Map Node built-in specifiers to shim file paths (relative to project root). */
const SHIMS: Record<string, string> = {
  'node:path': './build/shims/path.ts',
  path: './build/shims/path.ts',
  'node:os': './build/shims/os.ts',
  os: './build/shims/os.ts',
};

export function nodeBuiltinsShim(): Plugin {
  return {
    name: 'node-builtins-shim',
    setup(build) {
      for (const [specifier, shimPath] of Object.entries(SHIMS)) {
        const absoluteShim = path.resolve(process.cwd(), shimPath);
        build.onResolve({ filter: new RegExp(`^${specifier.replace(':', '\\:')}$`) }, () => ({
          path: absoluteShim,
        }));
      }
    },
  };
}
```

```typescript
// build/shims/path.ts — minimal path shim for Workers (POSIX only)
export const sep = '/';
export const delimiter = ':';

export function join(...parts: string[]): string {
  return parts
    .join('/')
    .replace(/\/+/g, '/')
    .replace(/\/$/, '') || '/';
}

export function dirname(p: string): string {
  return p.slice(0, p.lastIndexOf('/')) || '/';
}

export function basename(p: string, ext?: string): string {
  const base = p.slice(p.lastIndexOf('/') + 1);
  return ext && base.endsWith(ext) ? base.slice(0, -ext.length) : base;
}

export function extname(p: string): string {
  const i = p.lastIndexOf('.');
  return i > p.lastIndexOf('/') ? p.slice(i) : '';
}

export function resolve(...parts: string[]): string {
  // Workers have no CWD; resolve left-to-right, keep absolute segments
  let resolved = '';
  for (const part of parts.reverse()) {
    resolved = part.startsWith('/') ? join(part, resolved) : join('/', part, resolved);
    if (part.startsWith('/')) break;
  }
  return resolved || '/';
}

export function normalize(p: string): string {
  return p.replace(/\/+/g, '/').replace(/\/$/, '') || '/';
}

export default { sep, delimiter, join, dirname, basename, extname, resolve, normalize };
```

```typescript
// build/build.ts — custom build script wiring all plugins together
import * as esbuild from 'esbuild';
import { injectBuildMetadata } from './plugins/inject-build-metadata';
import { stripLocaleData } from './plugins/strip-locale-data';
import { nodeBuiltinsShim } from './plugins/node-builtins-shim';

async function build(): Promise<void> {
  const result = await esbuild.build({
    entryPoints: ['src/index.ts'],
    bundle: true,
    format: 'esm',
    target: 'es2022',
    outfile: 'dist/worker.js',
    // Cloudflare Workers globals — do not bundle them
    external: ['cloudflare:*', '__STATIC_CONTENT_MANIFEST'],
    // Minify in production
    minify: process.env.NODE_ENV === 'production',
    sourcemap: true,
    plugins: [
      injectBuildMetadata(),
      stripLocaleData('date-fns'),
      nodeBuiltinsShim(),
    ],
    metafile: true,
    logLevel: 'info',
  });

  // Print bundle analysis
  const analysis = await esbuild.analyzeMetafile(result.metafile!);
  console.log(analysis);

  // Fail if bundle exceeds Workers 1 MB (compressed) size limit
  const stat = await import('fs').then((fs) => fs.promises.stat('dist/worker.js'));
  const sizeKb = stat.size / 1024;
  console.log(`Bundle size: ${sizeKb.toFixed(1)} KB`);
  if (sizeKb > 900) {
    console.warn('WARNING: bundle approaching 1 MB Workers limit');
  }
}

build().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

```typescript
// src/index.ts — consuming the injected build metadata virtual module
import BUILD_META from '__BUILD_META__';

export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/_meta') {
      return Response.json(BUILD_META);
    }

    return new Response('hello', {
      headers: { 'X-Build': BUILD_META.gitHash },
    });
  },
} satisfies ExportedHandler<Env>;
```

```json
// package.json — build scripts
{
  "scripts": {
    "build": "tsx build/build.ts",
    "build:prod": "NODE_ENV=production ENVIRONMENT=production tsx build/build.ts",
    "dev": "wrangler dev"
  }
}
```

---

## Implementation Details

- **`onResolve` return `null`** means "I'm not handling this, pass to next resolver". An object with `path` (and optionally `namespace`) claims the import.
- **`namespace`** is an arbitrary string grouping virtual modules. Using a custom namespace (e.g. `build-meta`) prevents the `onLoad` hook from accidentally matching real files.
- **`loader: 'ts'`** in `onLoad` tells esbuild to parse the generated content as TypeScript, enabling type stripping if needed.
- **`external: ['cloudflare:*']`** prevents esbuild from trying to bundle Cloudflare-specific specifiers (`cloudflare:sockets`, `cloudflare:email`) which are resolved at runtime by the Workers runtime.
- Plugins run **sequentially** in declaration order. Order matters when two plugins target the same import specifier.

---

## Anti-patterns

- **Running `fs.readFileSync` inside `onLoad` on every call** — cache static data (git hash, package.json) outside the `setup` closure so it is read once per build.
- **Using `require()` inside a plugin** — esbuild plugins run in ESM context when using `tsx`/`ts-node` with `"type": "module"`. Use `import()` or top-level `await import()`.
- **Forgetting to mark Cloudflare specifiers as external** — bundling `cloudflare:sockets` will fail because esbuild cannot resolve the package. Always add `external: ['cloudflare:*']`.
- **Overriding Wrangler's internal plugins** — if using `wrangler.toml`'s `esbuild_plugins`, your plugins run in addition to Wrangler's built-in ones. Do not replicate what Wrangler already does (module rules, `__STATIC_CONTENT_MANIFEST` injection).

---

## Gotchas

- The `metafile: true` option in esbuild can emit a large JSON object for complex bundles. Pipe `esbuild.analyzeMetafile` output through a pager (`| less`) or write it to a file.
- `execSync` inside a plugin will fail in sandboxed CI environments that block subprocesses. Provide a fallback (`'unknown'`) as shown above.
- `stripLocaleData` depends on the locale import path convention of the specific library. Verify the path pattern matches the library's actual exports before shipping.

---

## Verification

```bash
# Build and inspect bundle
npm run build
ls -lh dist/worker.js

# Confirm build metadata is injected
grep -o '"gitHash":"[^"]*"' dist/worker.js

# Confirm stripped locales are absent
grep -c 'zh-CN\|zh-TW\|ko' dist/worker.js || echo 'Locales successfully stripped'

# Test metadata endpoint via wrangler dev
wrangler dev --local & sleep 3 && curl http://localhost:8787/_meta
```

---

## Related

- `documentation/docs/policies/devtools/bundle-size-analysis.md`
- `documentation/docs/policies/devtools/wrangler-custom-builds.md`
- `documentation/docs/policies/devtools/sourcemap-debugging.md`

---

## Sources

- https://esbuild.github.io/plugins/
- https://developers.cloudflare.com/workers/wrangler/custom-builds/
- https://esbuild.github.io/api/#metafile
