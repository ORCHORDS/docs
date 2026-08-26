# Anti-Corruption Layer (ACL) Pattern in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker integrates with one or more third-party APIs (payment gateway, CRM, shipping provider) whose data shapes, error codes, and versioning cadence are outside your control. Their schemas leak into your domain model, making refactors painful and tests brittle. When the provider changes a field name, every consumer breaks.

---

## Context

An **Anti-Corruption Layer** (ACL) is a translation boundary that converts external representations into your internal domain model — and vice versa. It prevents the external API's concepts from corrupting your bounded context.

In Cloudflare Workers:

- The ACL runs at the edge, so translation is free in terms of latency (same PoP as your Worker logic).
- D1 caches translated responses to reduce redundant external calls and survive external outages gracefully.
- The adapter pattern isolates each provider behind an interface so providers can be swapped without touching business logic.
- Error mapping converts provider-specific HTTP codes and payloads into typed domain exceptions.

---

## Solution

```typescript
// ============================================================
// domain/shipping.ts — internal domain model (pure, no external types)
// ============================================================
export interface ShipmentQuote {
  provider: string;
  serviceCode: string;
  estimatedDays: number;
  priceCents: number;
  currency: string;
}

export interface TrackingEvent {
  timestamp: Date;
  location: string;
  status: 'IN_TRANSIT' | 'OUT_FOR_DELIVERY' | 'DELIVERED' | 'EXCEPTION';
  description: string;
}

export interface TrackingInfo {
  trackingNumber: string;
  carrier: string;
  events: TrackingEvent[];
  estimatedDelivery: Date | null;
}

// Domain exceptions — typed, no provider specifics
export class ShipmentNotFoundException extends Error {
  constructor(trackingNumber: string) {
    super(`Shipment not found: ${trackingNumber}`);
    this.name = 'ShipmentNotFoundException';
  }
}
export class ShippingProviderUnavailableException extends Error {
  constructor(provider: string, cause?: unknown) {
    super(`Shipping provider ${provider} is unavailable`);
    this.name = 'ShippingProviderUnavailableException';
    if (cause) this.cause = cause;
  }
}
export class RateLimitExceededException extends Error {
  constructor(provider: string, retryAfterSeconds: number) {
    super(`Rate limit exceeded for ${provider}. Retry after ${retryAfterSeconds}s`);
    this.name = 'RateLimitExceededException';
  }
}

// Port — internal interface your business logic depends on
export interface ShippingPort {
  getQuotes(fromZip: string, toZip: string, weightGrams: number): Promise<ShipmentQuote[]>;
  track(trackingNumber: string): Promise<TrackingInfo>;
}

// ============================================================
// acl/fedex-adapter.ts — external shape → domain model
// ============================================================

// Third-party FedEx API shapes (external, never used outside this file)
interface FedExRateRequest {
  shipper: { address: { postalCode: string } };
  recipient: { address: { postalCode: string } };
  requestedPackageLineItems: Array<{ weight: { units: string; value: number } }>;
}

interface FedExRateService {
  serviceType: string;
  deliveryTimestamp: string;
  ratedShipmentDetails: Array<{ totalNetCharge: { amount: string; currency: string } }>;
}

interface FedExRateResponse {
  output: { rateReplyDetails: FedExRateService[] };
  errors?: Array<{ code: string; message: string }>;
}

interface FedExTrackEvent {
  date: string; // ISO
  eventDescription: string;
  scanLocation: { city: string; stateOrProvinceCode: string; countryCode: string };
  derivedStatus: string;
}

interface FedExTrackResponse {
  output: {
    completeTrackResults: Array<{
      trackResults: Array<{
        trackingInfo: { trackingNumberInfo: { trackingNumber: string } };
        estimatedDeliveryTimeWindow?: { window: { begins: string } };
        scanEvents: FedExTrackEvent[];
        error?: { code: string; message: string };
      }>;
    }>;
  };
}

export class FedExAdapter implements ShippingPort {
  private readonly baseUrl = 'https://apis.fedex.com';

  constructor(
    private apiKey: string,
    private db: D1Database,
    private cacheTtlSeconds = 300,
  ) {}

  async getQuotes(fromZip: string, toZip: string, weightGrams: number): Promise<ShipmentQuote[]> {
    const cacheKey = `fedex:quotes:${fromZip}:${toZip}:${weightGrams}`;

    // Check D1 cache first
    const cached = await this.db
      .prepare('SELECT payload, cached_at FROM acl_cache WHERE cache_key = ?1')
      .bind(cacheKey)
      .first<{ payload: string; cached_at: number }>();

    if (cached && Date.now() - cached.cached_at < this.cacheTtlSeconds * 1000) {
      return JSON.parse(cached.payload) as ShipmentQuote[];
    }

    // Translate to FedEx request shape
    const fedexRequest: FedExRateRequest = {
      shipper: { address: { postalCode: fromZip } },
      recipient: { address: { postalCode: toZip } },
      requestedPackageLineItems: [{
        weight: { units: 'KG', value: weightGrams / 1000 },
      }],
    };

    let fedexResponse: FedExRateResponse;
    try {
      const res = await fetch(`${this.baseUrl}/rate/v1/rates/quotes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiKey}`,
          'X-locale': 'en_US',
        },
        body: JSON.stringify(fedexRequest),
      });
      await this.assertOk(res, 'FedEx');
      fedexResponse = await res.json<FedExRateResponse>();
    } catch (err) {
      if (err instanceof ShippingProviderUnavailableException ||
          err instanceof RateLimitExceededException) throw err;
      throw new ShippingProviderUnavailableException('FedEx', err);
    }

    // Translate FedEx response → domain model
    const quotes: ShipmentQuote[] = fedexResponse.output.rateReplyDetails.map((svc) => ({
      provider: 'FedEx',
      serviceCode: svc.serviceType,
      estimatedDays: this.parseDays(svc.deliveryTimestamp),
      priceCents: Math.round(
        parseFloat(svc.ratedShipmentDetails[0]?.totalNetCharge.amount ?? '0') * 100,
      ),
      currency: svc.ratedShipmentDetails[0]?.totalNetCharge.currency ?? 'USD',
    }));

    // Cache translated result in D1
    await this.db
      .prepare(
        `INSERT INTO acl_cache (cache_key, payload, cached_at)
         VALUES (?1, ?2, ?3)
         ON CONFLICT (cache_key) DO UPDATE SET payload = excluded.payload, cached_at = excluded.cached_at`,
      )
      .bind(cacheKey, JSON.stringify(quotes), Date.now())
      .run();

    return quotes;
  }

  async track(trackingNumber: string): Promise<TrackingInfo> {
    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}/track/v1/trackingnumbers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({
          includeDetailedScans: true,
          trackingInfo: [{ trackingNumberInfo: { trackingNumber } }],
        }),
      });
      await this.assertOk(res, 'FedEx');
    } catch (err) {
      if (err instanceof ShipmentNotFoundException ||
          err instanceof RateLimitExceededException) throw err;
      throw new ShippingProviderUnavailableException('FedEx', err);
    }

    const data = await res.json<FedExTrackResponse>();
    const trackResult = data.output.completeTrackResults?.[0]?.trackResults?.[0];

    if (!trackResult || trackResult.error?.code === 'TRACKING.TRACKINGNUMBER.NOTFOUND') {
      throw new ShipmentNotFoundException(trackingNumber);
    }

    // Map FedEx scan events → domain TrackingEvent[]
    const events: TrackingEvent[] = (trackResult.scanEvents ?? []).map((ev) => ({
      timestamp: new Date(ev.date),
      location: [
        ev.scanLocation?.city,
        ev.scanLocation?.stateOrProvinceCode,
        ev.scanLocation?.countryCode,
      ].filter(Boolean).join(', '),
      status: this.mapStatus(ev.derivedStatus),
      description: ev.eventDescription,
    }));

    const estDeliveryStr = trackResult.estimatedDeliveryTimeWindow?.window?.begins;

    return {
      trackingNumber,
      carrier: 'FedEx',
      events,
      estimatedDelivery: estDeliveryStr ? new Date(estDeliveryStr) : null,
    };
  }

  private async assertOk(res: Response, provider: string): Promise<void> {
    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') ?? '60', 10);
      throw new RateLimitExceededException(provider, retryAfter);
    }
    if (res.status === 404) {
      throw new ShipmentNotFoundException('unknown');
    }
    if (!res.ok) {
      throw new ShippingProviderUnavailableException(provider, `HTTP ${res.status}`);
    }
  }

  private parseDays(deliveryTimestamp: string): number {
    if (!deliveryTimestamp) return 0;
    const ms = new Date(deliveryTimestamp).getTime() - Date.now();
    return Math.max(0, Math.ceil(ms / 86_400_000));
  }

  private mapStatus(derivedStatus: string): TrackingEvent['status'] {
    const map: Record<string, TrackingEvent['status']> = {
      'In transit': 'IN_TRANSIT',
      'On FedEx vehicle for delivery': 'OUT_FOR_DELIVERY',
      'Delivered': 'DELIVERED',
      'Delivery exception': 'EXCEPTION',
    };
    return map[derivedStatus] ?? 'IN_TRANSIT';
  }
}

// ============================================================
// worker.ts — business logic only sees ShippingPort
// ============================================================
interface Env {
  DB: D1Database;
  FEDEX_API_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Dependency is on the Port (interface), not the Adapter (implementation)
    const shipping: ShippingPort = new FedExAdapter(env.FEDEX_API_KEY, env.DB);

    try {
      if (request.method === 'GET' && url.pathname === '/quotes') {
        const from = url.searchParams.get('from') ?? '';
        const to = url.searchParams.get('to') ?? '';
        const weight = parseInt(url.searchParams.get('weight') ?? '0', 10);
        const quotes = await shipping.getQuotes(from, to, weight);
        return Response.json(quotes);
      }

      if (request.method === 'GET' && url.pathname.startsWith('/track/')) {
        const trackingNumber = url.pathname.split('/')[2];
        const info = await shipping.track(trackingNumber);
        return Response.json(info);
      }
    } catch (err) {
      return mapDomainError(err);
    }

    return new Response('Not found', { status: 404 });
  },
};

function mapDomainError(err: unknown): Response {
  if (err instanceof ShipmentNotFoundException)
    return Response.json({ error: err.message }, { status: 404 });
  if (err instanceof RateLimitExceededException)
    return Response.json({ error: err.message }, { status: 429 });
  if (err instanceof ShippingProviderUnavailableException)
    return Response.json({ error: err.message }, { status: 503 });
  return Response.json({ error: 'Internal server error' }, { status: 500 });
}
```

