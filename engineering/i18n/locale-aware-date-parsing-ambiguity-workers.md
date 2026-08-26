# Locale-Aware Date Parsing Ambiguity in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A form submission from a French user sends the date `03/04/2024`. Your Workers
API stores it as April 3rd (US MM/DD/YYYY interpretation) when the user intended
March 4th (European DD/MM/YYYY). Alternatively, an API accepts ISO 8601 dates
but receives `24-08-03` from a legacy integration — and it is not clear whether
this is 2024-08-03 or 2003-08-24. The built-in `Date.parse()` is notoriously
locale-unaware and inconsistent across V8 versions for non-ISO inputs.

---

## Context

JavaScript's `Date.parse()` is standardised only for a subset of ISO 8601. For
everything else, behaviour is implementation-defined. In V8 (the engine underlying
Workers), `Date.parse('03/04/2024')` returns the millisecond timestamp for
**March 4, 2024** (MM/DD/YYYY) regardless of the user's locale — silently
misinterpreting European dates.

The solution is to:

1. Identify the date format from context (URL locale prefix, `Accept-Language`
   header, explicit user preference stored in KV, or format shape detection).
2. Parse the date using an explicit format string rather than heuristic parsing.
3. Validate the parsed result against plausible calendar ranges before storing.

Workers runtime does **not** ship `Temporal.parse()` (Temporal API is
non-parseable for arbitrary strings by design), `moment`, or `date-fns` by
default. Keep the parsing logic dependency-light.

---

## Format Shape Detection

When the locale is unknown, shape analysis can narrow the candidate formats before
falling back to a safe error.

```typescript
// src/lib/date-shape.ts

export type DateFormat =
  | 'ISO8601'        // YYYY-MM-DD or YYYY-MM-DDTHH:mm:ssZ
  | 'MDY_SLASH'      // MM/DD/YYYY — US
  | 'DMY_SLASH'      // DD/MM/YYYY — EU, AU, BR
  | 'DMY_DOT'        // DD.MM.YYYY — DE, RU, TR
  | 'YMD_DASH'       // YYYY-MM-DD (same as ISO but without T — safe)
  | 'YMD_SLASH'      // YYYY/MM/DD — JP, CN informal
  | 'AMBIGUOUS'
  | 'UNKNOWN';

const ISO_RE = /^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]+)?$/;
const YMD_SLASH_RE = /^\d{4}\/\d{2}\/\d{2}$/;
const DMY_DOT_RE = /^\d{1,2}\.\d{1,2}\.\d{4}$/;
const SLASH4_RE = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/;
const DASH_SHORT_RE = /^\d{2}-\d{2}-\d{2,4}$/;

export function detectDateShape(input: string): DateFormat {
  const s = input.trim();

  if (ISO_RE.test(s)) return 'ISO8601';
  if (YMD_SLASH_RE.test(s)) return 'YMD_SLASH';
  if (DMY_DOT_RE.test(s)) return 'DMY_DOT';

  const slashMatch = SLASH4_RE.exec(s);
  if (slashMatch) {
    const a = parseInt(slashMatch[1], 10);
    const b = parseInt(slashMatch[2], 10);
    // If first part >12, must be day — unambiguously DMY
    if (a > 12) return 'DMY_SLASH';
    // If second part >12, must be MDY
    if (b > 12) return 'MDY_SLASH';
    // Both ≤12 — ambiguous
    return 'AMBIGUOUS';
  }

  if (DASH_SHORT_RE.test(s)) return 'AMBIGUOUS';
  return 'UNKNOWN';
}
```

---

## Locale-to-Format Mapping

Map BCP 47 locale roots to expected date ordering. This covers the common cases;
extend as needed for your user base.

