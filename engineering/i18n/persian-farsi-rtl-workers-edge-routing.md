# Persian and Farsi RTL Workers Edge Routing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Users from Iran, Afghanistan, and the Iranian diaspora are served the wrong locale variant, land on LTR pages, or hit URL paths that mix Arabic and Persian routing logic. Your Cloudflare Worker needs to distinguish `fa-IR` (Iranian Persian), `fa-AF` (Dari, Afghanistan), and `prs` (Dari alternate tag), apply RTL layout, serve the correct numbering system (Eastern Arabic / `arabext` digits), and route to the correct content without conflating Persian with Arabic.

---

## Context

Persian (Farsi) is an RTL language written in the Arabic script with additional letters (چ، پ، ژ، گ). It is distinct from Arabic in vocabulary, grammar, digit preferences, and locale data:

| Feature | Arabic (`ar`) | Persian Iran (`fa-IR`) | Dari Afghanistan (`fa-AF` / `prs`) |
|---------|--------------|----------------------|-------------------------------------|
| Script | Arabic | Arabic (extended) | Arabic (extended) |
| Digits default | Arabic-Indic `٠١٢٣٤٥٦٧٨٩` (`arab`) | Extended Arabic-Indic `۰۱۲۳۴۵۶۷۸۹` (`arabext`) | `arabext` |
| Currency | varies | IRR (ریال) | AFN (؋) |
| Calendar | Gregorian / Islamic | Solar Hijri (Persian) | Solar Hijri |
| Time zone | varies | Asia/Tehran (UTC+3:30 / +4:30 DST) | Asia/Kabul (UTC+4:30) |
| Number grouping | right-to-left Arabic conventions | right-to-left | right-to-left |

Routing errors are common because `Accept-Language: fa` arrives without a region, and `fa-AF` / `prs` is rare in browser headers. Geolocation (`cf.country`) is the most reliable first signal.

---

## 1. Locale Detection — Iran vs Afghanistan vs Diaspora

```typescript
// src/fa-detect.ts
export type PersianLocale = 'fa-IR' | 'fa-AF' | 'fa';

export function detectPersianLocale(request: Request): PersianLocale | null {
  const cf = (request as any).cf as { country?: string; region?: string } | undefined;

  // Primary: geolocation
  if (cf?.country === 'IR') return 'fa-IR';
  if (cf?.country === 'AF') return 'fa-AF';

  // Secondary: Accept-Language
  const accept = request.headers.get('Accept-Language') ?? '';
  const tags = accept.split(',').map(p => p.trim().split(';')[0].toLowerCase());

  for (const tag of tags) {
    if (tag === 'fa-ir') return 'fa-IR';
    if (tag === 'fa-af' || tag === 'prs') return 'fa-AF';
    if (tag.startsWith('fa')) return 'fa-IR'; // Default Persian to Iran
  }

  return null;
}

/** Returns the canonical BCP 47 locale tag for routing */
export function canonicalizePersian(locale: PersianLocale): string {
  // prs is an ISO 639-3 code; normalize to fa-AF for Intl APIs
  return locale === 'fa-AF' ? 'fa-AF' : locale;
}
```

---

## 2. Number and Currency Formatting

Persian uses Extended Arabic-Indic digits (`arabext`, U+06F0–U+06F9) by default in `fa-IR`. Always specify `nu-arabext` explicitly to be consistent across ICU versions.

```typescript
// src/fa-number-format.ts

const PERSIAN_CURRENCIES: Record<string, string> = {
  'fa-IR': 'IRR',
  'fa-AF': 'AFN',
  'fa': 'IRR',
};

export function formatNumber(value: number, locale: string): string {
  // Explicitly request Persian digit set
  return new Intl.NumberFormat(`${locale}-u-nu-arabext`, {
    useGrouping: true,
  }).format(value);
}

export function formatCurrency(amount: number, locale: string): string {
  const currency = PERSIAN_CURRENCIES[locale] ?? 'IRR';
  return new Intl.NumberFormat(`${locale}-u-nu-arabext`, {
    style: 'currency',
    currency,
    // IRR has no minor units (no fils); AFN has 2
    minimumFractionDigits: currency === 'IRR' ? 0 : 2,
    maximumFractionDigits: currency === 'IRR' ? 0 : 2,
  }).format(amount);
}

export function formatPercent(value: number, locale: string): string {
  return new Intl.NumberFormat(`${locale}-u-nu-arabext`, {
    style: 'percent',
    minimumFractionDigits: 1,
  }).format(value / 100);
}

// fa-IR: formatNumber(1234567) => "۱٬۲۳۴٬۵۶۷"
// fa-IR: formatCurrency(50000) => "‎ریال ۵۰٬۰۰۰"
```

---

## 3. Date Formatting — Solar Hijri (Persian) Calendar

The Persian calendar (`persian`) is the official calendar in Iran. `Intl.DateTimeFormat` supports it via `u-ca-persian`.