---

## Implementation Details

**D1 cache schema**

```sql
CREATE TABLE IF NOT EXISTS acl_cache (
  cache_key TEXT    PRIMARY KEY,
  payload   TEXT    NOT NULL,
  cached_at INTEGER NOT NULL
);
```

**Version negotiation** — When FedEx releases a new API version, add a `version` field to `FedExAdapter`'s constructor and update only the adapter. Business logic remains unchanged. Maintain two adapter instances simultaneously during the migration window.

**Adding a second provider** — Implement `UPSAdapter implements ShippingPort` in `acl/ups-adapter.ts`. The Worker selects an adapter based on configuration (e.g., an env var `SHIPPING_PROVIDER=ups`) without touching business logic.

---

## Anti-patterns

- **Using FedEx types in the domain layer** — the moment `FedExRateService` appears outside `acl/fedex-adapter.ts`, the ACL has been breached.
- **Caching raw provider responses** — cache the *translated* domain objects. If the provider changes field names, the cached raw responses will break on deserialization.
- **One giant ACL for all providers** — each provider gets its own adapter file. Mixing them creates merge conflicts and makes individual provider swaps harder.
- **Swallowing errors in the adapter** — map to typed domain exceptions, never to generic `Error`. The calling Worker needs to differentiate `ShipmentNotFoundException` from `RateLimitExceededException`.

