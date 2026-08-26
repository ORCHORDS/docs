# Locale-Aware RFC 7807 Error Responses in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers API returns validation errors in English regardless of the caller's
locale. French users see `"Amount must be a positive number"` in an English-only
response. Additionally, the error payload structure is ad-hoc — some endpoints
return `{ "error": "..." }`, others return `{ "message": "...", "code": 400 }` —
making client-side error handling inconsistent. You want a single, structured
error format that the client can parse reliably, with human-readable messages
adapted to the caller's locale.

---

## Context

RFC 7807 (Problem Details for HTTP APIs) defines a JSON (`application/problem+json`)
and XML error format. Its schema is:

```json
{
  "type": "https://api.example.com/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "The submitted amount must be greater than zero.",
  "instance": "/api/v1/payments/charge",
  "errors": []
}
```

The `title` and `detail` fields are human-readable and should be localized. The
`type` URI and machine-readable `code` fields must stay language-neutral.

Workers are well-placed to apply this pattern: they receive the `Accept-Language`
header before any downstream service and can enforce a uniform error envelope
across all routes.

---

## Error Catalogue Design

Externalize all human-readable strings into a typed catalogue keyed by error
code and locale. Do not inline strings in handler code.

```typescript
// src/i18n/error-messages.ts

export type ErrorCode =
  | 'VALIDATION_FAILED'
  | 'AMOUNT_NOT_POSITIVE'
  | 'CURRENCY_UNSUPPORTED'
  | 'DATE_PARSE_FAILED'
  | 'RESOURCE_NOT_FOUND'
  | 'UNAUTHORIZED'
  | 'RATE_LIMITED'
  | 'INTERNAL_ERROR';

export interface ErrorMessages {
  title: string;
  detail: string; // may contain {0}, {1} placeholders
}

export type ErrorCatalogue = Record<ErrorCode, ErrorMessages>;

const CATALOGUE: Record<string, ErrorCatalogue> = {
  'en': {
    VALIDATION_FAILED:      { title: 'Validation Error',          detail: 'One or more fields are invalid.' },
    AMOUNT_NOT_POSITIVE:    { title: 'Invalid Amount',             detail: 'The amount must be greater than zero.' },
    CURRENCY_UNSUPPORTED:   { title: 'Unsupported Currency',       detail: 'Currency "{0}" is not supported. Accepted: {1}.' },
    DATE_PARSE_FAILED:      { title: 'Invalid Date',               detail: 'Could not parse "{0}" as a date. Use {1} format.' },
    RESOURCE_NOT_FOUND:     { title: 'Not Found',                  detail: 'The requested resource was not found.' },
    UNAUTHORIZED:           { title: 'Unauthorized',               detail: 'Authentication is required to access this resource.' },
    RATE_LIMITED:           { title: 'Too Many Requests',          detail: 'Rate limit exceeded. Retry after {0} seconds.' },
    INTERNAL_ERROR:         { title: 'Internal Server Error',      detail: 'An unexpected error occurred. Please try again.' },
  },
  'fr': {
    VALIDATION_FAILED:      { title: 'Erreur de validation',       detail: 'Un ou plusieurs champs sont invalides.' },
    AMOUNT_NOT_POSITIVE:    { title: 'Montant invalide',           detail: 'Le montant doit être supérieur à zéro.' },
    CURRENCY_UNSUPPORTED:   { title: 'Devise non prise en charge', detail: 'La devise « {0} » n\'est pas prise en charge. Acceptées : {1}.' },
    DATE_PARSE_FAILED:      { title: 'Date invalide',              detail: '« {0} » ne peut pas être interprété comme une date. Utilisez le format {1}.' },
    RESOURCE_NOT_FOUND:     { title: 'Ressource introuvable',      detail: 'La ressource demandée est introuvable.' },
    UNAUTHORIZED:           { title: 'Non autorisé',               detail: 'Une authentification est requise pour accéder à cette ressource.' },
    RATE_LIMITED:           { title: 'Trop de requêtes',           detail: 'Limite de débit dépassée. Réessayez dans {0} secondes.' },
    INTERNAL_ERROR:         { title: 'Erreur interne',             detail: 'Une erreur inattendue s\'est produite. Veuillez réessayer.' },
  },
  'de': {
    VALIDATION_FAILED:      { title: 'Validierungsfehler',         detail: 'Ein oder mehrere Felder sind ungültig.' },
    AMOUNT_NOT_POSITIVE:    { title: 'Ungültiger Betrag',          detail: 'Der Betrag muss größer als null sein.' },
    CURRENCY_UNSUPPORTED:   { title: 'Währung nicht unterstützt',  detail: 'Die Währung „{0}" wird nicht unterstützt. Akzeptiert: {1}.' },
    DATE_PARSE_FAILED:      { title: 'Ungültiges Datum',           detail: '„{0}" konnte nicht als Datum erkannt werden. Bitte Format {1} verwenden.' },
    RESOURCE_NOT_FOUND:     { title: 'Nicht gefunden',             detail: 'Die angeforderte Ressource wurde nicht gefunden.' },
    UNAUTHORIZED:           { title: 'Nicht autorisiert',          detail: 'Zur Nutzung dieser Ressource ist eine Authentifizierung erforderlich.' },
    RATE_LIMITED:           { title: 'Zu viele Anfragen',          detail: 'Ratenlimit überschritten. Erneuter Versuch in {0} Sekunden.' },
    INTERNAL_ERROR:         { title: 'Interner Serverfehler',      detail: 'Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es erneut.' },
  },
  'ja': {
    VALIDATION_FAILED:      { title: 'バリデーションエラー',         detail: '1つ以上のフィールドが無効です。' },
    AMOUNT_NOT_POSITIVE:    { title: '金額が無効です',               detail: '金額はゼロより大きい値を入力してください。' },
    CURRENCY_UNSUPPORTED:   { title: '通貨がサポートされていません',  detail: '通貨「{0}」はサポートされていません。利用可能な通貨: {1}。' },
    DATE_PARSE_FAILED:      { title: '日付が無効です',               detail: '「{0}」を日付として認識できません。{1}形式を使用してください。' },
    RESOURCE_NOT_FOUND:     { title: 'リソースが見つかりません',      detail: 'リクエストされたリソースは存在しません。' },
    UNAUTHORIZED:           { title: '認証が必要です',               detail: 'このリソースへのアクセスには認証が必要です。' },
    RATE_LIMITED:           { title: 'リクエストが多すぎます',        detail: 'レート制限を超えました。{0}秒後に再試行してください。' },
    INTERNAL_ERROR:         { title: '内部サーバーエラー',            detail: '予期しないエラーが発生しました。再度お試しください。' },
  },
};

/** Resolve the best matching catalogue for a BCP 47 locale string. */
export function resolveCatalogue(locale: string): ErrorCatalogue {
  // Try full locale (e.g. fr-CA → fr)
  const language = locale.split('-')[0].toLowerCase();
  return CATALOGUE[language] ?? CATALOGUE['en'];
}

/** Substitute {0}, {1}, ... placeholders in a message string. */
export function interpolate(template: string, args: string[]): string {
  return template.replace(/\{(\d+)\}/g, (_, i) => args[parseInt(i, 10)] ?? '');
}
```

