# Data Residency Enforcement with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your product must keep EU personal data inside the EU and US personal data inside the US, satisfying GDPR Article 44 restrictions on international data transfers. Users are globally distributed, and a single Cloudflare Worker sits in front of all storage. You need to route each request to the correct regional D1 database (or equivalent storage), log any routing decisions for compliance audit, and handle edge cases (unknown regions, misconfigurations) without silently sending restricted data to the wrong jurisdiction.

## Context

Every incoming request to a Cloudflare Worker includes the `cf` object with country-level geolocation data (`request.cf.country`). This is populated by Cloudflare's Anycast network before your code runs — it is not spoofable via request headers.

Cloudflare **Smart Placement** may migrate your Worker to a PoP closer to your D1 database to reduce round-trip latency. This is useful but can conflict with residency requirements: a Worker placed in Frankfurt should not write to a US D1 database. Smart Placement must be disabled or configured carefully when data residency is enforced.

D1 databases are regional. You create a separate D1 instance per jurisdiction and select the correct one at runtime based on the detected country.

## Solution

```typescript
// data-residency.ts
import { Hono, type Context } from 'hono';

export interface Env {
  // EU-jurisdiction D1 — created with location hint 'weur'
  DB_EU: D1Database;
  // US-jurisdiction D1 — created with location hint 'wnam'
  DB_US: D1Database;
  // Compliance audit queue
  AUDIT_QUEUE: Queue<ResidencyEvent>;
  // Fallback flag: if 'strict', reject unknown jurisdictions; if 'us', default to US
  RESIDENCY_FALLBACK: string; // 'strict' | 'us' | 'eu'
}

type Jurisdiction = 'EU' | 'US';

interface ResidencyEvent {
  requestId: string;
  country: string | null;
  detectedJurisdiction: Jurisdiction | null;
  action: 'routed' | 'fallback' | 'rejected';
  fallbackJurisdiction?: Jurisdiction;
  path: string;
  timestamp: string;
}

// ── EU country list (EEA + UK post-Brexit adequacy decision) ─────────────────
const EU_COUNTRIES = new Set([
  'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR',
  'GR','HR','HU','IE','IT','LT','LU','LV','MT','NL','PL',
  'PT','RO','SE','SI','SK',
  // EEA non-EU
  'IS','LI','NO',
  // UK — adequacy decision in effect; remove if revoked
  'GB',
  // Switzerland — adequacy decision
  'CH',
]);

function detectJurisdiction(country: string | undefined | null): Jurisdiction | null {
  if (!country) return null;
  if (EU_COUNTRIES.has(country)) return 'EU';
  // Explicit US
  if (country === 'US') return 'US';
  // All other countries: return null (caller decides fallback)
  return null;
}

function selectDatabase(jurisdiction: Jurisdiction, env: Env): D1Database {
  return jurisdiction === 'EU' ? env.DB_EU : env.DB_US;
}

// ── Middleware ───────────────────────────────────────────────────────────────
async function residencyMiddleware(
  c: Context<{ Bindings: Env }>,
  next: () => Promise<void>
): Promise<Response | void> {
  const requestId = crypto.randomUUID();
  const cf = c.req.raw.cf as { country?: string } | undefined;
  const country = cf?.country ?? null;
  const detected = detectJurisdiction(country);

  let jurisdiction: Jurisdiction;
  let action: ResidencyEvent['action'];

  if (detected) {
    jurisdiction = detected;
    action = 'routed';
  } else {
    // Unknown country — apply fallback policy
    const fallback = (c.env.RESIDENCY_FALLBACK ?? 'strict') as string;

    if (fallback === 'strict') {
      await logResidencyEvent(c.env.AUDIT_QUEUE, {
        requestId,
        country,
        detectedJurisdiction: null,
        action: 'rejected',
        path: new URL(c.req.url).pathname,
        timestamp: new Date().toISOString(),
      });
      return c.json(
        {
          error: 'Data residency policy: jurisdiction cannot be determined for your location.',
          country,
          requestId,
        },
        451  // HTTP 451 Unavailable For Legal Reasons
      );
    }

    jurisdiction = fallback === 'eu' ? 'EU' : 'US';
    action = 'fallback';
  }

  // Inject DB selection and metadata into context
  c.set('jurisdiction', jurisdiction);
  c.set('db', selectDatabase(jurisdiction, c.env));
  c.set('requestId', requestId);

  // Fire-and-forget compliance log
  void logResidencyEvent(c.env.AUDIT_QUEUE, {
    requestId,
    country,
    detectedJurisdiction: detected,
    action,
    ...(action === 'fallback' ? { fallbackJurisdiction: jurisdiction } : {}),
    path: new URL(c.req.url).pathname,
    timestamp: new Date().toISOString(),
  });

  return next();
}

async function logResidencyEvent(queue: Queue<ResidencyEvent>, event: ResidencyEvent): Promise<void> {
  try {
    await queue.send(event);
  } catch (err) {
    // Non-fatal: log to console if queue unavailable
    console.error('[residency] audit queue send failed', err);
  }
}

// ── App ──────────────────────────────────────────────────────────────────────
type Variables = {
  jurisdiction: Jurisdiction;
  db: D1Database;
  requestId: string;
};

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

app.use('*', residencyMiddleware as never);

// Example: read a user profile from the correct regional DB
app.get('/users/:id', async (c) => {
  const db: D1Database = c.get('db');
  const jurisdiction: Jurisdiction = c.get('jurisdiction');
  const { id } = c.req.param();

  const user = await db
    .prepare('SELECT id, email, name FROM users WHERE id = ?')
    .bind(id)
    .first<{ id: string; email: string; name: string }>();

  if (!user) return c.json({ error: 'User not found' }, 404);

  return c.json({
    user,
    _meta: { jurisdiction, requestId: c.get('requestId') },
  });
});

// Example: write a user profile to the correct regional DB
app.post('/users', async (c) => {
  const db: D1Database = c.get('db');
  const jurisdiction: Jurisdiction = c.get('jurisdiction');
  const body = await c.req.json<{ email: string; name: string }>();

  const userId = crypto.randomUUID();
  await db
    .prepare('INSERT INTO users (id, email, name, jurisdiction) VALUES (?, ?, ?, ?)')
    .bind(userId, body.email, body.name, jurisdiction)
    .run();

  return c.json(
    { userId, jurisdiction, requestId: c.get('requestId') },
    201
  );
});

// ── Cross-jurisdiction transfer guard ────────────────────────────────────────
// Call before any operation that would copy data between DB_EU and DB_US
export async function assertSameJurisdiction(
  sourceJurisdiction: Jurisdiction,
  targetJurisdiction: Jurisdiction,
  operationId: string
): Promise<void> {
  if (sourceJurisdiction !== targetJurisdiction) {
    throw new Error(
      `[residency] GDPR Art.44 violation: cross-jurisdiction transfer blocked. ` +
      `source=${sourceJurisdiction} target=${targetJurisdiction} op=${operationId}`
    );
  }
}

export default app;
```

