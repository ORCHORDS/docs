# Durable Objects Location Hints Deploy Configuration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Durable Objects migrate to unexpected regions after a redeploy — latency
spikes for EU users when a DO spawns in `enam` (Eastern North America) instead
of `weur` (Western Europe). Or you need to satisfy data-residency requirements
that restrict certain Durable Objects to specific jurisdictions, and a plain
`wrangler deploy` ignores that requirement silently.

## Context

By default Cloudflare places a Durable Object instance in the region closest
to the first request that creates it. `locationHint` overrides that heuristic
at construction time. `jurisdictionRestriction` (also called Jurisdiction
Constraints in the dashboard) pins a *namespace* to a jurisdiction (`eu`,
`fedramp`). Location hints are per-ID (construction-time), while jurisdictions
are per-namespace (deploy-time). Neither is retroactive: once a DO is created
in a region it stays there until deleted and re-created.

---

## 1. Available Location Codes

| Code   | Region                         |
|--------|-------------------------------|
| `wnam` | Western North America          |
| `enam` | Eastern North America          |
| `sam`  | South America                  |
| `weur` | Western Europe                 |
| `eeur` | Eastern Europe                 |
| `apac` | Asia Pacific                   |
| `oc`   | Oceania                        |
| `afr`  | Africa                         |
| `me`   | Middle East                    |

---

## 2. Namespace Declaration with Jurisdiction

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Unrestricted namespace — location hint at creation time only
[[durable_objects.bindings]]
name       = "SESSIONS"
class_name = "SessionDO"

# EU-jurisdicted namespace — data never leaves EU PoPs
[[durable_objects.bindings]]
name        = "EU_ORDERS"
class_name  = "OrderDO"
jurisdiction = "eu"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["SessionDO", "OrderDO"]
```

---

## 3. Using Location Hints at Construction Time

```typescript
// src/index.ts
export interface Env {
  SESSIONS : DurableObjectNamespace;
  EU_ORDERS: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const userId = url.searchParams.get("user_id") ?? "anonymous";

    // Hint to the region nearest the user
    const hint = regionFromCFRay(request.headers.get("CF-RAY") ?? "");
    const sessionId = env.SESSIONS.idFromName(userId);
    const session   = env.SESSIONS.get(sessionId, { locationHint: hint });

    // EU_ORDERS: jurisdiction already pins to EU; hint is redundant but harmless
    const orderId = env.EU_ORDERS.idFromName(userId);
    const order   = env.EU_ORDERS.get(orderId, { locationHint: "weur" });

    return session.fetch(request);
  },
} satisfies ExportedHandler<Env>;

/** Derive a coarse location from the CF-RAY suffix */
function regionFromCFRay(ray: string): DurableObjectLocationHint {
  const iata = ray.slice(-3).toUpperCase();
  const euIata = new Set(["LHR","AMS","CDG","FRA","MXP","MAD","WAW","ARN"]);
  const apIata = new Set(["NRT","SIN","SYD","BOM","ICN","HKG"]);
  if (euIata.has(iata)) return "weur";
  if (apIata.has(iata)) return "apac";
  return "wnam";
}

export { SessionDO } from "./session-do";
export { OrderDO   } from "./order-do";
```

---

## 4. Durable Object Class with SQLite Storage

```typescript
// src/session-do.ts
import { DurableObject } from "cloudflare:workers";

export class SessionDO extends DurableObject {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // SQLite storage is local to the region where the DO was created
    this.ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS events (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        INTEGER NOT NULL,
        payload   TEXT    NOT NULL
      )
    `);
  }

  async fetch(request: Request): Promise<Response> {
    const { searchParams } = new URL(request.url);
    const event = searchParams.get("event");
    if (event) {
      this.ctx.storage.sql.exec(
        "INSERT INTO events (ts, payload) VALUES (?, ?)",
        Date.now(), event
      );
    }
    const rows = this.ctx.storage.sql
      .exec("SELECT * FROM events ORDER BY ts DESC LIMIT 10")
      .toArray();
    return Response.json(rows);
  }
}
```

---

## 5. CI Deploy Gate — Verify Jurisdiction Before Deploy

```typescript
// scripts/verify-do-jurisdiction.ts
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN   = process.env.CF_API_TOKEN!;
const WORKER     = process.env.WORKER_NAME ?? "my-worker";

interface DONamespace {
  id        : string;
  name      : string;
  script    : string;
  jurisdiction?: string;
}

async function getNamespaces(): Promise<DONamespace[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/workers/durable_objects/namespaces`,
    { headers: { Authorization: `Bearer ${CF_TOKEN}` } }
  );
  const { result } = await res.json<{ result: DONamespace[] }>();
  return result.filter(ns => ns.script === WORKER);
}

