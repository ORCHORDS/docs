# Email Template Internationalisation & Localisation with KV + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The example project platform serves tenants in multiple markets. Transactional emails —
welcome, OTP, invoice, shipping confirmation — must be rendered in the recipient's
preferred language with locale-appropriate date formatting, currency, and number
formatting. Translations need to be updated without redeploying Workers. The
solution must support right-to-left (RTL) scripts and be testable by sending a
test email in any locale.

---

## Context

Cloudflare KV is used as the translation store: keys are namespaced by locale and
template name (`t:{locale}:{template}`), values are JSON objects of keyed strings.
Workers load translations from KV on each send (or from the in-memory cache within
a Worker lifetime). The `Intl` API — available in Workers — handles date, number,
and currency formatting per locale without importing additional libraries.

Supported locales are declared in a D1 table so tenants can enable/disable languages
without redeployment. RTL locales (Arabic, Hebrew, Persian) receive an additional
`dir="rtl"` attribute injected automatically.

---

## KV Key Convention

```
Namespace: EMAIL_I18N
Key:   t:{locale}:{templateName}
       e.g. "t:fr-FR:welcome"
            "t:ar:invoice"
Value: JSON object of string keys → translated strings
       {
         "subject": "Bienvenue sur example project",
         "greeting": "Bonjour {{firstName}} !",
         "cta":      "Commencer"
       }

Key:   locales:supported   (single key listing all enabled locales)
Value: JSON string array, e.g. ["en", "fr-FR", "de", "ar", "ja"]
```

---

## D1 Schema: Per-Recipient Locale Preference

```sql
CREATE TABLE IF NOT EXISTS user_locale (
  user_id     TEXT PRIMARY KEY,
  locale      TEXT NOT NULL DEFAULT 'en',
  timezone    TEXT NOT NULL DEFAULT 'UTC',
  currency    TEXT NOT NULL DEFAULT 'USD',
  updated_at  TEXT NOT NULL
);
```

---

## Translation Loader with In-Memory Cache

```typescript
// src/i18n/loader.ts
import type { KVNamespace } from '@cloudflare/workers-types';

type Translations = Record<string, string>;

// Module-level cache: lives for the duration of one Worker invocation
const cache = new Map<string, Translations>();

const FALLBACK_LOCALE = 'en';

export async function getTranslations(
  kv: KVNamespace,
  locale: string,
  templateName: string,
): Promise<Translations> {
  const key = `t:${locale}:${templateName}`;
  if (cache.has(key)) return cache.get(key)!;

  let raw = await kv.get(key, 'json') as Translations | null;

  if (!raw && locale !== FALLBACK_LOCALE) {
    // Try language-only (e.g. "fr" when "fr-FR" not found)
    const langOnly = locale.split('-')[0];
    raw = await kv.get(`t:${langOnly}:${templateName}`, 'json') as Translations | null;
  }

  if (!raw) {
    // Fall back to English
    raw = await kv.get(`t:${FALLBACK_LOCALE}:${templateName}`, 'json') as Translations | null;
  }

  const translations = raw ?? {};
  cache.set(key, translations);
  return translations;
}
```

---

## String Interpolation Engine

```typescript
// src/i18n/interpolate.ts

export type InterpolationData = Record<string, string | number>;

/**
 * Replace {{key}} placeholders in a translated string.
 * Supports basic plural: {{count, plural, one:item|other:items}}
 */
export function interpolate(
  template: string,
  data: InterpolationData,
  locale: string,
): string {
  return template.replace(
    /\{\{(\w+)(?:,\s*plural,\s*([^}]+))?\}\}/g,
    (_, key, pluralDef) => {
      const value = data[key];
      if (value === undefined) return `{{${key}}}`;

      if (pluralDef) {
        const pr = new Intl.PluralRules(locale);
        const form = pr.select(Number(value));  // 'one', 'other', 'few', etc.
        const forms = Object.fromEntries(
          pluralDef.split('|').map((pair: string) => {
            const [k, v] = pair.split(':');
            return [k.trim(), v.trim()];
          }),
        );
        const resolved = forms[form] ?? forms['other'] ?? String(value);
        return `${value} ${resolved}`;
      }

      return String(value);
    },
  );
}
```