```typescript
// src/fa-dates.ts

const TZ_FA: Record<string, string> = {
  'fa-IR': 'Asia/Tehran',
  'fa-AF': 'Asia/Kabul',
  'fa': 'Asia/Tehran',
};

export function formatDate(date: Date, locale: string): string {
  const timeZone = TZ_FA[locale] ?? 'Asia/Tehran';
  // Solar Hijri calendar with Persian digits
  return new Intl.DateTimeFormat(`${locale}-u-ca-persian-nu-arabext`, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone,
  }).format(date);
  // Example: "۱۵ مرداد ۱۴۰۵" (15 Mordad 1405 in Solar Hijri)
}

export function formatGregorianDate(date: Date, locale: string): string {
  // For contexts requiring Gregorian (e.g., ISO dates, API responses)
  const timeZone = TZ_FA[locale] ?? 'Asia/Tehran';
  return new Intl.DateTimeFormat(`${locale}-u-ca-gregory-nu-arabext`, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone,
  }).format(date);
}

export function formatRelative(date: Date, locale: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const diffMs = date.getTime() - Date.now();
  const diffDays = Math.round(diffMs / 86_400_000);
  if (Math.abs(diffDays) < 1) {
    return rtf.format(Math.round(diffMs / 3_600_000), 'hour');
  }
  return rtf.format(diffDays, 'day');
}
```

---

## 4. URL Routing for Persian Locales

Persian content is typically served under `/fa/`, `/fa-ir/`, or `/fa-af/` path prefixes. The Worker intercepts requests and routes before the origin sees them.

```typescript
// src/fa-router.ts
import { detectPersianLocale } from './fa-detect';

interface Env {
  ORIGIN: string;
}

export function buildPersianUrl(
  url: URL,
  locale: 'fa-IR' | 'fa-AF' | 'fa',
): URL {
  const out = new URL(url.toString());

  // Normalise path: /en/page -> /fa/page or /fa-af/page
  const segments = out.pathname.split('/').filter(Boolean);
  const localeSegments = ['en', 'ar', 'fr', 'de', 'fa', 'fa-ir', 'fa-af'];

  const prefix = locale === 'fa-AF' ? 'fa-af' : 'fa';

  if (segments[0] && localeSegments.includes(segments[0].toLowerCase())) {
    segments[0] = prefix;
  } else {
    segments.unshift(prefix);
  }

  out.pathname = '/' + segments.join('/');
  return out;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const persianLocale = detectPersianLocale(request);

    if (!persianLocale) {
      return fetch(new Request(url.toString(), request));
    }

    // Redirect to localised URL if not already on the Persian path
    const isOnPersianPath =
      url.pathname.startsWith('/fa/') ||
      url.pathname.startsWith('/fa-af/') ||
      url.pathname === '/fa' ||
      url.pathname === '/fa-af';

    if (!isOnPersianPath) {
      const localizedUrl = buildPersianUrl(url, persianLocale);
      return Response.redirect(localizedUrl.toString(), 302);
    }

    // Proxy to origin with RTL layout header
    const proxyReq = new Request(
      `${env.ORIGIN}${url.pathname}${url.search}`,
      request,
    );
    proxyReq.headers.set('X-Locale', persianLocale);
    proxyReq.headers.set('X-Text-Direction', 'rtl');

    return fetch(proxyReq);
  },
};
```

---

## 5. RTL HTML Injection for Persian Pages

```typescript
// src/fa-htmlrewriter.ts

export function applyPersianRTL(
  response: Response,
  locale: string,
): Response {
  const ct = response.headers.get('Content-Type') ?? '';
  if (!ct.includes('text/html')) return response;

  return new HTMLRewriter()
    .on('html', {
      element(el) {
        // Set RTL direction and Persian lang attribute
        el.setAttribute('dir', 'rtl');
        if (!el.getAttribute('lang')) {
          el.setAttribute('lang', locale);
        }
      },
    })
    .on('head', {
      element(el) {
        // Inject Persian font and RTL CSS
        el.append(
          `<link rel="preconnect" href="https://fonts.googleapis.com">` +
          `<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap" rel="stylesheet">` +
          `<style>body{font-family:'Vazirmatn',Tahoma,'Arial Unicode MS',sans-serif}</style>`,
          { html: true },
        );
      },
    })
    .transform(response);
}
```

---

## 6. KV-Based Locale Preference with Persian Defaults

```typescript
// src/fa-prefs.ts

export interface PersianPrefs {
  locale: 'fa-IR' | 'fa-AF';
  digitSystem: 'arabext' | 'latn';
  calendar: 'persian' | 'gregory';
}

const DEFAULTS: Record<string, PersianPrefs> = {
  'fa-IR': { locale: 'fa-IR', digitSystem: 'arabext', calendar: 'persian' },
  'fa-AF': { locale: 'fa-AF', digitSystem: 'arabext', calendar: 'persian' },
};

export async function getPersianPrefs(
  userId: string,
  locale: string,
  kv: KVNamespace,
): Promise<PersianPrefs> {
  const stored = await kv.get<PersianPrefs>(`prefs:${userId}`, 'json');
  if (stored) return stored;
  return DEFAULTS[locale] ?? DEFAULTS['fa-IR'];
}

