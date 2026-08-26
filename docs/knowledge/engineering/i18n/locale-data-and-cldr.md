# locale-data-and-cldr

**Issue:** Locale data — CLDR, dates, numbers, plurals
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a French user. You show them "1 items."
You show them "1/8/2026" (US format) when it's
"8/1/2026" (FR format). You show them $10.00 when
they expect 10,00 €. The user is confused.

## Root cause
**Locale data is specific.** Use CLDR.

**Source:** CLDR:
https://cldr.unicode.org/

## The "CLDR" concept

CLDR (Common Locale Data Repository) provides locale
data for:
- **Date formats:** "1/8/2026" vs "8/1/2026"
- **Time formats:** "1:00 PM" vs "13:00"
- **Number formats:** "1,000.00" vs "1 000,00"
- **Currency:** "$10.00" vs "10,00 €"
- **Plural rules:** 1 item, 2 items, 5 items
- **Names:** "January" vs "Janvier"
- **Sort order:** "ä" vs "a" + "e"

CLDR is the standard.

## The "Intl" pattern

For Intl (built into JS):
```ts
// Date
const date = new Date();
new Intl.DateTimeFormat('fr-FR').format(date);  // "08/01/2026"
new Intl.DateTimeFormat('en-US').format(date);  // "1/8/2026"

// Number
new Intl.NumberFormat('fr-FR').format(1234.56);  // "1 234,56"
new Intl.NumberFormat('en-US').format(1234.56);  // "1,234.56"

// Currency
new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(10);  // "10,00 €"
new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(10);  // "$10.00"

// Relative time
const rtf = new Intl.RelativeTimeFormat('fr-FR', { numeric: 'auto' });
rtf.format(-1, 'day');  // "hier"
rtf.format(1, 'day');  // "demain"

// List
const list = new Intl.ListFormat('fr-FR');
list.format(['Alice', 'Bob', 'Charlie']);  // "Alice, Bob et Charlie"

// Plural
new Intl.PluralRules('fr-FR').select(1);  // "one"
new Intl.PluralRules('fr-FR').select(5);  // "other"
```

The Intl API is built-in.

**Source:** MDN Intl:
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl

## The "date-fns / dayjs" pattern

For a library:
- **date-fns:** Tree-shakeable, immutable
- **dayjs:** Moment.js-like, small
- **luxon:** Powerful, immutable

```ts
import { format } from 'date-fns';
import { fr } from 'date-fns/locale';

format(new Date(), 'PPP', { locale: fr });  // "8 janvier 2026"
```

The library handles locales.

## The "ICU MessageFormat" pattern

For ICU MessageFormat:
```ts
import { IntlMessageFormat } from 'icu-messageformat';

const mf = new IntlMessageFormat(
  '{count, plural, one {# message} other {# messages}}',
  'en',
);

mf.format({ count: 1 });  // "1 message"
mf.format({ count: 5 });  // "5 messages"
```

The ICU handles plurals.

**Source:** ICU MessageFormat:
https://messageformat.unicode.org/

## The "plural rules" pattern

For plural rules:
- **English:** one, other
- **French:** one (0, 1), many (10^6+), other
- **Russian:** one, few, many, other
- **Arabic:** zero, one, two, few, many, other
- **Chinese:** other (no plural)

```ts
const rules = new Intl.PluralRules('ru-RU');
rules.select(1);  // "one"
rules.select(2);  // "few"
rules.select(5);  // "many"
rules.select(21);  // "one"
```

The rules are locale-specific.

## The "currency" pattern

For currency:
```ts
new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(1000);  // "￥1,000"
new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(1000);  // "1.000,00 €"
new Intl.NumberFormat('ar-EG', { style: 'currency', currency: 'EGP' }).format(1000);  // "١٬٠٠٠٫٠٠ ج.م."
```

The currency is localized.

## The "first day of week" pattern

For the first day of the week:
- **Sunday:** US, Canada
- **Monday:** EU, most of the world
- **Saturday:** Some Middle East

```ts
new Intl.Locale('en-US').getWeekInfo();  // { firstDay: 7 }  // Sunday
new Intl.Locale('fr-FR').getWeekInfo();  // { firstDay: 1 }  // Monday
```

The first day is locale-specific.

## The "calendar" pattern

For the calendar:
- **Gregorian:** Most of the world
- **Islamic:** Saudi Arabia
- **Hebrew:** Israel
- **Japanese:** Japan
- **Buddhist:** Thailand

```ts
new Intl.DateTimeFormat('ar-SA', { calendar: 'islamic' }).format(new Date());
```

The calendar is locale-specific.

## The "name order" pattern

For the name order:
- **Given Last:** US, EU
- **Family First:** Japan, China, Korea, Hungary

```ts
new Intl.DisplayNames('ja-JP', { type: 'name' }).of('Alice Smith');  // "スミス・アリス" (Family Given)
```

The name order is locale-specific.

## The "address format" pattern

For the address format:
- **Big-endian:** US (Street, City, State, Zip)
- **Little-endian:** EU (Street, Zip, City, Country)
- **Big-endian:** Asia (Zip, State, City, Street)

The address format is locale-specific.

## The "phone format" pattern

For the phone:
- **US:** +1 (555) 123-4567
- **UK:** +44 20 1234 5678
- **FR:** +33 1 23 45 67 89
- **JP:** +81 3-1234-5678

The phone is locale-specific.

## The "i18n anti-pattern" anti-patterns

### 1. Hard-coded English
- **Issue:** Not localized
- **Fix:** Use translation keys

### 2. Date without locale
- **Issue:** Wrong format
- **Fix:** Intl.DateTimeFormat

### 3. Number without locale
- **Issue:** Wrong decimal
- **Fix:** Intl.NumberFormat

### 4. Hard-coded plural
- **Issue:** Wrong for many locales
- **Fix:** ICU MessageFormat

### 5. Currency without locale
- **Issue:** Wrong symbol + format
- **Fix:** Intl.NumberFormat with currency

## Verification
- **Test:** Each locale renders correctly
- **Test:** Plurals are correct
- **Test:** Dates are formatted
- **Live:** Locale coverage is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "hard-coded English" anti-pattern.** Use keys.
- **The "date without locale" anti-pattern.** Intl.
- **The "no plural" anti-pattern.** ICU.

## Related
- `icu-messageformat-advanced.md`
- `icu-plural-rules-20-locales.md`
- `date-and-number-formatting.md`
- `locale-fallback-chain.md`
- `feature-cookbook-localization.md`
- CLDR: https://cldr.unicode.org/
- ICU: https://icu.unicode.org/
- Intl: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
