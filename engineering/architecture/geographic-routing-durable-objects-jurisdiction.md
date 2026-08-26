# Geographic Routing — Durable Objects Jurisdiction and Data Residency

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A SaaS platform must store EU user data exclusively in European data centres to comply with GDPR Article 44. A naively-named Durable Object (`idFromName("user:42")`) may run in any Cloudflare datacenter globally. Without explicit jurisdiction routing, a UK user's data might be stored in a Virginia datacenter, triggering a compliance violation.

## Context

Cloudflare Durable Objects have two mechanisms for geographic placement:

1. **Jurisdiction hints** (`env.NAMESPACE.jurisdiction("eu").idFromName(...)`) — constrain the DO to run only in the EU.
2. **Location hints** (`env.NAMESPACE.get(id, { locationHint: "eeur" })`) — suggest (not guarantee) a specific datacenter region for the stub's first activation.

Combined with the `CF-IPCountry` header on incoming requests, Workers can enforce data-residency routing at the edge before a DO is ever instantiated.

This pattern is distinct from general sharding: the primary concern here is *legal jurisdiction* and *data sovereignty*, not load distribution.

---

## Jurisdiction Detection

```typescript
interface Env {
  USER_DATA: DurableObjectNamespace;
}

const EU_COUNTRIES = new Set([
  'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI',
  'FR','GR','HR','HU','IE','IT','LT','LU','LV','MT',
  'NL','PL','PT','RO','SE','SI','SK',
  // EEA additions
  'IS','LI','NO',
  // GDPR-scope by adequacy
  'GB','CH',
]);

function getJurisdiction(request: Request): 'eu' | 'fedramp' | 'global' {
  const country = request.headers.get('CF-IPCountry') ?? 'XX';
  if (EU_COUNTRIES.has(country)) return 'eu';
  // US federal agencies — FedRAMP region
  if (country === 'US' && request.headers.get('X-Gov-Agency') === '1') return 'fedramp';
  return 'global';
}
```

---

## Jurisdiction-Scoped DO Lookup

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userId } = await request.json<{ userId: string }>();
    const jurisdiction = getJurisdiction(request);

    let ns: DurableObjectNamespace;
    switch (jurisdiction) {
      case 'eu':
        ns = env.USER_DATA.jurisdiction('eu');
        break;
      case 'fedramp':
        ns = env.USER_DATA.jurisdiction('fedramp');
        break;
      default:
        ns = env.USER_DATA;
    }

    // Namespace is now jurisdictionally scoped; idFromName is safe
    const id = ns.idFromName(`user:${userId}`);
    const stub = ns.get(id);

    return stub.fetch(request);
  },
};
```

The `jurisdiction()` call returns a *new namespace object* scoped to that zone. An ID generated from a jurisdictionally-scoped namespace is distinct from one generated from the global namespace — the same string `"user:42"` produces different IDs in different jurisdictions, preventing accidental cross-zone access.

---

## Location Hint for Latency Optimisation

When the user is in a jurisdiction with multiple Cloudflare regions, provide a location hint to reduce cold-start latency:

```typescript
const JURISDICTION_LOCATION_HINTS: Record<string, DurableObjectLocationHint> = {
  'DE': 'weur',  // Western Europe
  'FR': 'weur',
  'PL': 'eeur',  // Eastern Europe
  'US': 'enam',  // Eastern North America
  'SG': 'apac',
};

function getLocationHint(country: string): DurableObjectLocationHint | undefined {
  return JURISDICTION_LOCATION_HINTS[country];
}

// In the fetch handler, after scoping namespace:
const country = request.headers.get('CF-IPCountry') ?? 'XX';
const hint = getLocationHint(country);
const stub = hint ? ns.get(id, { locationHint: hint }) : ns.get(id);
```

Location hints are advisory; Cloudflare may override them based on capacity. Jurisdiction constraints are enforced.

---

## Routing Table as Configuration

Externalise the jurisdiction map to KV so it can be updated without a code deploy:

```typescript
interface JurisdictionConfig {
  euCountries: string[];
  fedRampCountries: string[];
}

async function loadJurisdictionConfig(kv: KVNamespace): Promise<JurisdictionConfig> {
  const raw = await kv.get('jurisdiction:config', 'json') as JurisdictionConfig | null;
  return raw ?? { euCountries: [...EU_COUNTRIES], fedRampCountries: [] };
}
```

Cache the config in `globalThis` within the Worker isolate to avoid per-request KV reads:

```typescript
let cachedConfig: JurisdictionConfig | null = null;
let cacheExpiry = 0;

async function getConfig(kv: KVNamespace): Promise<JurisdictionConfig> {
  if (cachedConfig && Date.now() < cacheExpiry) return cachedConfig;
  cachedConfig = await loadJurisdictionConfig(kv);
  cacheExpiry = Date.now() + 60_000; // refresh every minute
  return cachedConfig;
}
```

---

## Audit Logging for Compliance

```typescript
async function auditLog(
  env: Env,
  userId: string,
  jurisdiction: string,
  country: string,
): Promise<void> {
  await env.AUDIT_QUEUE.send({
    event: 'do_routed',
    userId,
    jurisdiction,
    requestCountry: country,
    timestamp: new Date().toISOString(),
  });
}
```

Audit logs let a Data Protection Officer confirm that EU user IDs were always routed to the `eu` jurisdiction namespace.

---

## Anti-patterns

- **Using the same namespace for all jurisdictions** — `idFromName("user:42")` on the global namespace and on `jurisdiction("eu")` produce different IDs. Mixing them creates two separate DOs for the same user, causing data divergence.
- **Trusting `CF-IPCountry` as the sole data-residency signal** — IP geolocation can be wrong (VPNs, Tor). Use account-level jurisdiction stored in D1 as the authoritative source; use `CF-IPCountry` only as a routing hint.
- **Applying location hints without jurisdiction scoping** — a location hint merely suggests where to run; it does not constrain data residency. Always pair hints with `jurisdiction()` for compliance.

---

## Gotchas

- `jurisdiction("eu")` is only available on Workers with the Durable Objects EU jurisdiction feature enabled (paid plan). Verify in the dashboard before deploying.
- IDs from a scoped namespace cannot be deserialized by the unscoped namespace and vice versa — store the jurisdiction alongside the user record in D1 so you always reconstruct the correct scoped namespace on lookup.
- Cloudflare's `fedramp` jurisdiction requires the FedRAMP-authorised Cloudflare environment; it is not available on standard accounts.

---

## Verification

```bash
# Route a synthetic EU request and confirm the DO runs in an EU datacenter
curl -X POST https://your-worker.workers.dev/user \
  -H 'Content-Type: application/json' \
  -H 'CF-IPCountry: DE' \
  -d '{"userId":"42"}'

# Check audit queue for jurisdiction=eu entries
wrangler tail --format pretty | grep '"jurisdiction":"eu"'
```

---

## Related

- `multi-tenancy-isolation-patterns.md` — tenant-level data isolation
- `multi-region-active-active-durable-objects.md` — multi-region DO replication
- `session-stickiness-durable-objects-workers-routing.md` — sticky routing for sessions
- `data-isolation-strategies.md` — broader data isolation taxonomy
- `sharding-strategy.md` — load-based sharding (different goal)

---

## Sources

- Cloudflare DO jurisdictions: https://developers.cloudflare.com/durable-objects/reference/data-location/
- GDPR Article 44 — transfers to third countries: https://gdpr-info.eu/art-44-gdpr/
- Cloudflare location hints: https://developers.cloudflare.com/durable-objects/reference/data-location/#provide-a-location-hint