## Implementation Details

**Creating regional D1 databases with location hints:**

```bash
# EU — Western Europe data centre
wrangler d1 create prod-users-eu --location weur

# US — Western North America data centre
wrangler d1 create prod-users-us --location wnam
```

**wrangler.toml:**

```toml
# Disable Smart Placement — it can violate residency by moving the worker
[placement]
mode = "off"

[[d1_databases]]
binding = "DB_EU"
database_name = "prod-users-eu"
database_id = "<eu-database-id>"

[[d1_databases]]
binding = "DB_US"
database_name = "prod-users-us"
database_id = "<us-database-id>"

[vars]
RESIDENCY_FALLBACK = "strict"
```

**GDPR Article 44 — transfer restrictions.** Personal data may only be transferred to a third country if that country has an adequacy decision, SCCs are in place, or another lawful mechanism applies. The country list in `EU_COUNTRIES` must be reviewed whenever the European Commission updates its adequacy decisions.

**UK adequacy decision.** The UK's adequacy decision was subject to review; keep a watch on EC updates and be prepared to remove `'GB'` from the set if revoked.

## Anti-patterns

- **Trusting `CF-IPCountry` headers from the client.** That header is set by Cloudflare's edge and is not available to Workers. Use `request.cf.country` instead — it is injected by the runtime and cannot be spoofed.
- **Single global D1 database.** Even with geo-restricted access, a single database co-locates EU and US data, complicating deletion requests and regulatory audits.
- **Enabling Smart Placement with regional databases.** Smart Placement optimises for latency to the nearest D1 instance, but if both instances are bound, it may route based on the wrong one.
- **Silently defaulting unknown countries to a jurisdiction.** Silence is a compliance risk. Always log fallback routing decisions.
- **Hard-coding the country list in-memory without a review process.** Adequacy decisions change. Store the definitive list in a versioned configuration and test that updates propagate.

## Gotchas

- `request.cf` is typed as `IncomingRequestCfProperties` in the Workers runtime. In test environments (Miniflare, Vitest), `cf` may be `undefined` — always null-check.
- D1 location hints are advisory. Cloudflare may serve the database from a nearby region if the hinted location is temporarily unavailable. For strict residency, verify with the D1 metrics dashboard.
- HTTP 451 is the correct status for "Unavailable For Legal Reasons" (RFC 7725). Do not use 403 for residency blocks — it conflates authorisation failure with legal restriction.
- The Hono `c.set()` / `c.get()` API requires the variable types to be declared in the `Variables` generic to avoid TypeScript errors.
- `cf.country` returns the ISO 3166-1 alpha-2 code in uppercase. Ensure your country set uses uppercase codes.

## Verification

```bash
# Simulate an EU request (override country in Miniflare / local dev)
wrangler dev --var RESIDENCY_FALLBACK=strict
# Then POST with curl and inspect _meta.jurisdiction in the response

# Test strict fallback: send a request with cf.country = 'SG' (Singapore, not in set)
# → expect HTTP 451 with requestId

# Check audit queue events
# → filter by action='rejected' or action='fallback'

# Verify EU record is absent from US database
wrangler d1 execute prod-users-us \
  --command "SELECT COUNT(*) FROM users WHERE id = '<eu-created-user-id>'"
# → 0
```

## Related

- `documentation/docs/policies/compliance/workers-gdpr-data-deletion-pipeline.md`
- `documentation/docs/policies/compliance/workers-audit-log-immutable-r2.md`
- Cloudflare D1 — location hints
- Cloudflare Smart Placement

## Sources

- GDPR Article 44 — General principle for transfers: https://gdpr-info.eu/art-44-gdpr/
- Cloudflare Workers — request.cf object: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Cloudflare D1 — location hints: https://developers.cloudflare.com/d1/configuration/data-location/
- RFC 7725 — HTTP 451: https://www.rfc-editor.org/rfc/rfc7725
- EU adequacy decisions: https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/adequacy-decisions_en
