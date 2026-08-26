# Intl.NumberFormat Scientific and Engineering Notation for Locale-aware Display in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A data-science dashboard formats sensor readings and API latency metrics with hard-coded
`toExponential(2)`, producing `1.23e+6` — unstyled, always in English, and unreadable for
French users who expect `1,23 × 10⁶`. A telemetry panel needs engineering notation (exponent
always a multiple of 3) to display values in kilo-, mega-, giga- scale. Neither use case
should require a third-party library; both must work in Cloudflare Workers without a DOM.

## Context

`Intl.NumberFormat` with `notation: 'scientific'` or `notation: 'engineering'` produces
locale-aware scientific representations. Key distinctions:

- **`'scientific'`** — exponent is whatever makes the coefficient fall in `[1, 10)`.
  `1234.5` → `1.2345 × 10³` in French, `1.2345E3` in some other locale patterns.
- **`'engineering'`** — exponent is always a multiple of 3; coefficient may reach `[1, 1000)`.
  `1234.5` → `1.2345 × 10³`; `12345678` → `12.3 × 10⁶`.
- Both compose with `minimumSignificantDigits` / `maximumSignificantDigits` for sig-fig control.
- The multiplication sign and exponent superscript rendering are locale-determined from CLDR.

These options are part of ECMA-402 and are fully available on V8 in Workers runtime since the
2022 runtime update.

---

## 1. Basic scientific and engineering formatting

```typescript
// src/lib/sci-format.ts

export type ScientificStyle = 'scientific' | 'engineering';

export function formatScientific(
  value: number,
  locale: string,
  opts: {
    style?: ScientificStyle;
    significantDigits?: number;
  } = {}
): string {
  const { style = 'scientific', significantDigits = 3 } = opts;

  return new Intl.NumberFormat(locale, {
    notation: style,
    maximumSignificantDigits: significantDigits,
  }).format(value);
}

// formatScientific(1234567, 'en-US')       => "1.23E6"
// formatScientific(1234567, 'fr-FR')       => "1,23 × 10⁶"
// formatScientific(1234567, 'de-DE')       => "1,23·10⁶"
// formatScientific(1234567, 'en-US', { style: 'engineering' }) => "1.23E6"  (1234.567 → 1.23E3)
// formatScientific(0.000042, 'en-US')     => "4.2E-5"
// formatScientific(0.000042, 'fr-FR')     => "4,2 × 10⁻⁵"
```

---

## 2. Engineering notation for SI prefix display

```typescript
// Map engineering exponents to SI prefix labels for supplementary display
const SI_PREFIXES: Record<number, string> = {
  24: 'Y',  21: 'Z',  18: 'E',  15: 'P',  12: 'T',
   9: 'G',   6: 'M',   3: 'k',   0: '',  -3: 'm',
  -6: 'μ',  -9: 'n', -12: 'p', -15: 'f', -18: 'a',
};

export interface EngValue {
  coefficient: number;
  exponent:    number;
  siPrefix:    string;
  formatted:   string;    // Intl.NumberFormat output
}

export function toEngineering(value: number, locale: string, unit = ''): EngValue {
  if (value === 0) return { coefficient: 0, exponent: 0, siPrefix: '', formatted: `0 ${unit}`.trim() };

  const exp3 = Math.floor(Math.log10(Math.abs(value)) / 3) * 3;
  const coeff = value / Math.pow(10, exp3);
  const siPrefix = SI_PREFIXES[exp3] ?? `×10^${exp3}`;

  const formatted = new Intl.NumberFormat(locale, {
    notation: 'engineering',
    maximumSignificantDigits: 4,
  }).format(value) + (unit ? ` ${unit}` : '');

  return { coefficient: coeff, exponent: exp3, siPrefix, formatted };
}

// toEngineering(1_234_567, 'en-US', 'Hz')
//   => { coefficient: 1.234567, exponent: 6, siPrefix: 'M', formatted: '1.23E6 Hz' }
//
// For display: `${coeff.toPrecision(3)} ${siPrefix}${unit}` => "1.23 MHz"
```

---

## 3. formatToParts for custom rendering in JSON API responses

```typescript
// Return structured parts for the frontend to style the exponent differently
export interface ScientificParts {
  coefficient: string;
  exponentSeparator: string;
  exponent: string;
  full: string;
}

export function scientificParts(value: number, locale: string): ScientificParts {
  const fmt   = new Intl.NumberFormat(locale, { notation: 'scientific', maximumSignificantDigits: 4 });
  const parts = fmt.formatToParts(value);

  // Part types for scientific notation: integer, decimal, fraction,
  // exponentSeparator, exponentMinusSign, exponentInteger
  const coeff = parts
    .filter(p => ['integer', 'decimal', 'fraction', 'minusSign'].includes(p.type))
    .map(p => p.value)
    .join('');
  const sep   = parts.find(p => p.type === 'exponentSeparator')?.value ?? 'E';
  const expSign = parts.find(p => p.type === 'exponentMinusSign')?.value ?? '';
  const expInt  = parts.find(p => p.type === 'exponentInteger')?.value ?? '0';

  return {
    coefficient:       coeff,
    exponentSeparator: sep,
    exponent:          expSign + expInt,
    full:              fmt.format(value),
  };
}

// scientificParts(0.00042, 'en-US')
//   => { coefficient: '4.2', exponentSeparator: 'E', exponent: '-4', full: '4.2E-4' }
// scientificParts(0.00042, 'fr-FR')
//   => { coefficient: '4,2', exponentSeparator: ' × 10', exponent: '⁻⁴', full: '4,2 × 10⁻⁴' }
```

