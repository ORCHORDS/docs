# Vitest Workers Geolocation cf Object Mocking
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A Cloudflare Worker reads geolocation fields from `request.cf` (`country`, `continent`, `city`,
`latitude`, `longitude`, `timezone`, `colo`, `asOrganization`, etc.) to apply geo-fencing,
currency localisation, or content routing logic. In unit tests and integration tests, `request.cf`
is `undefined` unless you supply it explicitly, causing the code under test to hit the `undefined`
branch every time regardless of which geo-branch you want to cover.

## Context
`@cloudflare/vitest-pool-workers` runs tests inside a miniature Workers runtime via Vitest's
`pool` integration. You can pass a fake `cf` object when constructing `Request` in tests because
the Workers runtime accepts `cf` as a second-argument option to `new Request()`. This lets you
exercise every geo branch without deploying to a PoP in that region. The `IncomingRequestCfProperties`
type from `@cloudflare/workers-types` documents every field so TypeScript keeps you honest.

## Project Layout
```
src/
  geo-router.ts       # business logic using request.cf
  index.ts            # Worker entry
test/
  geo-router.test.ts
vitest.config.ts
wrangler.toml
```

## Source Under Test
`src/geo-router.ts`:
```typescript
import type { IncomingRequestCfProperties } from '@cloudflare/workers-types';

export interface GeoDecision {
  region: 'eu' | 'us' | 'apac' | 'row';
  currency: string;
  blocklisted: boolean;
  datacenter: string;
}

const BLOCKED_COUNTRIES = new Set(['XX', 'YY']);
const EU_COUNTRIES = new Set([
  'AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI',
  'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT',
  'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK',
]);

export function routeByGeo(cf: IncomingRequestCfProperties | undefined): GeoDecision {
  const country = cf?.country ?? 'US';
  const colo = cf?.colo ?? 'UNKNOWN';

  if (BLOCKED_COUNTRIES.has(country)) {
    return { region: 'row', currency: 'USD', blocklisted: true, datacenter: colo };
  }

  if (EU_COUNTRIES.has(country)) {
    return { region: 'eu', currency: 'EUR', blocklisted: false, datacenter: colo };
  }

  if (country === 'US' || country === 'CA') {
    return { region: 'us', currency: 'USD', blocklisted: false, datacenter: colo };
  }

  const continent = cf?.continent ?? 'NA';
  if (continent === 'AS') {
    return { region: 'apac', currency: 'USD', blocklisted: false, datacenter: colo };
  }

  return { region: 'row', currency: 'USD', blocklisted: false, datacenter: colo };
}

export default {
  async fetch(req: Request): Promise<Response> {
    const decision = routeByGeo(req.cf as IncomingRequestCfProperties | undefined);
    return Response.json(decision);
  },
};
```

## Vitest Config
`vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          compatibilityDate: '2025-01-01',
          compatibilityFlags: ['nodejs_compat'],
        },
      },
    },
  },
});
```

## Test Helpers – cf Factory
`test/cf-factory.ts`:
```typescript
import type { IncomingRequestCfProperties } from '@cloudflare/workers-types';

/** Sensible defaults – override any field per test */
export function makeCf(overrides: Partial<IncomingRequestCfProperties> = {}): IncomingRequestCfProperties {
  return {
    country: 'US',
    continent: 'NA',
    city: 'San Francisco',
    region: 'California',
    regionCode: 'CA',
    latitude: '37.7749',
    longitude: '-122.4194',
    postalCode: '94102',
    timezone: 'America/Los_Angeles',
    colo: 'SFO',
    metroCode: '807',
    asn: 13335,
    asOrganization: 'Cloudflare, Inc.',
    httpProtocol: 'HTTP/2',
    tlsVersion: 'TLSv1.3',
    tlsCipher: 'AEAD-AES128-GCM-SHA256',
    tlsClientAuth: {
      certIssuerDNLegacy: '',
      certIssuerDN: '',
      certPresented: '0',
      certSubjectDNLegacy: '',
      certSubjectDN: '',
      certNotBefore: '',
      certNotAfter: '',
      certSerial: '',
      certFingerprintSHA1: '',
      certFingerprintSHA256: '',
      certVerified: 'NONE',
    },
    ...overrides,
  } as IncomingRequestCfProperties;
}

/** Build a Request with a synthetic cf object */
export function makeGeoRequest(
  url = 'https://example.com/',
  cf: Partial<IncomingRequestCfProperties> = {},
): Request {
  return new Request(url, { cf: makeCf(cf) } as RequestInit & { cf: unknown });
}
```

