# Anti-Corruption Layer for Legacy APIs in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker must integrate with a legacy SOAP/XML backend whose response shape is deeply nested,
uses XML attributes as data, mixes snake_case and PascalCase, and changes schema without notice.
Allowing its raw types to leak into application code means every schema change breaks domain
logic across many files.

## Context

The Anti-Corruption Layer (ACL) is a translation boundary that converts external representations
(legacy XML, SOAP envelopes, third-party REST payloads) into the project's own domain types.
In Cloudflare Workers:

- The Worker is the natural ACL host — it sits at the network edge between clients and legacy systems
- TypeScript strict mode plus explicit translation functions prevent external types from polluting the domain
- The domain model remains stable even when the external contract changes; only the ACL translator is updated
- Fetch calls to the legacy system are isolated in an *adapter* class; nothing else in the codebase calls those URLs

---

## Section 1 — Domain Types (Internal Model)

```typescript
// src/domain/types/product.ts

export interface Product {
  id: string;
  sku: string;
  name: string;
  priceCents: number;
  currency: 'USD' | 'EUR' | 'GBP';
  inStock: boolean;
  tags: string[];
}

export interface ProductSearchResult {
  products: Product[];
  totalCount: number;
  pageToken: string | null;
}
```

---

## Section 2 — Legacy XML/SOAP Response Types

These types mirror the wire format exactly and exist *only* inside the ACL module.
Nothing outside the `infrastructure/acl/` directory imports them.

```typescript
// src/infrastructure/acl/legacyProductTypes.ts
// INTERNAL to the ACL — do not import outside this directory

/** Raw shape returned by the legacy SOAP endpoint */
export interface LegacySoapEnvelope {
  'soap:Envelope': {
    'soap:Body': {
      GetProductsResponse: {
        Products: {
          Product: LegacyProduct | LegacyProduct[]; // single item is not an array!
        };
        TotalCount: string; // integer as string
        NextPageToken?: string;
      };
    };
  };
}

export interface LegacyProduct {
  '@_ProductId': string;   // XML attribute
  '@_SKU': string;         // XML attribute
  ProductName: string;
  Price: {
    Amount: string;        // decimal as string, e.g. "19.99"
    Currency: string;      // "USD", "EUR", etc.
  };
  StockStatus: 'IN_STOCK' | 'OUT_OF_STOCK' | 'UNKNOWN';
  Tags?: {
    Tag: string | string[]; // again, single tag is not an array
  };
}
```

---

## Section 3 — XML Parser and Translator

```typescript
// src/infrastructure/acl/LegacyProductAdapter.ts

import { XMLParser } from 'fast-xml-parser'; // bundled; no external CDN
import type { LegacySoapEnvelope, LegacyProduct } from './legacyProductTypes';
import type { Product, ProductSearchResult } from '../../domain/types/product';

const SUPPORTED_CURRENCIES = new Set(['USD', 'EUR', 'GBP']);

function toArray<T>(val: T | T[] | undefined): T[] {
  if (val === undefined) return [];
  return Array.isArray(val) ? val : [val];
}

function parseCurrency(raw: string): Product['currency'] {
  const upper = raw.toUpperCase();
  if (SUPPORTED_CURRENCIES.has(upper)) return upper as Product['currency'];
  throw new Error(`Unsupported currency from legacy system: ${raw}`);
}

function parsePriceCents(amount: string): number {
  const float = parseFloat(amount);
  if (isNaN(float)) throw new Error(`Cannot parse price: ${amount}`);
  return Math.round(float * 100);
}

function translateProduct(raw: LegacyProduct): Product {
  return {
    id: raw['@_ProductId'],
    sku: raw['@_SKU'],
    name: raw.ProductName.trim(),
    priceCents: parsePriceCents(raw.Price.Amount),
    currency: parseCurrency(raw.Price.Currency),
    inStock: raw.StockStatus === 'IN_STOCK',
    tags: toArray(raw.Tags?.Tag),
  };
}

export class LegacyProductAdapter {
  private readonly parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: '@_',
  });

  constructor(private readonly legacyBaseUrl: string) {}

  async searchProducts(
    query: string,
    pageToken?: string
  ): Promise<ProductSearchResult> {
    const url = new URL(`${this.legacyBaseUrl}/ProductService`);
    url.searchParams.set('query', query);
    if (pageToken) url.searchParams.set('pageToken', pageToken);

    const response = await fetch(url.toString(), {
      headers: {
        Accept: 'text/xml',
        SOAPAction: '"urn:GetProducts"',
      },
    });

    if (!response.ok) {
      throw new Error(
        `Legacy API error: HTTP ${response.status} ${response.statusText}`
      );
    }

    const xml = await response.text();
    const parsed = this.parser.parse(xml) as LegacySoapEnvelope;

    const resp =
      parsed['soap:Envelope']['soap:Body'].GetProductsResponse;

    const rawProducts = toArray(resp.Products.Product);
    const products = rawProducts.map(translateProduct);

    return {
      products,
      totalCount: parseInt(resp.TotalCount, 10),
      pageToken: resp.NextPageToken ?? null,
    };
  }
}
```