---

## Problem Details Builder

```typescript
// src/lib/problem-details.ts
import { resolveCatalogue, interpolate } from '../i18n/error-messages';
import type { ErrorCode } from '../i18n/error-messages';

const API_BASE_URL = 'https://api.example.com/errors';

export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  /** Locale used for title/detail strings */
  language: string;
  /** Optional field-level errors for VALIDATION_FAILED */
  errors?: FieldError[];
}

export interface FieldError {
  field: string;
  code: ErrorCode;
  detail: string;
}

export function buildProblemDetails(opts: {
  code: ErrorCode;
  status: number;
  instance: string;
  locale: string;
  args?: string[];
  fieldErrors?: Array<{ field: string; code: ErrorCode; args?: string[] }>;
}): ProblemDetails {
  const { code, status, instance, locale, args = [], fieldErrors } = opts;
  const catalogue = resolveCatalogue(locale);
  const language = locale.split('-')[0].toLowerCase();

  const messages = catalogue[code];
  const title  = messages.title;
  const detail = interpolate(messages.detail, args);

  const problem: ProblemDetails = {
    type: `${API_BASE_URL}/${code.toLowerCase().replace(/_/g, '-')}`,
    title,
    status,
    detail,
    instance,
    language,
  };

  if (fieldErrors?.length) {
    problem.errors = fieldErrors.map(fe => {
      const feCatalogue = resolveCatalogue(locale);
      const feMessages = feCatalogue[fe.code];
      return {
        field: fe.field,
        code: fe.code,
        detail: interpolate(feMessages.detail, fe.args ?? []),
      };
    });
  }

  return problem;
}

/** Build a Response with Content-Type: application/problem+json */
export function problemResponse(problem: ProblemDetails): Response {
  return new Response(JSON.stringify(problem), {
    status: problem.status,
    headers: {
      'Content-Type': 'application/problem+json; charset=utf-8',
      'Content-Language': problem.language,
    },
  });
}
```

