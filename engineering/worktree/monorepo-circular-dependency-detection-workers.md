# Monorepo Circular Dependency Detection for Cloudflare Workers Packages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers monorepo grows to fifteen packages. One day a build silently produces a bundle that crashes on startup with `RangeError: Maximum call stack size exceeded` or a more cryptic Webpack/esbuild cycle error. You trace it back to a circular import: `@repo/auth` imports `@repo/core`, which imports `@repo/utils`, which re-exports a helper from `@repo/auth`. The cycle existed for weeks unnoticed because both local dev and `wrangler dev` tolerated it, but esbuild's tree-shaking broke when it tried to produce a single-file Worker bundle.

The goal is to catch circular dependencies at the earliest possible moment — in a pre-commit hook, in CI before bundling, and in the package boundary lint step — so they never reach a `wrangler deploy`.

---

## Context

Circular dependencies in JavaScript/TypeScript monorepos are insidious because:
- Node.js (CommonJS) resolves them at runtime by returning partially-initialised module objects, masking the cycle.
- ESM in Node and in Workers runtimes raises an error only when a value needed at initialisation time is `undefined` due to the cycle, not when the import itself occurs.
- Bundlers like esbuild and Rollup attempt to flatten the module graph; a cycle forces them into an arbitrary linearisation order that can silently produce incorrect output.

In a pnpm workspace the dependency graph is declared in each package's `package.json` `dependencies` field. A cycle at the **package level** (A depends on B depends on A in `package.json`) is impossible to install — pnpm rejects it. But a cycle at the **source level** (A's TypeScript files import from B while B's files import from A, both listed as separate packages) is perfectly installable and is what causes runtime and bundler failures.

Tools:

| Tool | What it checks | Integration point |
|---|---|---|
| `madge` | Source-level import cycles, supports TypeScript via ts-node | CLI, CI |
| `eslint-plugin-import` `import/no-cycle` | Per-file cycle detection with depth limit | ESLint, pre-commit |
| `@monorepo-utils/check-graph` | Package-level graph cycles | CI script |
| Turborepo `--graph` output | Topological order, exposes if a task graph is cyclic | CI diagnostic |

---

## Installing Detection Tooling

```bash
# in the monorepo root
pnpm add -D madge @typescript-eslint/parser eslint-plugin-import -w

# optional: faster TypeScript-aware scanning
pnpm add -D ts-node -w
```

---

## ESLint Rule: import/no-cycle

Add to the root ESLint config (flat config style):

```typescript
// eslint.config.ts
import importPlugin from "eslint-plugin-import";
import tsParser from "@typescript-eslint/parser";

export default [
  {
    files: ["packages/*/src/**/*.ts"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: "./tsconfig.json",
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { import: importPlugin },
    settings: {
      "import/resolver": {
        typescript: {
          alwaysTryTypes: true,
          project: "./tsconfig.json",
        },
      },
    },
    rules: {
      // maxDepth: Infinity checks all transitive cycles, not just direct ones
      "import/no-cycle": ["error", { maxDepth: Infinity, ignoreExternal: true }],
    },
  },
];
```

This rule fires during `eslint` and therefore during any lint-staged or Lefthook pre-commit step.

---

## Madge: Full Graph Cycle Report

```typescript
// scripts/check-cycles.ts
import madge from "madge";
import path from "node:path";
import { execSync } from "node:child_process";

const PACKAGES_DIR = path.resolve(import.meta.dirname, "../packages");

// Enumerate all source entry points via pnpm workspace
const packages = execSync("pnpm ls --recursive --json", { encoding: "utf-8" });
const pkgList: Array<{ path: string; name: string }> = JSON.parse(packages);

let hasErrors = false;

for (const pkg of pkgList) {
  const srcDir = path.join(pkg.path, "src");
  const result = await madge(srcDir, {
    fileExtensions: ["ts", "tsx"],
    tsConfig: path.join(pkg.path, "tsconfig.json"),
    detectiveOptions: {
      ts: { mixedImports: true },
    },
  });

  const cycles = result.circular();

  if (cycles.length > 0) {
    console.error(`\n❌ Circular dependencies found in ${pkg.name}:`);
    for (const cycle of cycles) {
      console.error("  " + cycle.join(" → ") + " → " + cycle[0]);
    }
    hasErrors = true;
  } else {
    console.log(`✅ ${pkg.name}: no cycles`);
  }
}

if (hasErrors) {
  process.exit(1);
}
```

Run it:

```bash
npx tsx scripts/check-cycles.ts
```

---

## Integrating into Turborepo Pipeline

```json
// turbo.json (excerpt)
{
  "tasks": {
    "check:cycles": {
      "cache": false,
      "inputs": ["src/**/*.ts", "package.json", "tsconfig.json"],
      "outputs": []
    },
    "build": {
      "dependsOn": ["check:cycles", "^build"],
      "outputs": ["dist/**"]
    }
  }
}
```

Each package adds the task to its `package.json`:

```json
{
  "scripts": {
    "check:cycles": "madge --circular --extensions ts src/"
  }
}
```

Turborepo runs `check:cycles` for every affected package before allowing `build` to proceed. Since `build` feeds `wrangler deploy`, cycles are caught before bundling.

---

