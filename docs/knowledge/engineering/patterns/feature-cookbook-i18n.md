# feature-cookbook-i18n

**Issue:** Internationalization — 20 locales, RTL, ICU
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship an app in English. You add Spanish. The text
fits in Spanish (longer words). You add German. Some
strings are 30% longer. The layout breaks. You add
Arabic. The right-to-left layout breaks. You wish you'd
designed for i18n from day 1.

## Root cause
**i18n is hard.** Each locale has different rules. Build
for it from the start.

**Source:** Unicode CLDR:
https://cldr.unicode.org/

## The "locale detection" pattern

Detect the user's locale:
```ts
function getUserLocale(request: Request, user: User | null): string {
  // 1. User preference (if logged in)
  if (user?.locale) return user.locale;

  // 2. Cookie (if set)
  const cookie = parseCookie(request.headers.get('Cookie') ?? '');
  if (cookie.locale) return cookie.locale;

  // 3. Accept-Language header
  const acceptLanguage = request.headers.get('Accept-Language') ?? 'en';
  const preferred = acceptLanguage.split(',')[0].split(';')[0].toLowerCase();
  const supported = ['en', 'es', 'ar', 'ja', 'de', 'fr', 'ru', 'zh-CN'];
  if (supported.includes(preferred)) return preferred;

  // 4. Default
  return 'en';
}
```

The locale is determined from the most specific source.

## The "i18next" pattern

For 20 locales, use i18next:
```ts
import i18next from 'i18next';
import enMessages from './locales/en.json';
import esMessages from './locales/es.json';
// ... 20 locales

await i18next.init({
  resources: {
    en: { translation: enMessages },
    es: { translation: esMessages },
    // ...
  },
  lng: 'en',  // Default; set per request
  fallbackLng: 'en',
  interpolation: { escapeValue: false },  // React handles XSS
});
```

The library handles fallback, interpolation, plurals.

## The "ICU MessageFormat" pattern

For complex messages, use ICU:
```json
{
  "greeting": "Hello, {name}!",
  "items": "{count, plural, =0 {No items} one {1 item} other {# items}}",
  "last_seen": "{date, date, medium}"
}
```

The ICU format supports plural, gender, date formatting.

## The "plural rules" pattern

For plural, use the locale's rules:
```ts
// English: one, other
// "1 item" / "2 items" / "0 items"

// Arabic: zero, one, two, few, many, other
// "صفر عناصر" / "عنصر واحد" / "عنصران" / "أقل من 10" / "أكثر من 10" / "باقي"

// Russian: one, few, many, other
// "1 товар" / "2 товара" / "5 товаров" / "21 товар"

import { pluralRules } from 'intl-pluralrules';
const pr = new pluralRules('ar');
const cat = pr.select(0);  // 'zero'
const cat2 = pr.select(1);  // 'one'
```

For 20 locales, use a library that handles the rules.

## The "RTL" pattern

For RTL languages (Arabic, Hebrew, Persian, Urdu):
```css
[dir="rtl"] {
  /* Override styles */
}

[dir="rtl"] .icon-arrow {
  transform: scaleX(-1);  /* Mirror the icon */
}
```

```tsx
<div dir={isRTL(locale) ? 'rtl' : 'ltr'}>
  {/* Content */}
</div>
```

The direction is set on the root element.

## The "date and number" pattern

For locale-aware formatting:
```ts
import { DateTime } from 'luxon';

const dt = DateTime.fromISO('2026-08-09T14:30:00Z').setLocale('ar-SA');
console.log(dt.toLocaleString(DateTime.DATETIME_MED));
// "9 أغسطس 2026"

// Number
console.log(new Intl.NumberFormat('ar-SA').format(1234.56));
// "١٬٢٣٤٫٥٦"
```

Use `Intl.DateTimeFormat` and `Intl.NumberFormat` for
locale-aware formatting.

## The "currency" pattern

For currency, use Intl.NumberFormat:
```ts
const amount = 99.99;
const formatted = new Intl.NumberFormat(locale, {
  style: 'currency',
  currency: 'USD',
}).format(amount);
// "99.99 $" in en-US
// "99,99 $US" in fr-FR
// "US$ 99,99" in de-DE
```

The currency is formatted per the locale.

## The "translation file" pattern

For each locale, a JSON file:
```
locales/
├── en.json
├── es.json
├── ar.json
├── ja.json
└── ... 20 files
```