---

## Locale-Aware Formatting Utilities

```typescript
// src/i18n/format.ts

export function formatDate(
  date: Date | string,
  locale: string,
  timezone: string,
  style: Intl.DateTimeFormatOptions['dateStyle'] = 'long',
): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: style,
    timeZone:  timezone,
  }).format(d);
}

export function formatCurrency(
  amount: number,
  currency: string,
  locale: string,
): string {
  return new Intl.NumberFormat(locale, {
    style:    'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatNumber(
  value: number,
  locale: string,
  opts?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(locale, opts).format(value);
}
```

---

## HTML Direction Injection

```typescript
// src/i18n/rtl.ts

const RTL_LOCALES = new Set([
  'ar', 'ar-SA', 'ar-EG', 'ar-MA',
  'he', 'he-IL',
  'fa', 'fa-IR',
  'ur', 'ur-PK',
]);

export function getTextDirection(locale: string): 'ltr' | 'rtl' {
  const base = locale.split('-')[0];
  return RTL_LOCALES.has(locale) || RTL_LOCALES.has(base) ? 'rtl' : 'ltr';
}

/** Inject dir and lang attributes into the outermost <html> tag. */
export function injectDirLang(html: string, locale: string): string {
  const dir = getTextDirection(locale);
  return html.replace(
    /<html([^>]*)>/i,
    `<html$1 lang="${locale}" dir="${dir}">`,
  );
}
```

---

## Template Renderer

```typescript
// src/i18n/render.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import { getTranslations }  from './loader';
import { interpolate }       from './interpolate';
import { injectDirLang }     from './rtl';
import { formatDate, formatCurrency } from './format';

export interface RenderOptions {
  locale:   string;
  timezone: string;
  currency: string;
  data:     Record<string, string | number | Date>;
}

/** HTML template function type — receives translated strings and returns HTML. */
type TemplateFunction = (t: Record<string, string>, opts: RenderOptions) => string;

const TEMPLATES: Record<string, TemplateFunction> = {
  welcome: (t, { locale, data }) => `
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>${t.subject}</title></head>
    <body style="font-family: sans-serif; max-width: 600px; margin: auto;">
      <h1>${interpolate(t.greeting, data as Record<string, string>, locale)}</h1>
      <p>${t.body}</p>
      <a  style="background:#0066cc;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px;">
        ${t.cta}
      </a>
    </body>
    </html>
  `,

  invoice: (t, { locale, timezone, currency, data }) => {
    const amount   = Number(data.amount);
    const dueDate  = new Date(String(data.dueDate));
    return `
      <!DOCTYPE html>
      <html>
      <head><meta charset="utf-8"><title>${t.subject}</title></head>
      <body style="font-family: sans-serif; max-width: 600px; margin: auto;">
        <h1>${t.heading}</h1>
        <p>${interpolate(t.amountDue, { amount: formatCurrency(amount, currency, locale) }, locale)}</p>
        <p>${interpolate(t.dueBy, { date: formatDate(dueDate, locale, timezone) }, locale)}</p>
      </body>
      </html>
    `;
  },
};

export async function renderTemplate(
  kv: KVNamespace,
  templateName: string,
  options: RenderOptions,
): Promise<{ subject: string; html: string }> {
  const t     = await getTranslations(kv, options.locale, templateName);
  const tmplFn = TEMPLATES[templateName];

  if (!tmplFn) throw new Error(`Unknown template: ${templateName}`);

  const rawHtml  = tmplFn(t, options);
  const html     = injectDirLang(rawHtml, options.locale);
  const subject  = interpolate(t.subject ?? templateName, options.data as Record<string, string>, options.locale);

  return { subject, html };
}
```

---

## Loading Translations from KV (Admin CLI)