## Pre-commit Hook via Lefthook

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  commands:
    lint:
      glob: "packages/*/src/**/*.{ts,tsx}"
      run: pnpm eslint {staged_files} --rule 'import/no-cycle: error' --max-warnings 0
    cycles:
      glob: "packages/*/src/**/*.ts"
      # run full madge scan only when package sources change
      run: npx tsx scripts/check-cycles.ts
      root: "."
```

---

## CI Gate: GitHub Actions Step

```yaml
# .github/workflows/ci.yml (excerpt)
jobs:
  cycle-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Check circular dependencies
        run: npx tsx scripts/check-cycles.ts
      - name: Upload madge graph (on failure)
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: dependency-graph
          path: /tmp/dep-graph.svg

  build:
    needs: cycle-check
    # ... wrangler deploy steps
```

Generating the SVG graph for the failure artifact:

```bash
# add to check-cycles.ts when a cycle is detected:
const svg = await result.svg();
await fs.writeFile("/tmp/dep-graph.svg", svg);
```

---

## Workers-Specific Concern: Service Binding Cycles

Beyond source-level import cycles, Workers service bindings can form runtime dependency cycles:

- Worker A binds to Worker B (`services = [{ binding = "B", service = "worker-b" }]`)
- Worker B binds back to Worker A

Cloudflare currently allows deploying such a configuration but the request chain deadlocks at runtime. Detect it by extracting the service binding graph from all `wrangler.toml` files:

```typescript
// scripts/check-binding-cycles.ts
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import TOML from "@iarna/toml";

interface WranglerToml {
  name?: string;
  services?: Array<{ binding: string; service: string }>;
}

const packagesDir = "./packages";
const graph = new Map<string, string[]>(); // worker name -> [depends on]

for (const pkg of readdirSync(packagesDir)) {
  const tomlPath = join(packagesDir, pkg, "wrangler.toml");
  try {
    const raw = readFileSync(tomlPath, "utf-8");
    const config = TOML.parse(raw) as WranglerToml;
    if (config.name && config.services) {
      graph.set(
        config.name,
        config.services.map((s) => s.service)
      );
    }
  } catch {
    // no wrangler.toml in this package
  }
}

// DFS cycle detection
function hasCycle(
  node: string,
  visited: Set<string>,
  stack: Set<string>
): string[] | null {
  visited.add(node);
  stack.add(node);
  for (const neighbour of graph.get(node) ?? []) {
    if (!visited.has(neighbour)) {
      const cycle = hasCycle(neighbour, visited, stack);
      if (cycle) return [node, ...cycle];
    } else if (stack.has(neighbour)) {
      return [node, neighbour];
    }
  }
  stack.delete(node);
  return null;
}

let found = false;
for (const node of graph.keys()) {
  const cycle = hasCycle(node, new Set(), new Set());
  if (cycle) {
    console.error("Service binding cycle:", cycle.join(" → "));
    found = true;
  }
}
if (found) process.exit(1);
else console.log("No service binding cycles detected.");
```

---

## Anti-patterns

- **Suppressing `import/no-cycle` with an eslint-disable comment** — This is almost always wrong. The correct fix is to extract the shared type or utility into a third package that neither A nor B depends on circularly.
- **Running `madge` only on the entrypoint file** — Cycles often involve files that are not reachable from the public entrypoint but are reachable from test utilities. Scan the entire `src/` tree.
- **Ignoring cycles in `devDependencies`** — Build-time tools imported via `devDependencies` can still form cycles that break the TypeScript compiler's module resolution order.
- **Treating cycle detection as a one-time cleanup** — Cycles re-appear as code grows. Keep the gate in CI permanently.

---

## Gotchas

- `madge` uses static import analysis. Dynamic `import()` calls are not always traced. Add a comment to document intentional dynamic imports that break potential cycles.
- `eslint-plugin-import` with `maxDepth: Infinity` can be slow on large monorepos. Cache ESLint results with `ESLINT_USE_FLAT_CONFIG=true eslint --cache`.
- Re-exporting via barrel files (`index.ts`) is a common cycle amplifier. A barrel that re-exports from every sibling package will form a cycle with any package that imports the barrel. Prefer explicit imports.
- TypeScript `type`-only imports (`import type { Foo } from "..."`) are erased at compile time. They cannot cause runtime cycles, but they can still confuse `madge`. Use the `--ts-config` flag to let madge resolve them correctly.

---

## Verification

```bash
# Quick check: does madge find any cycle in the entire monorepo src tree?
find packages -name "src" -type d | xargs -I{} madge --circular --extensions ts {}

# Confirm Turborepo build order does not contain a cycle
pnpm turbo run build --dry=json | jq '.tasks[] | {task: .taskId, deps: .dependencies}'

# Confirm service binding graph is acyclic
npx tsx scripts/check-binding-cycles.ts
```

---

## Related

- `monorepo-package-boundary-enforcement-workers.md`
- `monorepo-wrangler-service-bindings-topology.md`
- `monorepo-deploy-order-workers-service-bindings.md`
- `turborepo-task-graph-visualization-debugging.md`
- `git-hooks-lefthook-monorepo.md`
- `typescript-path-aliases-monorepo-workers-build.md`

---

## Sources

- [madge — npm](https://www.npmjs.com/package/madge)
- [eslint-plugin-import: import/no-cycle](https://github.com/import-js/eslint-plugin-import/blob/main/docs/rules/no-cycle.md)
- [Cloudflare Docs — Service bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/)
- [Turborepo — Task dependencies](https://turbo.build/repo/docs/core-concepts/monorepos/task-dependencies)
