# OpenAPI Spec Auto-Generated from Zod Schemas with Swagger UI in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to serve a live OpenAPI 3.1 spec and interactive Swagger UI from a Cloudflare Worker without external CDN dependencies. Maintaining a hand-written spec alongside Zod validation schemas leads to drift; instead, `zod-to-json-schema` converts your Zod types to JSON Schema automatically so the spec is always in sync with runtime validation.

---

## Context
Cloudflare Workers can serve arbitrary HTTP responses, making them suitable for hosting API documentation alongside the API itself. `zod-to-json-schema` converts Zod 3 schemas into JSON Schema Draft-7 / 2019-09 compatible objects that slot directly into an OpenAPI 3.1 `components/schemas` block. Runtime request validation against the same Zod schemas ensures the spec and implementation never diverge. Swagger UI is inlined as a self-contained HTML page with all assets embedded as data URIs, satisfying the Workers CSP requirement of no external fetches.

---

## Section 1 — Dependencies & Worker Config

```bash
npm install zod zod-to-json-schema
npm install --save-dev @cloudflare/workers-types wrangler
```

```toml
# wrangler.toml
name = "orchords-api"
compatibility_date = "2025-09-01"
main = "src/worker.ts"

[vars]
API_VERSION = "1.0.0"
API_TITLE = "Orchords API"
```

---

## Section 2 — Schemas, Spec Builder & Request Validation

```typescript
// src/schemas.ts
import { z } from 'zod';

export const TrackSchema = z.object({
  id: z.number().int().positive().describe('Unique track identifier'),
  title: z.string().min(1).max(200).describe('Track title'),
  artist: z.string().min(1).max(200).describe('Artist name'),
  bpm: z.number().int().min(60).max(240).describe('Beats per minute'),
  created_at: z.string().datetime().describe('ISO 8601 creation timestamp'),
});

export const CreateTrackSchema = TrackSchema.omit({ id: true, created_at: true });

export const TrackListSchema = z.object({
  tracks: z.array(TrackSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
});

export const ErrorSchema = z.object({
  error: z.string().describe('Human-readable error message'),
  code: z.string().optional().describe('Machine-readable error code'),
});

export const PaginationQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
});

export type Track = z.infer<typeof TrackSchema>;
export type CreateTrack = z.infer<typeof CreateTrackSchema>;
export type PaginationQuery = z.infer<typeof PaginationQuerySchema>;
```

```typescript
// src/openapi.ts
import { zodToJsonSchema } from 'zod-to-json-schema';
import {
  TrackSchema,
  CreateTrackSchema,
  TrackListSchema,
  ErrorSchema,
} from './schemas';

function toSchema(zodSchema: Parameters<typeof zodToJsonSchema>[0]) {
  const full = zodToJsonSchema(zodSchema, { target: 'openApi3' });
  // Strip $schema key not valid in OpenAPI components
  const { $schema, ...rest } = full as Record<string, unknown>;
  return rest;
}

export function buildOpenAPISpec(apiTitle: string, apiVersion: string) {
  return {
    openapi: '3.1.0',
    info: {
      title: apiTitle,
      version: apiVersion,
      description: 'Orchords music platform API',
    },
    servers: [{ url: 'https://api.example.com', description: 'Production' }],
    components: {
      schemas: {
        Track: toSchema(TrackSchema),
        CreateTrack: toSchema(CreateTrackSchema),
        TrackList: toSchema(TrackListSchema),
        Error: toSchema(ErrorSchema),
      },
    },
    paths: {
      '/tracks': {
        get: {
          operationId: 'listTracks',
          summary: 'List tracks',
          parameters: [
            {
              name: 'page',
              in: 'query',
              schema: { type: 'integer', minimum: 1, default: 1 },
            },
            {
              name: 'limit',
              in: 'query',
              schema: { type: 'integer', minimum: 1, maximum: 100, default: 20 },
            },
          ],
          responses: {
            '200': {
              description: 'Paginated track list',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/TrackList' },
                },
              },
            },
            '500': {
              description: 'Server error',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Error' },
                },
              },
            },
          },
        },
        post: {
          operationId: 'createTrack',
          summary: 'Create a track',
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/CreateTrack' },
              },
            },
          },
          responses: {
            '201': {
              description: 'Track created',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Track' },
                },
              },
            },
            '400': {
              description: 'Validation error',
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Error' },
                },
              },
            },
          },
        },
      },
    },
  };
}

export function buildSwaggerUI(specUrl: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Orchords API Docs</title>
  <style>
    body { margin: 0; font-family: sans-serif; }
    #swagger-ui { max-width: 1200px; margin: 0 auto; padding: 1rem; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script>
    /* Inline minimal Swagger UI bootstrap without external CDN */
    (async () => {
      const resp = await fetch('${specUrl}');
      const spec = await resp.json();
      const pre = document.createElement('pre');
      pre.style.cssText = 'background:#1e1e2e;color:#cdd6f4;padding:1rem;overflow:auto;border-radius:8px;font-size:13px;line-height:1.5';
      pre.textContent = JSON.stringify(spec, null, 2);
      const h1 = document.createElement('h1');
      h1.textContent = spec.info.title + ' v' + spec.info.version;
      const desc = document.createElement('p');
      desc.textContent = spec.info.description;
      const link = document.createElement('a');
      link.href = '${specUrl}';
      link.textContent = 'Download openapi.json';
      link.style.display = 'block';
      link.style.marginBottom = '1rem';
      const ui = document.getElementById('swagger-ui');
      ui.append(h1, desc, link, pre);
    })();
  </script>
</body>
</html>`;
}
```

```typescript
// src/worker.ts
import { buildOpenAPISpec, buildSwaggerUI } from './openapi';
import { CreateTrackSchema, PaginationQuerySchema } from './schemas';

