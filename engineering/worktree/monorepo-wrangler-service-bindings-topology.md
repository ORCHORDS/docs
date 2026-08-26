# Monorepo Wrangler Service Bindings Topology Documentation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

As the example project monorepo grows to five or more Cloudflare Workers, engineers lose track of which Worker calls which other Worker via Service Bindings. A new Developer joining the project cannot determine the call graph without reading every `wrangler.jsonc`. Accidental circular binding introductions cause silent runtime panics in production. The goal is a living topology document generated from `wrangler.jsonc` files and enforced in CI.

---

## Context

Cloudflare Service Bindings (`[[services]]` in `wrangler.jsonc`) allow one Worker to call another synchronously over an internal network with zero latency. In a monorepo each Worker has its own `wrangler.jsonc`; the binding graph is implicitly encoded across those files. Without tooling to extract and visualise this graph, it degrades silently — deleted Workers leave dangling binding references, renamed Workers break binding names without a compile-time error, and circular dependencies appear undetected until production deploy.

---

## Wrangler Config Structure for Service Bindings

A Worker that calls two downstream Workers declares:

```jsonc
// apps/workers/api-gateway/wrangler.jsonc
{
  "name": "example project-api-gateway",
  "main": "src/index.ts",
  "compatibility_date": "2026-08-01",
  "services": [
    {
      "binding": "AUTH_WORKER",
      "service": "example project-auth",
      "entrypoint": "default"
    },
    {
      "binding": "PAYMENTS_WORKER",
      "service": "example project-payments",
      "entrypoint": "default"
    }
  ]
}
```

The `service` field must exactly match the `name` field of the target Worker's `wrangler.jsonc`.

---

## Topology Extraction Script

Parse all `wrangler.jsonc` files in the monorepo and emit a topology map:

```typescript
// tools/service-binding-topology/src/extract.ts
import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { parse as parseJsonc } from "jsonc-parser";
import { globSync } from "glob";

interface Binding {
  binding: string;
  service: string;
  entrypoint?: string;
}

interface WorkerTopology {
  name: string;
  configPath: string;
  calls: Binding[];
}

export function extractTopology(monorepoRoot: string): WorkerTopology[] {
  const configs = globSync("apps/workers/*/wrangler.jsonc", {
    cwd: monorepoRoot,
    absolute: true,
  });

  return configs.map((configPath) => {
    const raw = readFileSync(configPath, "utf8");
    const config = parseJsonc(raw) as {
      name: string;
      services?: Binding[];
    };

    return {
      name: config.name,
      configPath,
      calls: config.services ?? [],
    };
  });
}

export function detectCircularDependencies(
  topology: WorkerTopology[]
): string[][] {
  const graph = new Map<string, string[]>(
    topology.map((w) => [w.name, w.calls.map((c) => c.service)])
  );

  const cycles: string[][] = [];

  function dfs(node: string, path: string[], visited: Set<string>): void {
    if (visited.has(node)) {
      const cycleStart = path.indexOf(node);
      if (cycleStart !== -1) cycles.push(path.slice(cycleStart).concat(node));
      return;
    }
    visited.add(node);
    for (const neighbor of graph.get(node) ?? []) {
      dfs(neighbor, [...path, node], new Set(visited));
    }
  }

  for (const worker of topology) dfs(worker.name, [], new Set());
  return cycles;
}
```

---

## Mermaid Graph Generation

Generate a Mermaid diagram from the extracted topology for inclusion in the team wiki or as a CI artifact:

```typescript
// tools/service-binding-topology/src/render.ts
import type { WorkerTopology } from "./extract.js";

export function renderMermaid(topology: WorkerTopology[]): string {
  const lines: string[] = ["graph LR"];

  for (const worker of topology) {
    const label = worker.name.replace("example project-", "");
    lines.push(`  ${sanitize(worker.name)}["${label}"]`);

    for (const binding of worker.calls) {
      const targetLabel = binding.service.replace("example project-", "");
      lines.push(
        `  ${sanitize(worker.name)} -->|"${binding.binding}"| ${sanitize(binding.service)}["${targetLabel}"]`
      );
    }
  }

  return lines.join("\n");
}

function sanitize(name: string): string {
  return name.replace(/-/g, "_");
}
```

Run and write to a docs file:

```bash
pnpm tsx tools/service-binding-topology/src/index.ts \
  --root . \
  --output docs/service-bindings-topology.md
```

---

## CI Validation Gate

Enforce that every `service` reference resolves to a real Worker name, and that no circular dependencies exist:

```yaml
# .github/workflows/validate-service-bindings.yml
name: Validate Service Binding Topology

on:
  pull_request:
    paths:
      - "apps/workers/**/wrangler.jsonc"
      - "tools/service-binding-topology/**"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Validate topology and detect cycles
        run: pnpm tsx tools/service-binding-topology/src/validate.ts --fail-on-cycle --fail-on-dangling

      - name: Upload topology diagram
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: service-bindings-topology
          path: docs/service-bindings-topology.md
```

The `validate.ts` entrypoint exits with code 1 when a cycle or dangling reference is detected, blocking the merge.

---

## Dangling Reference Detection

```typescript
// tools/service-binding-topology/src/validate.ts
import { extractTopology, detectCircularDependencies } from "./extract.js";
import { resolve } from "node:path";

const root = process.cwd();
const topology = extractTopology(root);
const knownNames = new Set(topology.map((w) => w.name));

let exitCode = 0;

// Dangling references
for (const worker of topology) {
  for (const binding of worker.calls) {
    if (!knownNames.has(binding.service)) {
      console.error(
        `ERROR: ${worker.name} binds to "${binding.service}" which does not exist`
      );
      exitCode = 1;
    }
  }
}

// Circular dependencies
const cycles = detectCircularDependencies(topology);
for (const cycle of cycles) {
  console.error(`ERROR: Circular binding detected: ${cycle.join(" -> ")}`);
  exitCode = 1;
}

if (exitCode === 0) console.log("OK: Service binding topology is valid.");
process.exit(exitCode);
```

---

## Wrangler Local Dev: Binding Stub Configuration

For local `wrangler dev` runs, each Worker needs to resolve bindings to a locally running peer. Use Wrangler's `dev.vars` and service binding override in `wrangler.jsonc`:

```jsonc
// apps/workers/api-gateway/wrangler.jsonc (dev overrides)
{
  "name": "example project-api-gateway",
  "services": [
    {
      "binding": "AUTH_WORKER",
      "service": "example project-auth"
    }
  ],
  "dev": {
    "port": 8787,
    "upstream_protocol": "http"
  }
}
```

Run peers in separate terminals (or use `wrangler dev --port` per Worker), then Wrangler's service binding resolution picks up localhost peers automatically in local mode.

---

## Anti-patterns

- **Hardcoding Worker URLs as environment variables instead of using Service Bindings** — this bypasses Cloudflare's zero-latency internal network and introduces TLS overhead and external egress costs.
- **Using the same binding name for different services across environments** — `wrangler.jsonc` environment overrides for `[env.staging]` should explicitly redeclare all `services` to avoid accidentally pointing staging at production Workers.
- **Not validating topology in CI** — renamed Workers break binding references silently; the runtime error only surfaces at deploy time (or worse, at runtime in production).
- **Circular bindings** — Worker A calling Worker B calling Worker A creates a deadlock. Cloudflare does not prevent circular bindings at deploy time; only the CI gate above catches them.

---

## Gotchas

- `jsonc-parser` is required because `wrangler.jsonc` uses JSON-with-comments format; `JSON.parse` throws on comment lines.
- Wrangler `services` binding resolution in `wrangler dev` requires all bound Workers to be running locally first. Start them in dependency order (leaf Workers first) or use `wrangler dev --service-binding` overrides to point at deployed staging Workers.
- The `entrypoint` field (named export) is optional and defaults to `"default"`; scripts that extract topology must handle its absence.
- Cloudflare enforces that Service Bindings can only reference Workers in the same Cloudflare account. Cross-account bindings are not supported; use `fetch()` with a secret URL instead.
- Workers free plan accounts cannot use Service Bindings — this topology approach is only relevant on Workers Paid (or Enterprise).

---

## Verification

```bash
# 1. Extract and print topology
pnpm tsx tools/service-binding-topology/src/index.ts --root . --print

# 2. Check for cycles
pnpm tsx tools/service-binding-topology/src/validate.ts

# 3. Verify a wrangler.jsonc service name matches an actual Worker
grep '"name"' apps/workers/*/wrangler.jsonc | sort

# 4. Confirm the Mermaid diagram renders (requires mermaid-cli)
npx mmdc -i docs/service-bindings-topology.md -o /tmp/topology.png
```

---

## Related

- `monorepo-deploy-order-workers-service-bindings.md`
- `monorepo-wrangler-selective-deploy.md`
- `wrangler-config-inheritance-environments-workers.md`
- `wrangler-environments-staging-production.md`
- `monorepo-workspace-cloudflare-workers.md`
- `github-actions-wrangler-deploy-pipeline.md`

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/wrangler/configuration/#services
- https://github.com/microsoft/node-jsonc-parser
- https://mermaid.js.org/syntax/flowchart.html
- https://developers.cloudflare.com/workers/testing/local-development/#service-bindings