---

## Section 4 — Handler Using Only Domain Types

The handler imports `LegacyProductAdapter` but works entirely with `Product` — it has zero
knowledge of XML, SOAP, or legacy naming conventions.

```typescript
// src/handlers/productSearchHandler.ts

import { LegacyProductAdapter } from '../infrastructure/acl/LegacyProductAdapter';
import type { Product } from '../domain/types/product';

interface Env {
  LEGACY_API_BASE_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const query = url.searchParams.get('q') ?? '';
    const pageToken = url.searchParams.get('pageToken') ?? undefined;

    const adapter = new LegacyProductAdapter(env.LEGACY_API_BASE_URL);

    let result;
    try {
      result = await adapter.searchProducts(query, pageToken);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      return Response.json({ error: message }, { status: 502 });
    }

    // Response uses pure domain types — no legacy shape leaks here
    return Response.json({
      products: result.products.map(productView),
      total: result.totalCount,
      nextPageToken: result.pageToken,
    });
  },
};

function productView(p: Product) {
  return {
    id: p.id,
    sku: p.sku,
    name: p.name,
    price: { amount: p.priceCents, currency: p.currency },
    inStock: p.inStock,
    tags: p.tags,
  };
}
```

---

## Section 5 — Handling Schema Changes in the ACL Only

When the legacy system renames `ProductName` to `Title`, only `translateProduct` in
`LegacyProductAdapter.ts` changes. Domain code, tests, and API responses are untouched.

```typescript
// Before (legacy v1):
name: raw.ProductName.trim(),

// After (legacy v2 renames field to Title):
name: (raw as any).Title?.trim() ?? raw.ProductName?.trim() ?? '',
// Once migration complete, update LegacyProduct type and remove the fallback
```

---

## Anti-patterns

- **Importing `LegacyProduct` outside `infrastructure/acl/`** — the whole point is containment. Enforce with ESLint `no-restricted-imports` rules pointing at the acl directory.
- **Passing raw XML strings through domain services** — parse and translate at the boundary; domain services must receive domain types.
- **Letting the ACL call business logic** — the adapter only *translates*; it does not make decisions. Business logic lives in domain services that receive translated types.
- **Using `any` for the parsed XML result** — cast to the explicit `LegacySoapEnvelope` type so TypeScript catches schema drift at compile time.

## Gotchas

- `fast-xml-parser` must be bundled; it is not available as a Workers runtime global. Add it to `package.json` and verify the bundle size stays within the 1 MB (free) / 10 MB (paid) Worker script limit.
- XML single-element arrays (`Tag` vs `Tag[]`) are a frequent source of runtime errors — always wrap with `toArray()`.
- SOAP `SOAPAction` headers must match the service's WSDL exactly, including surrounding quotes.
- Character encoding issues in legacy XML (e.g. `ISO-8859-1`) require explicit `TextDecoder` handling before passing to the parser.

## Verification

```bash
# Confirm fast-xml-parser is bundled and bundle size is acceptable
npx wrangler deploy --dry-run 2>&1 | grep 'Script size'

# Unit-test the translator with fixture XML
npx vitest run src/infrastructure/acl/LegacyProductAdapter.test.ts

# Integration smoke-test
curl 'http://localhost:8787/?q=widget' | jq '.products[0].price'
```

## Related

- `workers-repository-pattern-d1.md` — same isolation principle applied to database access
- `workers-value-object-pattern-typescript.md` — value objects used in translated domain types

## Sources

- [fast-xml-parser npm](https://www.npmjs.com/package/fast-xml-parser)
- Evans, E. (2003). *Domain-Driven Design*. Addison-Wesley. Chapter 14: Maintaining Model Integrity — Anti-Corruption Layer.
