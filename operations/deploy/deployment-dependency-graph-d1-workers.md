# Deployment Dependency Graph Tracking with D1 and Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Deploying Services Without Knowing What They Depend On

Microservice platforms accumulate implicit deployment ordering requirements. Service B must not be deployed before Service A's new API is live, because B's new code calls an endpoint that only exists in A's next version. Without a machine-readable dependency graph, engineers rely on runbooks, tribal knowledge, or post-incident discoveries. Cascading deploy failures follow.

This article describes a D1-backed dependency graph for services, a Workers CI step that queries the graph and validates that all upstream dependencies are healthy before proceeding with a deploy, a topological sort implementation that produces a safe deploy ordering for batch releases, and a lightweight graph visualization API for internal dashboards.

The system treats the dependency graph as a first-class artifact: edges are stored in D1, validated by Workers at deploy time, and versioned alongside service manifests in Git. Any CI pipeline can call the graph API to discover its own upstream dependencies and block if they are unhealthy or on an incompatible version.

## Context

- D1 (SQLite) for the dependency edge store
- Cloudflare Workers for the graph API and CI gate
- GitHub Actions for CI integration
- Health-check endpoints on each service (HTTP 200 = healthy)

## D1 Schema: Dependency Edge Store

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS services (
  name           TEXT PRIMARY KEY,
  current_version TEXT,
  health_url     TEXT NOT NULL,
  owner_team     TEXT,
  updated_at     INTEGER
);

CREATE TABLE IF NOT EXISTS dependency_edges (
  id              TEXT PRIMARY KEY,
  dependent       TEXT NOT NULL,   -- service that needs the upstream
  upstream        TEXT NOT NULL,   -- service being depended on
  min_version     TEXT,            -- semver minimum, NULL = any
  edge_type       TEXT NOT NULL DEFAULT 'runtime',  -- runtime | build | test
  FOREIGN KEY (dependent) REFERENCES services(name),
  FOREIGN KEY (upstream)  REFERENCES services(name)
);

CREATE INDEX IF NOT EXISTS idx_dep_dependent ON dependency_edges(dependent);
CREATE INDEX IF NOT EXISTS idx_dep_upstream  ON dependency_edges(upstream);
```

## Graph API Worker

The graph API exposes three endpoints: `GET /graph/:service/upstreams` to list upstream dependencies, `POST /graph/validate-deploy` to check all upstreams are healthy, and `GET /graph/deploy-order` to return a topologically sorted deploy list for a set of services.

```ts
// src/graph-api.ts
interface Env { DB: D1Database; GATE_SECRET: string; }

interface ServiceRow {
  name: string;
  current_version: string;
  health_url: string;
  owner_team: string;
}

interface EdgeRow {
  upstream: string;
  min_version: string | null;
  edge_type: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const parts = url.pathname.split('/').filter(Boolean);

    // GET /graph/:service/upstreams
    if (req.method === 'GET' && parts[0] === 'graph' && parts[2] === 'upstreams') {
      const service = parts[1];
      const edges = await env.DB.prepare(
        `SELECT de.upstream, de.min_version, de.edge_type, s.current_version, s.health_url
         FROM dependency_edges de
         JOIN services s ON s.name = de.upstream
         WHERE de.dependent = ?`
      ).bind(service).all<EdgeRow & { current_version: string; health_url: string }>();
      return Response.json(edges.results);
    }

    // POST /graph/validate-deploy  { service: string }
    if (req.method === 'POST' && parts[0] === 'graph' && parts[1] === 'validate-deploy') {
      if (req.headers.get('X-Gate-Secret') !== env.GATE_SECRET) {
        return new Response('Unauthorized', { status: 401 });
      }
      const { service } = await req.json<{ service: string }>();
      const result = await validateUpstreams(env.DB, service);
      const status = result.every(r => r.healthy) ? 200 : 424;
      return Response.json(result, { status });
    }