```typescript
// src/lib/locale-date-format.ts
import type { DateFormat } from './date-shape';

// Map locale prefix → preferred unambiguous ordering
const LOCALE_FORMAT_MAP: Record<string, DateFormat> = {
  // Day-first locales
  en_GB: 'DMY_SLASH', en_AU: 'DMY_SLASH', en_NZ: 'DMY_SLASH',
  en_IE: 'DMY_SLASH', en_IN: 'DMY_SLASH', en_ZA: 'DMY_SLASH',
  fr: 'DMY_SLASH', de: 'DMY_DOT', it: 'DMY_SLASH', es: 'DMY_SLASH',
  pt: 'DMY_SLASH', nl: 'DMY_SLASH', pl: 'DMY_DOT', cs: 'DMY_DOT',
  ru: 'DMY_DOT', uk: 'DMY_DOT', ar: 'DMY_SLASH', tr: 'DMY_DOT',
  // Month-first locales
  en: 'MDY_SLASH', en_US: 'MDY_SLASH', en_CA: 'MDY_SLASH',
  // Year-first locales
  ja: 'YMD_SLASH', zh: 'YMD_SLASH', ko: 'YMD_SLASH',
};

/**
 * Returns the date format expected for a locale string.
 * Tries full locale, then language subtag, then falls back to ISO8601
 * as the only safe unambiguous default.
 */
export function getPreferredDateFormat(locale: string): DateFormat {
  const normalized = locale.replace(/-/g, '_');
  if (LOCALE_FORMAT_MAP[normalized]) return LOCALE_FORMAT_MAP[normalized];

  const language = normalized.split('_')[0];
  return LOCALE_FORMAT_MAP[language] ?? 'ISO8601';
}
```

---

## Date Parser

```typescript
// src/lib/parse-date.ts
import { detectDateShape } from './date-shape';
import { getPreferredDateFormat } from './locale-date-format';
import type { DateFormat } from './date-shape';

export interface ParsedDate {
  year: number;
  month: number; // 1-indexed
  day: number;
  /** ISO 8601 string safe for storage */
  iso: string;
}

export class DateParseError extends Error {
  constructor(
    public readonly input: string,
    public readonly reason: string
  ) {
    super(`Cannot parse date "${input}": ${reason}`);
    this.name = 'DateParseError';
  }
}

function padded(n: number): string {
  return String(n).padStart(2, '0');
}

function validateCalendar(y: number, m: number, d: number): void {
  if (y < 1000 || y > 9999) throw new Error(`year ${y} out of range`);
  if (m < 1 || m > 12) throw new Error(`month ${m} out of range`);
  const daysInMonth = new Date(y, m, 0).getDate(); // Date(y, m, 0) = last day of month m
  if (d < 1 || d > daysInMonth) throw new Error(`day ${d} out of range for ${y}-${padded(m)}`);
}

function buildIso(y: number, m: number, d: number): string {
  return `${y}-${padded(m)}-${padded(d)}`;
}

function parseWithFormat(input: string, format: DateFormat): ParsedDate {
  const s = input.trim();

  if (format === 'ISO8601' || format === 'YMD_DASH') {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (!m) throw new Error('does not match YYYY-MM-DD');
    const [, y, mo, d] = m.map(Number);
    validateCalendar(y, mo, d);
    return { year: y, month: mo, day: d, iso: buildIso(y, mo, d) };
  }

  if (format === 'YMD_SLASH') {
    const m = /^(\d{4})\/(\d{2})\/(\d{2})$/.exec(s);
    if (!m) throw new Error('does not match YYYY/MM/DD');
    const [, y, mo, d] = m.map(Number);
    validateCalendar(y, mo, d);
    return { year: y, month: mo, day: d, iso: buildIso(y, mo, d) };
  }

  if (format === 'MDY_SLASH') {
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s);
    if (!m) throw new Error('does not match MM/DD/YYYY');
    const mo = Number(m[1]), d = Number(m[2]), y = Number(m[3]);
    validateCalendar(y, mo, d);
    return { year: y, month: mo, day: d, iso: buildIso(y, mo, d) };
  }

  if (format === 'DMY_SLASH') {
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s);
    if (!m) throw new Error('does not match DD/MM/YYYY');
    const d = Number(m[1]), mo = Number(m[2]), y = Number(m[3]);
    validateCalendar(y, mo, d);
    return { year: y, month: mo, day: d, iso: buildIso(y, mo, d) };
  }

  if (format === 'DMY_DOT') {
    const m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(s);
    if (!m) throw new Error('does not match DD.MM.YYYY');
    const d = Number(m[1]), mo = Number(m[2]), y = Number(m[3]);
    validateCalendar(y, mo, d);
    return { year: y, month: mo, day: d, iso: buildIso(y, mo, d) };
  }

  throw new Error(`unsupported format: ${format}`);
}

/**
 * Parse a user-submitted date string using locale context.
 *
 * @param input    Raw date string from user input or external source
 * @param locale   BCP 47 locale tag (e.g. "fr-FR", "en-US", "ja-JP")
 * @param strict   If true, throw on AMBIGUOUS rather than applying locale default
 */
export function parseLocaleDate(
  input: string,
  locale: string,
  strict = false
): ParsedDate {
  const shape = detectDateShape(input);

  if (shape === 'UNKNOWN') {
    throw new DateParseError(input, 'unrecognised date format');
  }

  if (shape === 'AMBIGUOUS') {
    if (strict) {
      throw new DateParseError(
        input,
        `ambiguous date — cannot determine MM/DD vs DD/MM without locale context (locale: ${locale})`
      );
    }
    // Apply locale default to resolve ambiguity
    const preferredFormat = getPreferredDateFormat(locale);
    return parseWithFormat(input, preferredFormat);
  }

  // Unambiguous shape — parse directly
  try {
    return parseWithFormat(input, shape);
  } catch (e) {
    throw new DateParseError(input, (e as Error).message);
  }
}
```