export async function setPersianPrefs(
  userId: string,
  prefs: PersianPrefs,
  kv: KVNamespace,
): Promise<void> {
  await kv.put(`prefs:${userId}`, JSON.stringify(prefs), {
    expirationTtl: 60 * 60 * 24 * 365, // 1 year
  });
}
```

---

## Anti-patterns

- **Using `ar` locale for Persian content** — `ar` and `fa` share a script but have entirely different language data. `Intl.NumberFormat('ar')` returns Arabic-Indic digits and Arabic number grouping, which is wrong for Persian. Always use `fa` or `fa-IR`.
- **Conflating `fa-IR` and `fa-AF`** — Currency, time zone, and some vocabulary differ. Use geolocation to distinguish Iran vs Afghanistan before selecting the locale.
- **Redirecting Iranian users to `/ar/`** — Arabic and Persian are distinct languages. A Persian speaker cannot reliably read Arabic text.
- **Not setting `dir="rtl"` on `<html>`** — Persian is RTL at the document level. Without `dir="rtl"` on `<html>`, every flex container, text alignment, and scroll position defaults to LTR.
- **Using Gregorian calendar without user preference** — Iranian users expect Solar Hijri dates in official and consumer contexts. Default to `ca-persian` for `fa-IR`; offer a Gregorian toggle for technical contexts.

---

## Gotchas

- **IRR has no minor units**: The Iranian Rial (`IRR`) is the official currency but many Iranians quote prices in Tomans (1 Toman = 10 Rials). `Intl.NumberFormat` does not know about Tomans; if your product uses Tomans, store the value in Tomans and format as `IRR` divided by 10, or create a custom formatter.
- **Tehran DST**: Iran observes DST, advancing to UTC+4:30 in summer. `Asia/Tehran` in the IANA database handles this correctly. Do not hardcode UTC+3:30.
- **`fa-AF` ICU coverage**: CLDR data for `fa-AF` (Dari) is less complete than `fa-IR`. Some ICU builds fall back to `fa` for missing data. Test `Intl.DateTimeFormat('fa-AF')` output in the Worker runtime explicitly.
- **`prs` tag**: `prs` (ISO 639-3 for Dari) may appear in `Accept-Language` headers from Afghan browsers and software. Normalise to `fa-AF` before passing to Intl APIs, as `Intl` does not recognize `prs` in all environments.
- **Arabic vs Persian numerals**: Arabic uses `arab` (U+0660–U+0669); Persian uses `arabext` (U+06F0–U+06F9). They look similar but are different code points. ICU's `fa-IR` defaults to `arabext`. Explicitly pass `-u-nu-arabext` to avoid relying on ICU defaults that may change across versions.

---

## Verification

```typescript
// verify/fa.ts — deploy as Worker endpoint GET /verify-fa
export default {
  async fetch(): Promise<Response> {
    const checks: Record<string, unknown> = {
      // Persian digits
      num_arabext: new Intl.NumberFormat('fa-IR-u-nu-arabext').format(1234567),
      // Expected: "۱٬۲۳۴٬۵۶۷"

      // Gregorian date in Persian
      date_persian_cal: new Intl.DateTimeFormat(
        'fa-IR-u-ca-persian-nu-arabext',
        { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Tehran' },
      ).format(new Date('2026-08-06')),
      // Expected: "۱۵ مرداد ۱۴۰۵"

      // IRR currency
      currency_irr: new Intl.NumberFormat('fa-IR-u-nu-arabext', {
        style: 'currency', currency: 'IRR', minimumFractionDigits: 0,
      }).format(500000),

      // AFN currency
      currency_afn: new Intl.NumberFormat('fa-AF-u-nu-arabext', {
        style: 'currency', currency: 'AFN',
      }).format(1200.5),

      // RTL check
      direction: new Intl.Locale('fa-IR').textInfo?.direction,
      // Expected: "rtl"
    };
    return Response.json(checks);
  },
};
```

---

## Related

- `arabic-persian-text-rendering.md`
- `rtl-text-detection-workers-htmlrewriter.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `bidi-rtl-layout-css.md`
- `locale-url-routing-workers-middleware.md`
- `edge-timezone-detection-cf-object.md`
- `non-gregorian-calendars-eras-2026.md`

---

## Sources

- CLDR fa data: https://github.com/unicode-org/cldr/blob/main/common/main/fa.xml
- CLDR fa_AF data: https://github.com/unicode-org/cldr/blob/main/common/main/fa_AF.xml
- Unicode Extended Arabic-Indic digits U+06F0–U+06F9: https://www.unicode.org/charts/PDF/U0600.pdf
- IANA time zone Asia/Tehran: https://data.iana.org/time-zones/tzdb-latest.tar.lz
- Cloudflare Workers geolocation: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Solar Hijri calendar: https://en.wikipedia.org/wiki/Solar_Hijri_calendar
- Intl.Locale.prototype.textInfo: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/textInfo
- Persian (Farsi) BCP 47: https://www.rfc-editor.org/rfc/rfc5646
