# unicode-collation-2026

**Issue:** A team sorts customer names in their web app. They use JavaScript's default `Array.prototype.sort()`. The German umlauts sort after Z. The team ships a list where Müller appears after Schmidt. The list is wrong.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Default code-point sort is wrong for every locale. The 2026 fix is ICU Collator / `Intl.Collator` with the locale data backed by CLDR. The CLDR root collation is the UCA DUCET (Default Unicode Collation Element Table).

## Root cause

Strings sort by code point (UTF-16) in JavaScript, Python (default), and most languages. The result is wrong for almost every language:

- German umlauts (ä, ö, ü) sort after Z, but German dictionaries put them after a, o, u
- Chinese sorts by code point, but Chinese dictionaries sort by radical-stroke count
- Swedish places ä after z, but German places ä after a
- French secondary sort is from the last accent difference (Canadian French)

The 2026 fix: use locale-aware collator backed by CLDR.

## The Unicode Collation Algorithm (UCA)

UTS #10 defines the Unicode Collation Algorithm. The default collation is DUCET (Default Unicode Collation Element Table). CLDR provides 240+ locale-specific tailorings.

- **Levels** — primary (different base letters), secondary (accents), tertiary (case), quaternary (punctuation)
- **Strengths** — ICU/CLDR map levels to strengths (1, 2, 3, 4, identical)
- **Reorder** — parametric reordering of script groups (e.g., Greek before Latin)

The 2026 pattern: use the library's collator with the right locale; don't hand-roll.

## The Intl.Collator pattern

```javascript
// German: ä sorts with a (after a)
const collator = new Intl.Collator('de-DE', { sensitivity: 'base' });
['Müller', 'Schmidt', 'Äpfel'].sort(collator.compare);
// ["Äpfel", "Müller", "Schmidt"]

// Swedish: ä sorts after z
const svCollator = new Intl.Collator('sv-SE', { sensitivity: 'base' });
['Müller', 'Schmidt', 'Äpfel'].sort(svCollator.compare);
// ["Müller", "Schmidt", "Äpfel"]

// Default code-point sort: wrong for both
['Müller', 'Schmidt', 'Äpfel'].sort();
// ['Müller', 'Schmidt', 'Äpfel'] — Ä sorts after Z in code point

// Chinese: by radical-stroke (CLDR 46+ matches Unicode Radical-Stroke Index)
const zhCollator = new Intl.Collator('zh-Hans-CN');
// Sorts by radical + residual stroke count
```

`Intl.Collator` is Stage 4 in ECMA-402, Baseline 2026, supported in all major browsers and Node 16+.

## The 5 collation use cases

1. **Sort lists** — user-facing lists (names, products, search results)
2. **Search** — locale-aware substring matching
3. **Index headers** — alphabetic index labels (A, B, C, ... in user locale)
4. **Database sort** — SQL `ORDER BY` with collation (Postgres ICU, MySQL utf8mb4_unicode_ci)
5. **Grouping** — locale-aware grouping (e.g., all "ä" entries together)

The wrong tool for any of these: default code-point sort.

## The 4 collation strengths

| Strength | Level | What it differentiates | Use case |
|---|---|---|---|
| primary (1) | base letters | a vs b vs c | sort lists |
| secondary (2) | + accents | a vs á vs à | locale-aware sort |
| tertiary (3) | + case | a vs A | case-insensitive search |
| quaternary (4) | + punctuation | a vs a. vs a, | identical sort |
| identical | + Unicode variants | tie-breaker | deterministic sort |

`{ sensitivity: 'base' }` = primary; `'accent'` = secondary; `'case'` = tertiary; `'variant'` = quaternary.

## The 5 anti-patterns

1. **Default `Array.prototype.sort()`** — code-point sort; wrong for non-ASCII
2. **Hand-rolled locale rules** — fragile; CLDR has 240+ locales, more every release
3. **Converting to lowercase before sort** — collator's `caseFirst` option is the right tool
4. **No locale on the collator** — defaults to runtime locale, not content locale
5. **Database sort in code-point order** — `ORDER BY name` without collation clause; set the column collation

## The CLDR 46 root collation change

CLDR 46 (October 2024) aligned the root collation with the UCA DUCET, eliminating the historic divergence. The change:

