# Swahili Localization with Cloudflare Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A platform serving East Africa (Kenya, Tanzania, Uganda, DRC) needs to deliver Swahili (`sw`,
`sw-KE`, `sw-TZ`) UI strings, locale-formatted dates and numbers, and translated database content.
The team discovers that V8's `Intl` support for `sw` is partial, that pluralisation is simpler than
European languages but still locale-tagged, and that accepting `sw-KE` versus `sw-TZ` leads to
subtle currency differences (KES vs TZS). This article covers the full Workers + D1 implementation.

---

## Context

Swahili (Kiswahili) is a Bantu language spoken by 200+ million people across East Africa. Its BCP-47
tags are:
- `sw` — undifferentiated Swahili (fallback)
- `sw-KE` — Swahili as used in Kenya (currency KES, timezone Africa/Nairobi)
- `sw-TZ` — Swahili as used in Tanzania (currency TZS, timezone Africa/Dar_es_Salaam)
- `sw-UG` — Uganda (currency UGX, timezone Africa/Kampala)
- `sw-CD` — Democratic Republic of Congo (currency CDF, timezone Africa/Kinshasa)

Swahili pluralisation under CLDR uses the `other` rule only (no singular/plural distinction in the
grammatical sense; quantifiers carry the number). `Intl.PluralRules` with `sw` returns `one` for
`n = 1` and `other` otherwise, matching English behaviour.

---

## 1. Locale Negotiation for Swahili Subtags

```typescript
// worker/locale/negotiate.ts
const SUPPORTED_SW = ['sw-KE', 'sw-TZ', 'sw-UG', 'sw-CD', 'sw'];
const SW_FALLBACK = 'sw-KE';

export function negotiateSwahili(acceptLanguage: string): string {
  for (const tag of acceptLanguage.split(',')) {
    const candidate = tag.trim().split(';')[0].trim();
    // Exact match
    if (SUPPORTED_SW.includes(candidate)) return candidate;
    // Prefix match: sw-* → sw-KE fallback
    if (candidate.toLowerCase().startsWith('sw')) return SW_FALLBACK;
  }
  return SW_FALLBACK;
}
```

---

## 2. D1 Schema for Multilingual Content

Store translated strings in D1 with a `locale` column that supports both full subtags and language-
only fallback.

```sql
-- D1 schema: translations table
CREATE TABLE IF NOT EXISTS translations (
  key        TEXT NOT NULL,
  locale     TEXT NOT NULL,   -- "sw-KE", "sw-TZ", "sw", "en"
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (key, locale)
);

CREATE INDEX IF NOT EXISTS idx_translations_locale ON translations (locale);

-- Seed some Swahili translations
INSERT OR IGNORE INTO translations (key, locale, value) VALUES
  ('welcome', 'sw',    'Karibu'),
  ('farewell','sw',    'Kwaheri'),
  ('balance', 'sw-KE', 'Salio: {amount} KES'),
  ('balance', 'sw-TZ', 'Salio: {amount} TZS'),
  ('balance', 'sw-UG', 'Salio: {amount} UGX'),
  ('balance', 'sw',    'Salio: {amount}'),
  ('items',   'sw',    '{count} bidhaa');
```

---

## 3. Fallback Chain Lookup

Look up the most specific locale first, then strip the region subtag, then fall back to English.

```typescript
// worker/i18n/lookup.ts
interface TranslationRow {
  value: string;
}

export async function lookupTranslation(
  env: Env,
  key: string,
  locale: string
): Promise<string | null> {
  const chain = buildFallbackChain(locale);

  for (const tag of chain) {
    const row = await env.DB.prepare(
      `SELECT value FROM translations WHERE key = ? AND locale = ? LIMIT 1`
    )
      .bind(key, tag)
      .first<TranslationRow>();

    if (row) return row.value;
  }
  return null;
}

function buildFallbackChain(locale: string): string[] {
  const chain: string[] = [locale];
  // "sw-KE" → add "sw"
  const hyphen = locale.lastIndexOf('-');
  if (hyphen > 0) chain.push(locale.slice(0, hyphen));
  // Always end with English
  chain.push('en');
  return chain;
}
```

---

## 4. Swahili Number and Currency Formatting

`Intl.NumberFormat` for `sw-KE` formats using Western Arabic digits and locale-appropriate
grouping. Kenya uses a period as decimal separator; Tanzania uses a period too. Currency symbols
follow the number in KES/TZS display.

```typescript
// worker/i18n/format.ts
interface FormatOptions {
  locale: string;
  currency?: string;
}

export function formatNumber(value: number, opts: FormatOptions): string {
  return new Intl.NumberFormat(opts.locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(value);
}

export function formatCurrency(value: number, opts: FormatOptions): string {
  const currency = opts.currency ?? localeCurrency(opts.locale);
  return new Intl.NumberFormat(opts.locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

function localeCurrency(locale: string): string {
  const map: Record<string, string> = {
    'sw-KE': 'KES',
    'sw-TZ': 'TZS',
    'sw-UG': 'UGX',
    'sw-CD': 'CDF',
    sw: 'KES', // safe default
  };
  return map[locale] ?? 'USD';
}
```

