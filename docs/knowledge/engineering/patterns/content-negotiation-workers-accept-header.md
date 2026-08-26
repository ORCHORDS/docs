# Content Negotiation in Workers via Accept Header

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your API must serve the same resource in multiple formats — JSON for programmatic clients, HTML for browsers, CSV for data analysts — without separate endpoints per format. Clients signal their preference through the HTTP `Accept` header. A query-parameter override (`?format=csv`) provides a browser-friendly escape hatch.

## Context

HTTP content negotiation (RFC 7231 section 5.3.2) lets clients express an ordered preference list of media types with quality values (`q`). Workers parse the `Accept` header, select the best matching serialiser, route the data through it, and set `Content-Type` plus `Vary` response headers so downstream caches store separate variants per media type.

---

## Section 1 — Parsing Accept Header Quality Values

```typescript
// accept-parser.ts
export interface MediaType {
  type: string;
  q: number;
  params: Record<string, string>;
}

export function parseAccept(header: string | null): MediaType[] {
  if (!header) return [{ type: '*/*', q: 1, params: {} }];

  return header
    .split(',')
    .map((part): MediaType => {
      const segments = part.trim().split(';').map((s) => s.trim());
      const type = segments[0].toLowerCase();
      let q = 1;
      const params: Record<string, string> = {};

      for (const seg of segments.slice(1)) {
        const [k, v] = seg.split('=').map((s) => s.trim());
        if (k === 'q') {
          q = Math.min(1, Math.max(0, parseFloat(v ?? '1')));
        } else {
          params[k] = v ?? '';
        }
      }

      return { type, q, params };
    })
    .sort((a, b) => {
      if (b.q !== a.q) return b.q - a.q;
      const aSpec = a.type.includes('*') ? 0 : 1;
      const bSpec = b.type.includes('*') ? 0 : 1;
      return bSpec - aSpec;
    });
}

export function negotiate(accepted: MediaType[], offered: string[]): string | null {
  for (const { type } of accepted) {
    if (type === '*/*') return offered[0];
    const [acceptType, acceptSubtype] = type.split('/');
    for (const offer of offered) {
      const [offerType, offerSubtype] = offer.split('/');
      if (
        (acceptType === '*' || acceptType === offerType) &&
        (acceptSubtype === '*' || acceptSubtype === offerSubtype)
      ) {
        return offer;
      }
    }
  }
  return null;
}
```

## Section 2 — Serialisers

```typescript
// serialisers.ts
export type Serialiser = (data: unknown) => { body: string; contentType: string };

export const jsonSerialiser: Serialiser = (data) => ({
  body: JSON.stringify(data, null, 2),
  contentType: 'application/json; charset=utf-8',
});

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export const htmlSerialiser: Serialiser = (data) => {
  const rows = Array.isArray(data) ? data : [data];
  const headers = rows.length > 0 ? Object.keys(rows[0] as object) : [];
  const thead = `<tr>${headers.map((h) => `<th>${escHtml(h)}</th>`).join('')}</tr>`;
  const tbody = rows
    .map(
      (row) =>
        `<tr>${headers
          .map((h) => `<td>${escHtml(String((row as Record<string, unknown>)[h] ?? ''))}</td>`)
          .join('')}</tr>`,
    )
    .join('');
  const body = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Result</title>
<style>table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:4px 8px}th{background:#f0f0f0}</style>
</head><body><table><thead>${thead}</thead><tbody>${tbody}</tbody></table></body></html>`;
  return { body, contentType: 'text/html; charset=utf-8' };
};