```json
// en.json
{
  "app.title": "My App",
  "user.greeting": "Hello, {name}!",
  "user.items_count": "{count, plural, =0 {No items} one {1 item} other {# items}}"
}
```

The keys are stable; the values are translated.

## The "missing translation" pattern

For missing translations, fall back:
```ts
function translate(key: string, locale: string): string {
  const messages = locales[locale] ?? locales.en;
  return messages[key] ?? locales.en[key] ?? key;
}
```

A missing translation falls back to English; if not in
English, the key is returned (visible in the UI).

## The "translation review" pattern

For translation review, use a translation service:
- **Crowdin:** https://crowdin.com/
- **Lokalise:** https://lokalise.com/
- **Transifex:** https://www.transifex.com/

The service has a UI for translators; the JSON is
auto-generated.

## The "RTL-safe icons" pattern

For icons, mirror in RTL:
```css
[dir="rtl"] .icon-back {
  transform: scaleX(-1);
}
```

Or use CSS logical properties:
```css
.icon-arrow {
  margin-inline-start: 0.5rem;  /* Works in LTR and RTL */
}
```

## The "translation test" pattern

For each locale, test that:
- All keys are present
- No English leaks (e.g. "Submit" instead of "Enviar")
- Layout doesn't break

```ts
test('all locales have all keys', () => {
  const enKeys = Object.keys(enMessages);
  for (const locale of Object.keys(locales)) {
    const messages = locales[locale];
    for (const key of enKeys) {
      expect(messages).toHaveProperty(key);
    }
  }
});
```

## The "locale switcher" pattern

For the UI, a locale switcher:
```tsx
function LocaleSwitcher() {
  const [locale, setLocale] = useState(getCurrentLocale());

  const handleChange = (newLocale: string) => {
    setLocale(newLocale);
    document.cookie = `locale=${newLocale}; Path=/; Max-Age=31536000`;
    location.reload();
  };

  return (
    <select value={locale} onChange={(e) => handleChange(e.target.value)}>
      <option value="en">English</option>
      <option value="es">Español</option>
      <option value="ar">العربية</option>
      {/* ... 20 options */}
    </select>
  );
}
```

The user can switch; the choice is persisted.

## The "i18n SEO" pattern

For SEO, use the lang attribute:
```html
<html lang="en">
  <head>
    <link rel="alternate" hreflang="en" href="https://example.com/en/page" />
    <link rel="alternate" hreflang="es" href="https://example.com/es/page" />
    <link rel="alternate" hreflang="ar" href="https://example.com/ar/page" />
  </head>
</html>
```

The hreflang tags tell Google about the alternates.

## The "RTL + components" pattern

For RTL-safe components:
- Use `margin-inline-start` instead of `margin-left`
- Use `padding-inline-end` instead of `padding-right`
- Use `text-align: start` instead of `text-align: left`
- Use `inset-inline-start` instead of `left`

```css
.card {
  margin-inline-start: 1rem;  /* LTR: 1rem on the left, RTL: 1rem on the right */
  text-align: start;
}
```

## Verification
- **Test:** Each locale has the right keys
- **Test:** Layout doesn't break in any locale
- **Live:** User locale is detected correctly
- **Audit:** Quarterly review of translations

## Gotchas
- **The "no fallback" anti-pattern.** A missing translation
  shows the key; not good. Always have a fallback.
- **The "no RTL support" anti-pattern.** Adding Arabic
  later requires flipping the entire layout. Plan for it.
- **The "string concatenation" anti-pattern.** "Hello, " +
  name + "!" doesn't work in all languages. Use
  interpolation.
- **The "no plural support" anti-pattern.** "1 items" is
  wrong. Use ICU.
- **The "date without timezone" anti-pattern.** A date
  without a timezone is ambiguous. Always include the
  timezone.
- **The "translation by developers" anti-pattern.** Native
  speakers translate; developers review.

## Related
- `i18n/icu-messageformat-advanced.md`
- `i18n/icu-plural-rules-20-locales.md`
- `i18n/rtl-safe-component-patterns.md`
- `i18n/date-and-number-formatting.md`
- `i18n/data-i18n-marker-pattern.md`
- `i18n/locale-fallback-chain.md`
- `i18n/brand-literals-stay-english.md`
- i18next: https://www.i18next.com/
- FormatJS: https://formatjs.io/
- CLDR: https://cldr.unicode.org/