The frontend can then render `<span class="coeff">4,2</span> × 10<sup>-4</sup>` using the
separated parts for typographically correct superscript rendering.

---

## 4. Workers handler for telemetry metrics API

```typescript
// src/handlers/metrics.ts
import { formatScientific, toEngineering } from '../lib/sci-format';

export interface Env { DB: D1Database; }

interface MetricRow { name: string; value: number; unit: string; }

export async function handleMetrics(req: Request, env: Env): Promise<Response> {
  const locale = new URL(req.url).searchParams.get('locale') ?? 'en-US';

  const rows = await env.DB.prepare(
    'SELECT name, value, unit FROM telemetry WHERE recorded_at > unixepoch() - 3600 LIMIT 100'
  ).all<MetricRow>();

  const formatted = rows.results.map(row => ({
    name:        row.name,
    rawValue:    row.value,
    unit:        row.unit,
    scientific:  formatScientific(row.value, locale),
    engineering: toEngineering(row.value, locale, row.unit),
    // e.g. for 1_500_000 Hz → engineering { siPrefix: 'M', formatted: '1.5E6 Hz' }
  }));

  return Response.json({ locale, metrics: formatted });
}
```

---

## 5. Significant-digit rules for different domains

```typescript
// Domain-specific sig-fig presets
const SIG_FIG_PRESETS = {
  chemistry:   { minimumSignificantDigits: 3, maximumSignificantDigits: 4 },
  finance:     { minimumFractionDigits: 2,    maximumFractionDigits: 2 },   // not scientific
  engineering: { minimumSignificantDigits: 3, maximumSignificantDigits: 3 },
  physics:     { minimumSignificantDigits: 4, maximumSignificantDigits: 6 },
  display:     { maximumSignificantDigits: 2 },   // compact dashboard tiles
} as const;

export function formatDomainSci(
  value: number,
  locale: string,
  domain: keyof typeof SIG_FIG_PRESETS = 'display'
): string {
  const preset = SIG_FIG_PRESETS[domain];
  return new Intl.NumberFormat(locale, {
    notation: 'scientific',
    ...preset,
  } as Intl.NumberFormatOptions).format(value);
}
```

---

## Anti-patterns

- **`Number.toExponential()`** — always produces ASCII `1.23e+6` regardless of locale; never
  locale-aware.
- **Manually building `"1.23 × 10^6"` strings** — hard-codes the multiplication symbol and
  ignores locale decimal separators; breaks for locales that use `·` or `E`.
- **Using `notation: 'compact'` when scientific is intended** — `'compact'` produces `1.2M`,
  not `1.2 × 10⁶`; they serve different audiences.
- **Mixing `maximumSignificantDigits` with `minimumFractionDigits`** — these two constraints
  conflict; ECMA-402 throws a `RangeError` if both are specified. Pick one system.

## Gotchas

- **Exponent separator is locale-specific** — `fr-FR` uses ` × 10`, `en-US` uses `E`,
  `de-DE` uses `·10`; never assume `E` as the separator when parsing Intl output.
- **Negative exponents** — the `exponentMinusSign` part type may use a locale-specific minus
  (U+2212 MINUS SIGN) rather than a hyphen-minus; check for both when parsing `formatToParts`.
- **Engineering vs. compact** — `notation: 'engineering'` does NOT automatically append SI
  prefix labels (k, M, G); you must map the exponent to a prefix yourself if needed.
- **`maximumSignificantDigits: 1` rounds aggressively** — `1_999_999` with 1 sig-fig becomes
  `2E6`; validate presets with domain experts before deploying.
- **Zero handling** — `formatScientific(0, locale)` produces `0E0` in some locales; special-
  case zero if a plain `"0"` is preferred.

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { formatScientific, scientificParts } from '../src/lib/sci-format';

describe('formatScientific', () => {
  it('uses locale decimal separator', () => {
    const result = formatScientific(1234.5, 'fr-FR');
    expect(result).toMatch(/,/);        // French decimal comma
  });
  it('produces E notation for en-US', () => {
    expect(formatScientific(1234.5, 'en-US')).toMatch(/E/i);
  });
  it('engineering exponent is multiple of 3', () => {
    const eng = formatScientific(1_234_567, 'en-US', { style: 'engineering' });
    // 1.23E6 — exponent 6 is a multiple of 3
    expect(eng).toMatch(/E6/i);
  });
});

describe('scientificParts', () => {
  it('separates coefficient and exponent', () => {
    const parts = scientificParts(12345, 'en-US');
    expect(parts.coefficient).toBe('1.235');
    expect(parts.exponent).toBe('4');
  });
});
```

## Related

- `number-currency-formatting-2026.md`
- `intl-numberformat-explicit-rounding-policy.md`
- `compact-number-notation-locales-2026.md`
- `locale-aware-number-currency-formatting.md`
- `intl-api-workers-edge-formatting.md`

## Sources

- ECMA-402 Intl.NumberFormat `notation` option: https://tc39.es/ecma402/#sec-intl-numberformat-constructor
- MDN Intl.NumberFormat notation: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#notation
- CLDR Number Patterns (scientific): https://cldr.unicode.org/translation/number-currency-formats/number-and-currency-patterns
- SI prefixes: https://www.bipm.org/en/measurement-units/si-prefixes
- Cloudflare Workers V8 ECMA-402 support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