function csvCell(value: string): string {
  if (value.includes(',') || value.includes('"') || value.includes('\n')) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export const csvSerialiser: Serialiser = (data) => {
  const rows = Array.isArray(data) ? data : [data];
  if (rows.length === 0) return { body: '', contentType: 'text/csv; charset=utf-8' };
  const headers = Object.keys(rows[0] as object);
  const lines = [
    headers.map(csvCell).join(','),
    ...rows.map((row) =>
      headers.map((h) => csvCell(String((row as Record<string, unknown>)[h] ?? ''))).join(','),
    ),
  ];
  return { body: lines.join('\r\n'), contentType: 'text/csv; charset=utf-8' };
};

export const serialisers: Record<string, Serialiser> = {
  'application/json': jsonSerialiser,
  'text/html': htmlSerialiser,
  'text/csv': csvSerialiser,
};

export const OFFERED = Object.keys(serialisers);
```

## Section 3 — Worker with Format Override and Vary Header

```typescript
// worker.ts
import { parseAccept, negotiate } from './accept-parser';
import { serialisers, OFFERED } from './serialisers';

export interface Env { DB: D1Database; }

async function fetchData(db: D1Database, resourceId: string): Promise<unknown> {
  const { results } = await db
    .prepare('SELECT * FROM products WHERE id = ?')
    .bind(resourceId)
    .all();
  return results;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const resourceId = url.searchParams.get('id') ?? '1';

    const formatOverride = url.searchParams.get('format');
    const overrideMap: Record<string, string> = {
      json: 'application/json',
      html: 'text/html',
      csv: 'text/csv',
    };
    const forcedType = formatOverride ? overrideMap[formatOverride.toLowerCase()] : undefined;

    const accepted = parseAccept(request.headers.get('Accept'));
    const selectedType = forcedType ?? negotiate(accepted, OFFERED);

    if (!selectedType || !serialisers[selectedType]) {
      return new Response(
        `Not Acceptable. Supported: ${OFFERED.join(', ')}`,
        { status: 406, headers: { 'Content-Type': 'text/plain' } },
      );
    }

    const data = await fetchData(env.DB, resourceId);
    const { body, contentType } = serialisersselectedType;

    return new Response(body, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        Vary: forcedType ? 'Accept-Encoding' : 'Accept',
        'Cache-Control': 'public, max-age=60',
      },
    });
  },
};
```

## Section 4 — Negotiation Test Cases

```typescript
// accept-parser.test.ts
import { parseAccept, negotiate } from './accept-parser';

const OFFERED = ['application/json', 'text/html', 'text/csv'];

const cases: Array<[string | null, string | null]> = [
  ['text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'text/html'],
  ['application/json', 'application/json'],
  ['text/csv;q=0.9,application/json', 'application/json'],
  ['image/png', null],
  ['*/*', 'application/json'],
  [null, 'application/json'], // no header => first offered
];

for (const [header, expected] of cases) {
  const result = negotiate(parseAccept(header), OFFERED);
  console.assert(result === expected, `FAIL: "${header}" => ${result} (expected ${expected})`);
}
console.log('All negotiation tests passed');
```

## Anti-patterns

- Ignoring `q` values and selecting the first listed type: `text/csv;q=0.5,application/json;q=1.0` would wrongly return CSV.
- Setting `Vary: *`: disables caching entirely; use `Vary: Accept` instead.
- Not returning `406 Not Acceptable`: silently defaulting to JSON hides negotiation failures.
- Parsing `Accept` on every sub-request: parse once at the entry point and pass the selected type downstream.

## Gotchas

- Cloudflare's CDN respects `Vary` headers; ensure your `Cache-Control` policy accounts for per-format variants.
- When format is forced via query param, set `Vary: Accept-Encoding` (not `Vary: Accept`) so the CDN stores the forced-format variant correctly.
- Browsers send `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`; specificity sorting correctly picks `text/html` first.
- jQuery sends `Accept: application/json, text/javascript, */*; q=0.01`; the wildcard still matches — rely on specificity sorting, not presence of wildcard.

## Verification

```bash
# JSON
curl -s -H 'Accept: application/json' 'https://worker.example.com/?id=1' | jq type

# HTML
curl -s -H 'Accept: text/html' 'https://worker.example.com/?id=1' | grep '<table'

# CSV
curl -s -H 'Accept: text/csv' 'https://worker.example.com/?id=1'

# Browser-style Accept
curl -s -H 'Accept: text/html,*/*;q=0.8' 'https://worker.example.com/?id=1' | head -3

# Format override
curl -s 'https://worker.example.com/?id=1&format=csv'

# 406
curl -si -H 'Accept: image/png' 'https://worker.example.com/?id=1' | head -2
```

## Related

- documentation/docs/policies/patterns/idempotent-receiver-workers-kv.md
- MDN — HTTP Content Negotiation
- RFC 7231 section 5.3.2

## Sources

- https://developer.mozilla.org/en-US/docs/Web/HTTP/Content_negotiation
- https://www.rfc-editor.org/rfc/rfc7231#section-5.3.2
- https://developers.cloudflare.com/workers/