## Tests
`test/geo-router.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { routeByGeo } from '../src/geo-router';
import { makeCf, makeGeoRequest } from './cf-factory';
import worker from '../src/geo-router';

describe('routeByGeo – unit', () => {
  it('returns us region for US country code', () => {
    const decision = routeByGeo(makeCf({ country: 'US', colo: 'IAD' }));
    expect(decision).toMatchObject({ region: 'us', currency: 'USD', blocklisted: false, datacenter: 'IAD' });
  });

  it('returns us region for Canadian requests', () => {
    const decision = routeByGeo(makeCf({ country: 'CA', continent: 'NA', colo: 'YVR' }));
    expect(decision.region).toBe('us');
  });

  it('returns eu region for German requests with EUR currency', () => {
    const decision = routeByGeo(makeCf({ country: 'DE', continent: 'EU', colo: 'FRA' }));
    expect(decision).toMatchObject({ region: 'eu', currency: 'EUR', blocklisted: false });
  });

  it('returns apac region based on continent when country is unknown', () => {
    const decision = routeByGeo(makeCf({ country: 'SG', continent: 'AS', colo: 'SIN' }));
    expect(decision.region).toBe('apac');
  });

  it('blocklists requests from sanctioned country codes', () => {
    const decision = routeByGeo(makeCf({ country: 'XX' }));
    expect(decision).toMatchObject({ blocklisted: true });
  });

  it('falls back to row for unknown continent', () => {
    const decision = routeByGeo(makeCf({ country: 'ZZ', continent: 'AF', colo: 'JNB' }));
    expect(decision.region).toBe('row');
  });

  it('handles undefined cf gracefully, defaults to US', () => {
    const decision = routeByGeo(undefined);
    expect(decision.region).toBe('us');
    expect(decision.blocklisted).toBe(false);
  });
});

describe('routeByGeo – integration via fetch handler', () => {
  it('returns JSON with correct region for EU request', async () => {
    const req = makeGeoRequest('https://example.com/', { country: 'FR', continent: 'EU', colo: 'CDG' });
    const res = await worker.fetch(req);
    expect(res.status).toBe(200);

    const body = await res.json() as { region: string; currency: string };
    expect(body.region).toBe('eu');
    expect(body.currency).toBe('EUR');
  });

  it('returns JSON with blocklisted: true for restricted country', async () => {
    const req = makeGeoRequest('https://example.com/', { country: 'YY' });
    const res = await worker.fetch(req);
    const body = await res.json() as { blocklisted: boolean };
    expect(body.blocklisted).toBe(true);
  });
});

describe('snapshot – full cf object preserved in response', () => {
  it('matches snapshot for US request from SFO', async () => {
    const req = makeGeoRequest('https://example.com/', { country: 'US', colo: 'SFO' });
    const res = await worker.fetch(req);
    const body = await res.json();
    expect(body).toMatchInlineSnapshot(`
      {
        "blocklisted": false,
        "currency": "USD",
        "datacenter": "SFO",
        "region": "us",
      }
    `);
  });
});
```

## Anti-patterns
- **Constructing `new Request(url)` without `cf`** – `request.cf` will be `undefined` inside the
  Workers runtime too when running `wrangler dev --local`; your code must handle `undefined`, and
  tests should cover that branch explicitly.
- **Using `Object.assign(req, { cf: ... })`** – `Request` is immutable; mutating it fails silently
  or throws. Always pass `cf` as a constructor option.
- **Mocking `request.cf` with `vi.spyOn`** – `Request.prototype.cf` is a getter from the native
  runtime; `vi.spyOn` does not intercept native getters in the Workers pool. Use the constructor
  approach instead.
- **Testing only the happy path country** – geo-routing code almost always has a fallback branch
  for unknown countries; add an explicit test for `undefined` and for an unrecognised country code.

## Gotchas
- `IncomingRequestCfProperties` has ~40 fields; TypeScript will error if you forget required ones
  that have no `?` modifier. The `makeCf` factory pattern with a full default object sidesteps this.
- In Miniflare / `@cloudflare/vitest-pool-workers`, `req.cf` is typed as
  `IncomingRequestCfProperties` when a `cf` init option is passed; otherwise it is `undefined`. The
  type cast `req.cf as IncomingRequestCfProperties` is safe only after the `undefined` guard.
- The `cf` field is stripped if you proxy the `Request` through `fetch()` before inspecting it in a
  test; read `req.cf` before forwarding, or pass it down explicitly.

## Verification
```bash
npx vitest run test/geo-router.test.ts
# Expected: all tests green, snapshot up to date

# Update snapshots after intentional changes
npx vitest run --update-snapshots test/geo-router.test.ts
```

## Related
- `vitest-cloudflare-pool-workers.md`
- `vitest-custom-matchers-workers-environment.md`
- `workers-unit-testing-fetch-mocking.md`
- `snapshot-testing-workers-responses.md`
- `test-data-builders.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://github.com/cloudflare/workers-types
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://miniflare.dev/