---

## Worker Integration

```typescript
// src/workers/date-intake.ts
import { parseLocaleDate, DateParseError } from '../lib/parse-date';

interface DateSubmission {
  date: string;
  locale?: string;
}

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    let body: DateSubmission;
    try {
      body = await request.json<DateSubmission>();
    } catch {
      return Response.json({ error: 'Invalid JSON body' }, { status: 400 });
    }

    // Prefer explicit locale from body; fall back to Accept-Language header
    const rawLocale =
      body.locale ??
      request.headers.get('Accept-Language')?.split(',')[0].split(';')[0].trim() ??
      'en-US';

    // Cloudflare also exposes cf.timezone; use it to cross-check if you need TZ context
    const cfLocale = (request as any).cf?.country
      ? mapCountryToLocale((request as any).cf.country as string)
      : rawLocale;

    try {
      const parsed = parseLocaleDate(body.date, cfLocale);
      return Response.json({
        input: body.date,
        locale: cfLocale,
        iso: parsed.iso,
        components: { year: parsed.year, month: parsed.month, day: parsed.day },
      });
    } catch (e) {
      if (e instanceof DateParseError) {
        return Response.json({ error: e.message }, { status: 422 });
      }
      throw e;
    }
  },
};

// Lightweight fallback: country code → BCP 47 locale
function mapCountryToLocale(cc: string): string {
  const map: Record<string, string> = {
    US: 'en-US', GB: 'en-GB', DE: 'de-DE', FR: 'fr-FR',
    JP: 'ja-JP', CN: 'zh-CN', BR: 'pt-BR', AU: 'en-AU',
    RU: 'ru-RU', IN: 'en-IN', AR: 'es-AR', MX: 'es-MX',
  };
  return map[cc] ?? 'en-US';
}
```

---

## Anti-patterns

**Using `new Date(userInput)` directly:**
```typescript
const d = new Date(body.date); // ❌ — locale-unaware, V8 parses MM/DD/YYYY
```