- Non-decimal-digit numeric characters now sort after decimal digits
- CLDR no longer tailors currency symbols (some now sort like letter sequences)
- CJK radical-stroke order matches the Unicode Radical-Stroke Index (UAX #38)

The practical impact: the root collation in 2026 behaves like DUCET. Locale tailorings still apply on top.

## The ICU / Python / Java pattern

For backend, ICU, Python `pyuca`, Java `Collator` provide CLDR-backed collation.

```python
# Python with PyICU
import icu
collator = icu.Collator.createInstance(icu.Locale("de-DE"))
sorted_names = sorted(names, key=collator.getSortKey)

# Java
Collator collator = Collator.getInstance(new Locale("de", "DE"));
Collections.sort(names, collator);
```

The library handles locale-specific rules. The application sets the locale and the strength.

## The database collation pattern

For SQL `ORDER BY`, set the column collation.

```sql
-- PostgreSQL with ICU
CREATE TABLE users (
  name TEXT COLLATE "de-DE-x-icu"
);

-- MySQL
CREATE TABLE users (
  name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_de_pb_0900_ai_ci
);
```

The 2026 default for international apps: ICU collation in PostgreSQL, `utf8mb4_*_ai_ci` in MySQL.

## The search collation pattern

For search, the strength setting matters.

```javascript
// Case-insensitive, accent-insensitive search
const searchCollator = new Intl.Collator('de-DE', {
  sensitivity: 'base',
  usage: 'search'  // tie-breaker for ties
});
const matches = items.filter(item =>
  searchCollator.compare(item.name, query) === 0
);
```

`{ usage: 'search' }` uses a different tie-breaker rule than `'sort'`; the difference is subtle but documented.

## The 5 best practices

1. **Always pass a locale to the collator.** `new Intl.Collator()` defaults to runtime locale; `new Intl.Collator('de-DE')` uses German.
2. **Pick the right strength for the use case.** 'base' for case-insensitive lists; 'accent' for locale sort; 'variant' for identical.
3. **Use CLDR-backed data.** ICU, Intl APIs, `pyuca`, Java `Collator` all use CLDR.
4. **Set the database column collation.** `ORDER BY` without collation clause is locale-blind.
5. **Test with locale-specific strings.** Äpfel, naïve, Москва, 中文 — each tests a different collation rule.

## The 2026 tailwind

The 2026 default stack.

| Layer | Tool | Locale data |
|---|---|---|
| JavaScript | Intl.Collator | ECMA-402 + CLDR |
| Python | PyICU / pyuca | ICU + CLDR |
| Java | java.text.Collator | ICU + CLDR |
| PostgreSQL | ICU collation (pg_trgm) | ICU + CLDR |
| MySQL | utf8mb4_*_ai_ci | built-in |
| .NET | CompareInfo | CLDR |

All roads lead to CLDR. Pick the library; the data is the same.

## Verification

The tell that collation is real:

- `Intl.Collator` is used for any user-facing sort
- The collator is configured with a locale
- The strength matches the use case (base for case-insensitive, accent for locale sort)
- Database `ORDER BY` uses a collation clause
- Test cases cover locale-specific edge cases (ä, ñ, 漢, Я)

The tell it isn't:

- `Array.prototype.sort()` for user-facing lists
- `String.prototype.toLowerCase()` before sort
- `ORDER BY name` without collation clause
- Locale-agnostic sort of international data
- German umlauts sort after Z

## Gotchas

- **Default sort is locale-blind.** Always pass a locale.
- **Java's `Collator.getInstance()` defaults to default locale.** For user-specific locale, set explicitly.
- **Sensitivity 'base' is case- and accent-insensitive.** Use for search; use 'accent' or 'variant' for strict sort.
- **CLDR 46 changed the root collation.** Update your data and re-test.
- **The 4 strengths are not arbitrary.** Primary for letters, secondary for accents, tertiary for case, quaternary for punctuation.

## Related

- `i18n/cldr-data-2026.md` — CLDR backing data
- `i18n/Intl-PluralRules-2026.md` — plural categories
- `i18n/icu-message-format.md` — message format
- `i18n/locale-negotiation.md` — locale selection

## Source URLs (verified 2026-08-10)

- https://www.unicode.org/reports/tr35/tr35-collation.html — UTS #35 LDML Collation
- https://www.unicode.org/reports/tr10/ — UTS #10 UCA
- https://unicode-org.github.io/icu/userguide/collation/ — ICU collation
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator — Intl.Collator
- https://cldr.unicode.org/downloads/cldr-46 — CLDR 46 release notes
- https://cldr.unicode.org/index/cldr-spec/collation-guidelines — CLDR collation guidelines
- https://unicode-org.github.io/icu/userguide/collation/concepts.html — ICU collation concepts
- https://www.unicode.org/Public/UCA/6.2.0/CollationAuxiliary.html — UCA auxiliary files