---

## Middleware: Locale Extraction and Error Wrapping

```typescript
// src/middleware/locale.ts

/** Extract best locale from Accept-Language, falling back to 'en'. */
export function extractLocale(request: Request): string {
  const raw = request.headers.get('Accept-Language') ?? '';
  // Parse first q-weighted tag: "fr-FR,fr;q=0.9,en;q=0.8" → "fr-FR"
  const firstTag = raw.split(',')[0]?.split(';')[0]?.trim();
  if (!firstTag) return 'en';
  try {
    // Validate via Intl.Locale
    return new Intl.Locale(firstTag).baseName;
  } catch {
    return 'en';
  }
}
```

```typescript
// src/workers/payments.ts
import { buildProblemDetails, problemResponse } from '../lib/problem-details';
import { extractLocale } from '../middleware/locale';

const SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'KRW'];

export default {
  async fetch(request: Request): Promise<Response> {
    const locale = extractLocale(request);
    const url = new URL(request.url);

    if (request.method !== 'POST') {
      return problemResponse(buildProblemDetails({
        code: 'VALIDATION_FAILED',
        status: 405,
        instance: url.pathname,
        locale,
      }));
    }

    let body: { amount?: unknown; currency?: unknown };
    try {
      body = await request.json();
    } catch {
      return problemResponse(buildProblemDetails({
        code: 'VALIDATION_FAILED',
        status: 400,
        instance: url.pathname,
        locale,
      }));
    }

    const fieldErrors: Array<{ field: string; code: any; args?: string[] }> = [];

    const amount = Number(body.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      fieldErrors.push({ field: 'amount', code: 'AMOUNT_NOT_POSITIVE' });
    }

    const currency = String(body.currency ?? '').toUpperCase();
    if (!SUPPORTED_CURRENCIES.includes(currency)) {
      fieldErrors.push({
        field: 'currency',
        code: 'CURRENCY_UNSUPPORTED',
        args: [currency, SUPPORTED_CURRENCIES.join(', ')],
      });
    }

    if (fieldErrors.length > 0) {
      return problemResponse(buildProblemDetails({
        code: 'VALIDATION_FAILED',
        status: 422,
        instance: url.pathname,
        locale,
        fieldErrors,
      }));
    }

    // ... process payment ...
    return Response.json({ status: 'accepted' }, { status: 202 });
  },
};
```

### Example response for a French user with two field errors

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json; charset=utf-8
Content-Language: fr

{
  "type": "https://api.example.com/errors/validation-failed",
  "title": "Erreur de validation",
  "status": 422,
  "detail": "Un ou plusieurs champs sont invalides.",
  "instance": "/api/v1/payments/charge",
  "language": "fr",
  "errors": [
    {
      "field": "amount",
      "code": "AMOUNT_NOT_POSITIVE",
      "detail": "Le montant doit être supérieur à zéro."
    },
    {
      "field": "currency",
      "code": "CURRENCY_UNSUPPORTED",
      "detail": "La devise « XYZ » n'est pas prise en charge. Acceptées : USD, EUR, GBP, JPY, KRW."
    }
  ]
}
```

---

## Loading Error Strings from KV (for Large Catalogues)

If the error catalogue grows beyond what you want inlined in the bundle, store it
in KV and fetch lazily at cold start.

```typescript
// src/lib/problem-details-kv.ts
export interface Env {
  ERROR_MESSAGES: KVNamespace;
}

let catalogueCache: Record<string, any> | null = null;