    // GET /graph/deploy-order?services=a,b,c
    if (req.method === 'GET' && parts[0] === 'graph' && parts[1] === 'deploy-order') {
      const names = (url.searchParams.get('services') ?? '').split(',').filter(Boolean);
      const order = await topoSort(env.DB, names);
      return Response.json({ order });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function validateUpstreams(db: D1Database, service: string) {
  const edges = await db.prepare(
    `SELECT de.upstream, de.min_version, s.health_url, s.current_version
     FROM dependency_edges de
     JOIN services s ON s.name = de.upstream
     WHERE de.dependent = ? AND de.edge_type = 'runtime'`
  ).bind(service).all<{ upstream: string; min_version: string | null; health_url: string; current_version: string }>();

  return Promise.all(edges.results.map(async (edge) => {
    let healthy = false;
    try {
      const res = await fetch(edge.health_url, { signal: AbortSignal.timeout(5000) });
      healthy = res.ok;
    } catch { healthy = false; }

    const versionOk = edge.min_version
      ? semverGte(edge.current_version, edge.min_version)
      : true;

    return {
      upstream: edge.upstream,
      healthy: healthy && versionOk,
      http_ok: healthy,
      version_ok: versionOk,
      current_version: edge.current_version,
      required_min: edge.min_version,
    };
  }));
}
```

## Topological Sort for Batch Deploy Ordering

```ts
// Kahn's algorithm — returns services in safe deploy order
async function topoSort(db: D1Database, services: string[]): Promise<string[]> {
  // Build adjacency: upstream -> [dependents]
  const set = new Set(services);
  const edges = await db.prepare(
    `SELECT dependent, upstream FROM dependency_edges
     WHERE dependent IN (${services.map(() => '?').join(',')})
       AND upstream   IN (${services.map(() => '?').join(',')})`
  ).bind(...services, ...services).all<{ dependent: string; upstream: string }>();

  const inDegree = new Map<string, number>(services.map(s => [s, 0]));
  const graph = new Map<string, string[]>(services.map(s => [s, []]));

  for (const { dependent, upstream } of edges.results) {
    graph.get(upstream)!.push(dependent);
    inDegree.set(dependent, (inDegree.get(dependent) ?? 0) + 1);
  }

  const queue = [...inDegree.entries()]
    .filter(([, deg]) => deg === 0)
    .map(([s]) => s);
  const order: string[] = [];

  while (queue.length) {
    const node = queue.shift()!;
    order.push(node);
    for (const dep of graph.get(node) ?? []) {
      const deg = (inDegree.get(dep) ?? 1) - 1;
      inDegree.set(dep, deg);
      if (deg === 0) queue.push(dep);
    }
  }

  if (order.length !== services.length) {
    throw new Error(`Cycle detected among: ${services.filter(s => !order.includes(s)).join(', ')}`);
  }
  return order;
}

// Minimal semver gte (major.minor.patch only)
function semverGte(a: string, b: string): boolean {
  const parse = (s: string) => s.split('.').map(Number);
  const [aMaj, aMin, aPatch] = parse(a);
  const [bMaj, bMin, bPatch] = parse(b);
  if (aMaj !== bMaj) return aMaj > bMaj;
  if (aMin !== bMin) return aMin > bMin;
  return aPatch >= bPatch;
}
```

## CI Integration: GitHub Actions Gate Step

```yaml
# .github/workflows/validated-deploy.yml (relevant step)
- name: Validate upstream dependencies
  id: dep-check
  run: |
    RESULT=$(curl -sf -X POST \
      -H "X-Gate-Secret: ${{ secrets.GATE_SECRET }}" \
      -H "Content-Type: application/json" \
      -d "{\"service\":\"${{ env.SERVICE_NAME }}\"}" \
      https://graph-api.example.workers.dev/graph/validate-deploy)
    echo "$RESULT" | jq .
    FAILED=$(echo "$RESULT" | jq '[.[] | select(.healthy == false)] | length')
    if [ "$FAILED" -gt "0" ]; then
      echo "::error::$FAILED upstream(s) unhealthy — aborting deploy"
      exit 1
    fi
```

## Visualization API

```ts
// GET /graph/dot — returns a Graphviz DOT string for the full graph
async function renderDot(db: D1Database): Promise<string> {
  const edges = await db.prepare(
    `SELECT dependent, upstream, edge_type FROM dependency_edges`
  ).all<{ dependent: string; upstream: string; edge_type: string }>();

  const lines = edges.results.map(e => {
    const style = e.edge_type === 'runtime' ? '' : ' [style=dashed]';
    return `  "${e.dependent}" -> "${e.upstream}"${style};`;
  });
  return `digraph deps {\n  rankdir=LR;\n${lines.join('\n')}\n}`;
}
```

## Anti-patterns

- Hardcoding deploy ordering in CI YAML — the graph drifts from reality within weeks; a D1 source of truth stays in sync when teams register their own edges
- Checking only HTTP 200 for health without version validation — a service might be "healthy" on an older version that lacks the API the dependent needs
- Running the topological sort in the CI script rather than the API — each CI job would need to query and sort independently; centralize in the Worker
- Using directed edges in the wrong direction — model edges as "dependent → upstream" (the service that needs something points at what it needs)

## Gotchas

- `AbortSignal.timeout()` is available in Workers runtime but not in all Node.js versions; test locally with Node 20+
- SQLite `IN (?,?,?)` placeholders must match the count exactly; the `topoSort` function builds the placeholder list dynamically — verify it against the actual D1 bind count limits (currently 100 per query)
- Cycles are a legitimate bug in the dependency data; the Kahn's algorithm check surfaces them, but you need an ops process to resolve them before batch deploys can proceed
- The health URL field should point to a readiness endpoint, not a liveness endpoint — a service can be alive but not ready to serve traffic

## Verification

```ts
// Confirm the graph returns a non-empty deploy order for a known service set
const res = await fetch('https://graph-api.example.workers.dev/graph/deploy-order?services=auth-worker,api-worker,ui-worker');
const { order } = await res.json<{ order: string[] }>();
console.assert(order.length === 3, `Expected 3 services in deploy order, got ${order.length}`);
console.assert(order.indexOf('auth-worker') < order.indexOf('api-worker'), 'auth-worker must deploy before api-worker');
```

## Related

- [consumer-contract-deploy-gates.md](consumer-contract-deploy-gates.md)
- [environment-promotion-gates.md](environment-promotion-gates.md)
- [deploy-gate-antipatterns.md](deploy-gate-antipatterns.md)
- [health-check-readiness-patterns.md](health-check-readiness-patterns.md)
- [deployment-approval-workflow.md](deployment-approval-workflow.md)

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
- https://en.wikipedia.org/wiki/Topological_sorting#Kahn's_algorithm
- https://semver.org/
- https://graphviz.org/doc/info/lang.html