**Using `Date.parse()` and checking for NaN:**
```typescript
if (isNaN(Date.parse(input))) { throw ...; } // ❌ — only catches malformed strings, not wrong interpretation
```

**Inferring locale purely from IP without a preference signal:**
IP geolocation tells you where the user is connecting from, not where they're
from or what date format their application is set to. Use `cf.country` only as a
last-resort fallback, preferably combined with a stored preference.

**Silently resolving all ambiguous dates one way:**
```typescript
// ❌ — fails silently for half the world
const [m, d, y] = input.split('/'); // assumes MDY
```

---

## Gotchas

- **Two-digit years**: `03/04/24` — V8 interprets the year as 1924 or 2024
  depending on the heuristic. Reject two-digit years outright and return a 422.
- **Korean and Chinese date formats** often include `年月日` characters
  (`2024年03月04日`). These require separate handling outside the regex approach
  above; use `Intl.DateTimeFormat.formatToParts` with a known reference date and
  reverse-map instead.
- **The `fr-CA` locale** uses `YYYY-MM-DD` (ISO style) even though `fr-FR` uses
  `DD/MM/YYYY`. Country matters, not just language.
- **Timestamps with time zones**: if the input is `03/04/2024 14:00 +02:00`,
  parse the date part first, then concatenate with the time in ISO 8601 format
  before constructing a `Date`.
- Reject inputs longer than ~30 characters before running regex — guards against
  ReDoS in untrusted contexts.

---

## Verification

```typescript
// tests/parse-date.test.ts
import { parseLocaleDate, DateParseError } from '../src/lib/parse-date';
import { describe, it, expect } from 'vitest';

describe('parseLocaleDate', () => {
  it('parses unambiguous ISO dates regardless of locale', () => {
    expect(parseLocaleDate('2024-03-04', 'en-US').iso).toBe('2024-03-04');
    expect(parseLocaleDate('2024-03-04', 'fr-FR').iso).toBe('2024-03-04');
  });

  it('resolves 03/04/2024 as March 4 for en-US', () => {
    expect(parseLocaleDate('03/04/2024', 'en-US').iso).toBe('2024-03-04');
  });

  it('resolves 03/04/2024 as April 3 for fr-FR', () => {
    expect(parseLocaleDate('03/04/2024', 'fr-FR').iso).toBe('2024-04-03');
  });

  it('parses DD.MM.YYYY for de-DE', () => {
    expect(parseLocaleDate('03.04.2024', 'de-DE').iso).toBe('2024-04-03');
  });

  it('parses YYYY/MM/DD for ja-JP', () => {
    expect(parseLocaleDate('2024/03/04', 'ja-JP').iso).toBe('2024-03-04');
  });

  it('throws on invalid day 32', () => {
    expect(() => parseLocaleDate('2024-01-32', 'en-US')).toThrow(DateParseError);
  });

  it('throws on unknown format', () => {
    expect(() => parseLocaleDate('not-a-date', 'en-US')).toThrow(DateParseError);
  });

  it('throws in strict mode for ambiguous input', () => {
    expect(() => parseLocaleDate('03/04/2024', 'en-US', true)).toThrow(DateParseError);
  });
});
```

---

## Related

- `datetime-formatting-temporal-api-intl.md`
- `date-time-timezone-workers-edge-formatting.md`
- `d1-locale-aware-date-range-queries.md`
- `edge-timezone-detection-cf-object.md`
- `locale-aware-input-validation.md`

---

## Sources

- V8 date parsing behaviour: https://tc39.es/ecma262/#sec-date-time-string-format
- CLDR locale-to-date-format mapping: https://cldr.unicode.org/translation/date-time/date-time-patterns
- Cloudflare `request.cf` object: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Temporal API (for context on why it doesn't expose a parse function): https://tc39.es/proposal-temporal/docs/#Temporal.PlainDate