```bash
# Push English translations
wrangler kv key put --namespace-id=YOUR_NS_ID "t:en:welcome" \
  '{"subject":"Welcome to example project","greeting":"Hello {{firstName}}!","body":"Your account is ready.","cta":"Get started"}'

# Push French translations
wrangler kv key put --namespace-id=YOUR_NS_ID "t:fr-FR:welcome" \
  '{"subject":"Bienvenue sur example project","greeting":"Bonjour {{firstName}} !","body":"Votre compte est prêt.","cta":"Commencer"}'

# Push Arabic translations (RTL)
wrangler kv key put --namespace-id=YOUR_NS_ID "t:ar:welcome" \
  '{"subject":"مرحباً بك في example project","greeting":"مرحباً {{firstName}}!","body":"حسابك جاهز.","cta":"ابدأ الآن"}'
```

---

## Worker Entry Point

```typescript
// src/index.ts
import { renderTemplate } from './i18n/render';
import { getUserLocale }  from './i18n/userLocale';

export interface Env {
  EMAIL_I18N: KVNamespace;
  DB:         D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{
      userId:       string;
      templateName: string;
      data:         Record<string, string | number>;
    }>();

    const prefs = await getUserLocale(env.DB, body.userId);

    const { subject, html } = await renderTemplate(env.EMAIL_I18N, body.templateName, {
      locale:   prefs.locale,
      timezone: prefs.timezone,
      currency: prefs.currency,
      data:     body.data,
    });

    // Hand off to MailChannels or failover layer
    return Response.json({ subject, html, locale: prefs.locale });
  },
};
```

---

## Anti-patterns

- **Hardcoding locale strings in the Worker bundle** — translations in source code
  require a redeployment for every copy change. Always store strings in KV.
- **Building custom plural rules** — `Intl.PluralRules` supports complex plural forms
  (Arabic has 6 forms, Russian has 3). Never attempt to hand-code plural logic;
  always delegate to `Intl.PluralRules`.
- **Embedding direction in CSS only** — `dir` must be in the HTML attribute to work
  correctly in Outlook's HTML renderer, which ignores `direction: rtl` on the body.
- **Falling back silently to English without logging** — if a locale is configured
  but missing from KV, log the missing key so the ops team can add it.
- **Using `toLocaleDateString()` without `timeZone`** — defaults to the Worker's
  execution TZ (UTC), not the recipient's. Always pass `timeZone` explicitly.

---

## Gotchas

- KV `get()` with `'json'` returns `null` for missing keys, not an empty object.
  Always guard with `?? {}`.
- The module-level `cache` in the translation loader lives for the duration of one
  Worker invocation (~30 s max), not across requests. This is intentional: it
  avoids stale translations in long-lived processes while still batching multiple
  `kv.get()` calls within a single email-send request.
- `Intl.DateTimeFormat` with `dateStyle` is not available in all Miniflare versions.
  Pin `miniflare >= 3.20240304.0` and `@cloudflare/workers-types >= 4.20240329`.
- RTL emails in Outlook require `<td dir="rtl">` per cell, not just on `<body>`.
  The `injectDirLang` function above handles only the `<html>` tag; full Outlook
  RTL support requires RTL-aware table templates.

---

## Verification

```bash
# Confirm a translation key is readable
wrangler kv key get --namespace-id=YOUR_NS_ID "t:fr-FR:welcome"

# Send a test render request
curl -X POST https://your-worker.workers.dev/ \
  -H "content-type: application/json" \
  -d '{"userId":"u_123","templateName":"welcome","data":{"firstName":"Marie","ctaUrl":"https://app.example project.com"}}'

# Verify Arabic rendering includes dir="rtl"
# Response html should contain: <html lang="ar" dir="rtl">

# Test missing locale falls back to English
wrangler kv key delete --namespace-id=YOUR_NS_ID "t:it:welcome"
# Then request with locale it → should still receive English subject
```

---

## Related

- `rtl-cjk-email-localization.md`
- `email-personalization-merge-tags-workers-kv.md`
- `email-template-versioning.md`
- `email-transactional-template-personalization-r2-workers.md`
- `email-timezone-aware-send-scheduling-d1-workers.md`

---

## Sources

- MDN — Intl.PluralRules: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- MDN — Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- W3C Internationalization — RTL email: https://www.w3.org/International/articles/inline-bidi-markup/
- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- Unicode CLDR Plural Rules — https://cldr.unicode.org/index/cldr-spec/plural-rules