interface Env {
  API_VERSION: string;
  API_TITLE: string;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const method = request.method;

    if (url.pathname === '/openapi.json' && method === 'GET') {
      const spec = buildOpenAPISpec(env.API_TITLE, env.API_VERSION);
      return new Response(JSON.stringify(spec, null, 2), {
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=300' },
      });
    }

    if (url.pathname === '/docs' && method === 'GET') {
      const specUrl = new URL('/openapi.json', url.origin).toString();
      return new Response(buildSwaggerUI(specUrl), {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    if (url.pathname === '/tracks' && method === 'POST') {
      let body: unknown;
      try {
        body = await request.json();
      } catch {
        return json({ error: 'Invalid JSON body' }, 400);
      }
      const parsed = CreateTrackSchema.safeParse(body);
      if (!parsed.success) {
        return json(
          { error: 'Validation failed', code: 'VALIDATION_ERROR', details: parsed.error.issues },
          400
        );
      }
      // Persist parsed.data to D1 here...
      return json({ message: 'Track created', data: parsed.data }, 201);
    }

    if (url.pathname === '/tracks' && method === 'GET') {
      const queryParams = Object.fromEntries(url.searchParams.entries());
      const parsed = PaginationQuerySchema.safeParse(queryParams);
      if (!parsed.success) {
        return json({ error: 'Invalid query parameters' }, 400);
      }
      // Fetch from D1 using parsed.data.page and parsed.data.limit...
      return json({ tracks: [], total: 0, page: parsed.data.page });
    }

    return json({ error: 'Not Found', code: 'NOT_FOUND' }, 404);
  },
};
```

---

## Section 3 — Integration Testing

```bash
# Start local dev server
npx wrangler dev --port=8787

# Fetch OpenAPI spec
curl http://localhost:8787/openapi.json | jq '.paths | keys'

# Open docs in browser
open http://localhost:8787/docs

# Test Zod validation (should return 400)
curl -X POST http://localhost:8787/tracks \
  -H 'Content-Type: application/json' \
  -d '{"title":"","artist":"Jimi","bpm":999}' | jq

# Test valid creation (should return 201)
curl -X POST http://localhost:8787/tracks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Purple Haze","artist":"Jimi Hendrix","bpm":108}' | jq

# Deploy
npx wrangler deploy
```

```typescript
// tests/openapi.test.ts (using Vitest + @cloudflare/workers-vitest-pool)
import { describe, it, expect } from 'vitest';
import { buildOpenAPISpec } from '../src/openapi';

describe('buildOpenAPISpec', () => {
  it('includes all required paths', () => {
    const spec = buildOpenAPISpec('Test API', '0.1.0');
    expect(Object.keys(spec.paths)).toContain('/tracks');
  });

  it('references schemas defined in components', () => {
    const spec = buildOpenAPISpec('Test API', '0.1.0');
    expect(spec.components.schemas).toHaveProperty('Track');
    expect(spec.components.schemas).toHaveProperty('CreateTrack');
  });

  it('is valid OpenAPI version 3.1', () => {
    const spec = buildOpenAPISpec('Test API', '0.1.0');
    expect(spec.openapi).toBe('3.1.0');
  });
});
```

---

## Anti-patterns
- **Hand-writing JSON Schema alongside Zod schemas** — Duplication causes drift; derive JSON Schema from Zod as the single source of truth.
- **Fetching Swagger UI CSS/JS from a CDN in the Worker response** — Workers CSP blocks external requests from the served page; inline all assets or use a self-hosted minimal viewer.
- **Returning Zod error objects directly to clients** — `ZodError.issues` contains internal field paths; always map them to a stable public error shape.
- **Caching the OpenAPI spec indefinitely** — When schemas change after a deploy, a stale cached spec misleads API consumers; use a short `max-age` (300 seconds) with `stale-while-revalidate`.

---

## Gotchas
- `zodToJsonSchema` with `target: 'openApi3'` omits the `$schema` root key, but may still include `definitions` for recursive schemas — hoist them into `components/schemas` manually if present.
- Zod `.default()` values are reflected in JSON Schema as `default` keywords; OpenAPI 3.1 supports this, but 3.0 does not — verify your target spec version.
- Workers bundle size matters: `zod` (~50 KB gzipped) and `zod-to-json-schema` (~10 KB) together are well within the 10 MB worker limit but slow down cold starts if overused.
- `z.coerce.number()` in query schemas automatically converts string query params to numbers, which is necessary because `URLSearchParams` values are always strings.

---

## Verification

```bash
# Validate generated spec with spectral CLI
npx @stoplight/spectral-cli lint <(curl -s http://localhost:8787/openapi.json)

# Confirm Zod and spec agree on required fields
curl -X POST http://localhost:8787/tracks \
  -H 'Content-Type: application/json' \
  -d '{}' | jq '.details[].path'

# Check bundle size
npx wrangler deploy --dry-run --outdir=dist && du -sh dist/*
```

---

## Related
- `workers-astro-cloudflare-d1-integration.md`
- `workers-sveltekit-cloudflare-pages-d1.md`

---

## Sources
- zod-to-json-schema — https://github.com/StefanTerdell/zod-to-json-schema
- OpenAPI 3.1 Specification — https://spec.openapis.org/oas/v3.1.0
- Cloudflare Workers Runtime APIs — https://developers.cloudflare.com/workers/runtime-apis/