---

## 5. Swahili Date Formatting

```typescript
// worker/i18n/dates.ts
export function formatDate(
  isoDate: string,
  locale: string,
  style: 'short' | 'medium' | 'long' = 'medium'
): string {
  const tzMap: Record<string, string> = {
    'sw-KE': 'Africa/Nairobi',
    'sw-TZ': 'Africa/Dar_es_Salaam',
    'sw-UG': 'Africa/Kampala',
    'sw-CD': 'Africa/Kinshasa',
    sw: 'Africa/Nairobi',
  };

  const tz = tzMap[locale] ?? 'Africa/Nairobi';

  const formatter = new Intl.DateTimeFormat(locale, {
    dateStyle: style,
    timeZone: tz,
  });

  return formatter.format(new Date(isoDate));
}

// Swahili relative time
export function formatRelativeTime(targetIso: string, locale: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const diffMs = new Date(targetIso).getTime() - Date.now();
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

  if (Math.abs(diffDays) < 1) {
    const diffHours = Math.round(diffMs / (1000 * 60 * 60));
    return rtf.format(diffHours, 'hour');
  }
  return rtf.format(diffDays, 'day');
}
```

---

## 6. Pluralisation in Swahili

Swahili uses noun-class agreement for plurals, but for numeric string templates the CLDR plural
rule assigns `one` to n=1 and `other` to all other values. Workers' `Intl.PluralRules` handles
this correctly.

```typescript
// worker/i18n/plural.ts
export function pluraliseSwahili(
  count: number,
  forms: { one: string; other: string }
): string {
  const pr = new Intl.PluralRules('sw');
  const rule = pr.select(count); // "one" | "other"
  return (forms[rule] ?? forms.other).replace('{count}', String(count));
}

// Usage
const msg = pluraliseSwahili(3, {
  one:   '1 bidhaa',
  other: '{count} bidhaa',
});
// → "3 bidhaa"
```

---

## Anti-patterns

- **Using `sw` as a single locale for all East African users** — KES and TZS differ by roughly
  2,500× in value; displaying the wrong currency is a critical financial error.
- **Hardcoding `Africa/Nairobi` timezone for all Swahili users** — Tanzania uses EAT (UTC+3) same
  as Kenya, but DRC (Kinshasa) uses WAT (UTC+1); always resolve per region subtag.
- **Storing translations only at `sw` level** — region-specific strings (currency names, legal
  disclaimers) must be stored at `sw-KE` / `sw-TZ` level and fall through to `sw` only for shared
  strings.
- **Skipping Swahili plural rules** — even though Swahili has only `one`/`other`, omitting
  `Intl.PluralRules` and hardcoding plural forms breaks if the locale data changes or if you later
  extend to other Bantu languages.

---

## Gotchas

- V8 (Cloudflare Workers) Swahili `Intl.DateTimeFormat` month names may differ from commonly
  expected Kiswahili month names (e.g., "Januari" vs "januari"); test rendered output against
  CLDR data at https://github.com/unicode-org/cldr-json.
- `Intl.RelativeTimeFormat` with `sw` returns strings like "siku 3 zilizopita" (3 days ago) which
  are grammatically correct but may feel informal; provide an editorial override table in D1 for
  high-visibility strings.
- TZS amounts typically display without decimal places in local convention; override
  `minimumFractionDigits: 0` when `locale === 'sw-TZ'` and the amount is a whole number.
- Workers AI translation models have lower coverage for Swahili than for European languages;
  always post-edit machine-translated Swahili strings through a native reviewer before publishing.

---

## Verification

```bash
# Check number formatting for sw-KE and sw-TZ
node -e "
  console.log(new Intl.NumberFormat('sw-KE', {style:'currency',currency:'KES'}).format(1234.5));
  console.log(new Intl.NumberFormat('sw-TZ', {style:'currency',currency:'TZS'}).format(1234.5));
"
# Expected: locale-formatted KES/TZS amounts

# Verify D1 fallback chain
wrangler d1 execute MY_DB \
  --command "SELECT key, locale, value FROM translations WHERE key='balance' ORDER BY locale;"
```

---

## Related

- `locale-fallback-chain.md`
- `locale-negotiation-accept-language.md`
- `low-resource-language-localization.md`
- `ethiopic-amharic-script-rendering-workers.md`
- `georgian-script-localization-workers.md`

---

## Sources

- CLDR Swahili locale data — https://github.com/unicode-org/cldr-json/tree/main/cldr-json/cldr-dates-modern/main/sw
- IANA Language Subtag Registry — https://www.iana.org/assignments/language-subtag-registry
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- ECMA-402 Intl.PluralRules — https://tc39.es/ecma402/#pluralrules-objects
- Unicode CLDR plural rules — https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/language_plural_rules.html