const namespaces  = await getNamespaces();
const euNamespace = namespaces.find(ns => ns.name === "EU_ORDERS");

if (!euNamespace) {
  console.error("EU_ORDERS namespace not found — deploy the Worker first");
  process.exit(1);
}
if (euNamespace.jurisdiction !== "eu") {
  console.error(`EU_ORDERS jurisdiction is '${euNamespace.jurisdiction}', expected 'eu'`);
  process.exit(1);
}
console.log("Jurisdiction check passed:", euNamespace);
```

---

## 6. GitHub Actions — Deploy with Jurisdiction Verification

```yaml
# .github/workflows/deploy-do.yml
name: Deploy Worker with DO Location Config

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci

      - name: Deploy Worker
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Verify DO namespace jurisdictions
        run: npx tsx scripts/verify-do-jurisdiction.ts
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:  ${{ secrets.CF_API_TOKEN }}
          WORKER_NAME:   my-worker

      - name: Smoke test EU DO routing
        run: |
          RESPONSE=$(curl -sf "https://my-worker.example.com/session?user_id=test-eu")
          echo "$RESPONSE" | jq .
```

---

## Anti-patterns

- **Setting `locationHint` after the DO already exists** — hints are only
  respected at first construction; subsequent `.get()` calls with a hint are
  silently ignored for existing IDs.
- **Using `idFromName` for globally unique IDs without considering locality** —
  all users share the same DO instance; a US-centric ID pattern causes EU users
  to cross the Atlantic on every call.
- **Jurisdiction on a namespace that already has data** — you cannot add a
  jurisdiction constraint after objects are created; you must migrate data to a
  new namespace with the correct jurisdiction declaration.
- **Relying on location hints for data residency compliance** — hints are best
  effort; only `jurisdiction = "eu"` provides a contractual residency guarantee.

---

## Gotchas

- The `DurableObjectLocationHint` type is a string union in `@cloudflare/workers-types`;
  passing an invalid string compiles but is silently dropped at runtime.
- SQLite-backed Durable Objects (new in 2025) store their database file in the
  DO's home region; the file cannot be migrated without deleting and re-creating
  the object.
- `jurisdiction = "fedramp"` requires a FedRAMP-enabled Cloudflare account; the
  deploy succeeds silently on a standard account but the constraint is not
  enforced.
- Deleting a DO namespace (via API) is irreversible and destroys all stored data
  in it; there is no undo.

---

## Verification

```bash
# List DO namespaces with jurisdiction for a Worker
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/durable_objects/namespaces" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | select(.script=="my-worker") | {name, id, jurisdiction}'

# Confirm a specific DO object's region via CF-RAY header
curl -sv https://my-worker.example.com/session?user_id=probe-eu 2>&1 \
  | grep -i "cf-ray"
```

---

## Related

- `durable-objects-namespace-migration-zero-downtime.md`
- `durable-objects-live-migration-deploy-strategy.md`
- `workers-multi-region-durable-objects-coordination.md`
- `d1-zero-downtime-schema-migration-workers-compatibility.md`

---

## Sources

- DO location hints: https://developers.cloudflare.com/durable-objects/reference/access-durable-object-from-a-worker/#provide-a-location-hint
- DO jurisdictions: https://developers.cloudflare.com/durable-objects/reference/jurisdiction-restrictions/
- DO SQLite storage: https://developers.cloudflare.com/durable-objects/api/storage-api/#sqlite-backed-durable-objects