export async function loadCatalogue(kv: KVNamespace, language: string): Promise<any> {
  if (catalogueCache?.[language]) return catalogueCache[language];

  const raw = await kv.get(`error-messages:${language}`, 'json');
  const fallback = raw ?? await kv.get('error-messages:en', 'json') ?? {};
  catalogueCache = { ...(catalogueCache ?? {}), [language]: fallback };
  return fallback;
}
```

Store `error-messages:fr`, `error-messages:de`, etc. in KV as JSON objects
matching the `ErrorCatalogue` shape. Update them via `wrangler kv:key put`
without redeploying the Worker.

---

## Anti-patterns

**Hardcoded English in handler code:**
```typescript
return new Response(JSON.stringify({ error: 'Amount must be positive' }), { status: 422 }); // ❌
```

**Using `Content-Type: application/json` for error responses:**
RFC 7807 requires `application/problem+json`. Clients may use the content type to
decide whether to parse the body as a problem detail or a success payload.

**Translating `type` URIs:**
```json
{ "type": "https://api.example.com/erreurs/montant-invalide" }  // ❌ — breaks client logic
```
The `type` URI is a stable identifier used by machine clients. Localize only
`title` and `detail`.

**Including stack traces or internal identifiers in `detail`:**
```json
{ "detail": "TypeError at /src/workers/payments.ts:42" }  // ❌
```

---

## Gotchas

- **`Accept-Language: *`** is technically valid and means "any language". Treat it
  as equivalent to no preference → return `en`.
- **Right-to-left locales** (`ar`, `he`, `fa`): if error messages are embedded in
  HTML (e.g., a server-side-rendered error page), wrap them with `dir="rtl"` and
  `lang="ar"`. The JSON field itself does not need this; it is the rendering layer's
  responsibility.
- **Pluralization in error messages**: `"Rate limit exceeded. Retry after 1 second."` vs
  `"…after 3 seconds."`. The placeholder approach above does not handle plurals.
  For languages with complex plural rules (Arabic, Russian), use ICU
  MessageFormat strings in the catalogue and evaluate them at interpolation time.
- **`Content-Language` response header**: set it to the resolved language tag so
  caches and proxies know which language variant was served. Omitting it can cause
  `Vary: Accept-Language` caches to serve the wrong language to subsequent callers.
- **OAuth and RFC 9457**: RFC 9457 supersedes RFC 7807 and adds `errors` as a
  top-level field (already modelled above). Check which version your OpenAPI
  specification references.

---

## Verification

```typescript
// tests/problem-details.test.ts
import { buildProblemDetails, problemResponse } from '../src/lib/problem-details';
import { describe, it, expect } from 'vitest';

describe('buildProblemDetails', () => {
  it('uses English for unknown locale', () => {
    const p = buildProblemDetails({ code: 'RESOURCE_NOT_FOUND', status: 404, instance: '/x', locale: 'xx-XX' });
    expect(p.title).toBe('Not Found');
    expect(p.language).toBe('xx');
  });

  it('uses French for fr-FR', () => {
    const p = buildProblemDetails({ code: 'RESOURCE_NOT_FOUND', status: 404, instance: '/x', locale: 'fr-FR' });
    expect(p.title).toBe('Ressource introuvable');
    expect(p.language).toBe('fr');
  });

  it('interpolates args in detail string', () => {
    const p = buildProblemDetails({
      code: 'CURRENCY_UNSUPPORTED', status: 422, instance: '/x', locale: 'en', args: ['XYZ', 'USD, EUR'],
    });
    expect(p.detail).toContain('XYZ');
    expect(p.detail).toContain('USD, EUR');
  });

  it('includes field errors', () => {
    const p = buildProblemDetails({
      code: 'VALIDATION_FAILED', status: 422, instance: '/x', locale: 'de',
      fieldErrors: [{ field: 'amount', code: 'AMOUNT_NOT_POSITIVE' }],
    });
    expect(p.errors).toHaveLength(1);
    expect(p.errors![0].field).toBe('amount');
  });
});

describe('problemResponse', () => {
  it('sets correct Content-Type header', async () => {
    const p = buildProblemDetails({ code: 'UNAUTHORIZED', status: 401, instance: '/x', locale: 'en' });
    const r = problemResponse(p);
    expect(r.headers.get('Content-Type')).toMatch(/application\/problem\+json/);
    expect(r.status).toBe(401);
  });
});
```

---

## Related

- `api-error-message-localization.md`
- `locale-aware-input-validation.md`
- `icu-messageformat-pluralization-complex-languages.md`
- `locale-aware-date-parsing-ambiguity-workers.md`
- `locale-negotiation-accept-language.md`

---

## Sources

- RFC 7807 (Problem Details for HTTP APIs): https://www.rfc-editor.org/rfc/rfc7807
- RFC 9457 (successor to RFC 7807): https://www.rfc-editor.org/rfc/rfc9457
- `Content-Language` header: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Language
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