---

## Gotchas

- Cloudflare Workers `fetch()` follows redirects by default. If the provider returns a `302`, your logs will show requests to the redirect target. Set `redirect: 'follow'` explicitly or use `'manual'` if you need to inspect redirect headers.
- D1 cache entries do not auto-expire. Run a periodic cleanup via a Cron Trigger: `DELETE FROM acl_cache WHERE cached_at < ?1` with a threshold timestamp.
- `JSON.parse` on a large provider response can consume significant CPU. Monitor with `Date.now()` around parse calls; if consistently > 10 ms, consider streaming parsers or reducing response scope via provider query parameters.

---

## Verification

```bash
# Get shipping quotes (translated to domain model)
curl 'https://worker.example.com/quotes?from=10001&to=90210&weight=500'
# → [{"provider":"FedEx","serviceCode":"FEDEX_GROUND","estimatedDays":5,"priceCents":1299,...}]

# Track a shipment
curl 'https://worker.example.com/track/794622819110'
# → {"trackingNumber":"...","carrier":"FedEx","events":[...],"estimatedDelivery":"..."}

# Test D1 cache hit — second call should be faster
time curl 'https://worker.example.com/quotes?from=10001&to=90210&weight=500'
```

---

## Related

- `workers-hexagonal-architecture.md` — the ACL adapter is a concrete infrastructure adapter
- `workers-strangler-fig-pattern.md` — ACL translates legacy responses in the proxy layer
- `graceful-degradation-feature-tiers.md` — return cached ACL response when provider is down

---

## Sources

- [Cloudflare Workers documentation](https://developers.cloudflare.com/workers/)
- Eric Evans, *Domain-Driven Design*, Chapter 14 (Anti-Corruption Layer)
- Martin Fowler, *Patterns of Enterprise Application Architecture* — Gateway pattern
