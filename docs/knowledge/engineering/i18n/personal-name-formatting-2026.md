# personal-name-formatting-2026

**Issue:** A team stores user names as `first_name` + `last_name`. They display "John Smith" in the UI. A Chinese user enters their name as "李振藩" (surname Li, given Zhenfan). The UI shows "Zhenfan Li" or "John Smith" depending on assumptions. The name is wrong.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Name order, components, and formatting vary by culture. The 2026 fix is the Unicode Person Name Formats specification (UTS #35 Part 8, added to CLDR 42, refined in CLDR 43+) backed by ICU's PersonNameFormatter. The 2026 default: structured name fields, locale-aware formatting.

## Root cause

Name structure differs by culture:
- Western: given name(s) first, surname last (John Smith)
- East Asian: surname first, given name last (李振藩, 李 = surname)
- Hispanic: paternal + maternal surname, both used (Gabriel García Márquez)
- Indonesian: often single name (Sukarno)
- Arabic: given + father's name + family name; bin/bint separator (Fatima bint Yusuf)

Hardcoding "first_name + last_name" is wrong for most of the world.

## The 9 name fields (UTS #35 Part 8)

| Field | Description | Example |
|---|---|---|
| title | Honorific | Ms., Mr., Prof., Dr. |
| given | Primary given name | Sally, Mohan, Johnathan |
| given2 | Secondary given name(s) | Peter, Roland, S. |
| given-informal | Informal given | Sal, Mo, John |
| surname | Family name | Schmidt, Ramamurthy |
| surname2 | Secondary surname | Rivera, Garcia |
| generation | Generational suffix | Jr., Sr., III |
| credentials | Post-nominal | MBA, Esq., PhD, R.N. |

The schema is in CLDR 43+; ICU's PersonNameFormatter is the 2026 reference implementation.

## The 5 formatting orders

| Order | Example | Used in |
|---|---|---|
| `givenFirst` | "Charles Babbage" | English, French, German |
| `surnameFirst` | "Babbage Charles" | Japanese, Chinese, Korean, Hungarian |
| `sorting` | "Babbage, Charles" | library catalogs, sort by last name |
| `native` | "李振藩" | native script of the name's origin |
| `foreign` | "Zhenfan Li" | latinized version of a non-Western name |

The order is selected per (name locale, formatting locale) pair.

## The 4 name attributes

| Attribute | Values | Use |
|---|---|---|
| length | long, medium, short | "Charles Babbage" vs "C. Babbage" vs "Babbage" |
| usage | addressing, referring, sorting | "Dear Dr. Smith" vs "Dr. Smith" vs "Smith, Dr." |
| style | formal, informal | "Dr. Charles Babbage" vs "Charlie" |
| formality | formal, informal | (deprecated, replaced by style) |

The formatter takes (name, formatting locale, length, usage, style) and produces the right format.

## The CLDR 43+ patterns

The 2026 production formatter.

```java
// ICU 73+ PersonNameFormatter
import com.ibm.icu.text.PersonNameFormatter;
import com.ibm.icu.text.PersonName;

PersonName name = PersonName.builder()
    .setGiven("Charles")
    .setSurname("Babbage")
    .setNameLocale(Locale.US)
    .build();

PersonNameFormatter formatter = PersonNameFormatter.builder()
    .setLocale(Locale.JAPAN)  // formatting locale
    .setLength(PersonNameFormatter.Length.MEDIUM)
    .setUsage(PersonNameFormatter.Usage.REFERRING)
    .setStyle(PersonNameFormatter.Style.FORMAL)
    .build();

String formatted = formatter.format(name);
// For Japanese formatting locale with US name:
// Uses surnameFirst if the name locale (US) matches a "surnameFirst" rule, else givenFirst
```

The 4 name attributes and the (name locale, formatting locale) pair determine the output.

## The 5 cultural conventions

| Culture | Default order | Example |
|---|---|---|
| Western (en, fr, de) | givenFirst | "John Smith" |
| East Asian (ja, zh, ko) | surnameFirst | "田中 太郎" |
| Hispanic (es, pt) | givenFirst + double surname | "Juan García López" |
| Hungarian (hu) | surnameFirst | "Babbage Charles" |
| Icelandic (is) | givenFirst (patronymic) | "Jón Gunnarsson" |

The 5 conventions are encoded in CLDR per locale.

## The 5 best practices

1. **Store name as structured fields, not a string.** given, surname, given2, surname2, title, generation, credentials, name locale.
2. **Store the name locale.** "Zhenfan Li" with `nameLocale=zh-Hans` displays differently than with `nameLocale=en-US`.
3. **Format per the formatting locale.** Japanese UI for "John Smith" shows "Smith John" if the name is from a `surnameFirst` culture.
4. **Support double surnames.** Hispanic names have two surnames; the pattern must hold both.
5. **Use ICU PersonNameFormatter or equivalent.** Don't hand-roll locale-specific rules.

## The 5 anti-patterns

1. **Single `name` string.** Loses structure; impossible to format correctly per locale.
2. **`first_name` + `last_name` only.** Misses double surnames, generation, credentials, title.
3. **Forcing Western order on East Asian names.** "Zhenfan Li" for a Chinese user is wrong; "李振藩" or "Li Zhenfan" is right.
4. **No name locale stored.** Can't distinguish "John Smith" (English name) from "John Smith" (Latin transliteration of a Chinese name).
5. **Hand-rolled name formatting.** CLDR has 240+ locales; the library handles them.

## The data model pattern

```typescript
interface PersonName {
  title?: string;          // Dr., Prof., Mr.
  given?: string;          // primary given
  given2?: string;         // secondary given
  givenInformal?: string;  // informal given
  surname?: string;        // family name
  surname2?: string;       // secondary family name (Hispanic)
  generation?: string;     // Jr., Sr., III
  credentials?: string;    // MBA, PhD, R.N.
  nameLocale: string;      // BCP 47 locale of the name, e.g. "en-US", "zh-Hans"
  preferredOrder?: 'givenFirst' | 'surnameFirst';  // optional override
}
```

The 8 fields + name locale + optional preferredOrder covers the 2026 international name space.

## The 5 display scenarios

| Scenario | Length | Usage | Style | Example |
|---|---|---|---|---|
| Salutation | long | addressing | formal | "Dear Dr. Charles Babbage" |
| Profile | medium | referring | formal | "Charles Babbage" |
| Mention | short | referring | formal | "C. Babbage" |
| Casual | short | referring | informal | "Charlie" |
| Sortable | medium | sorting | formal | "Babbage, Charles" |

The 5 scenarios map to the 4 attributes. Most UIs use (medium, referring, formal) as the default.

## The ICU / Java vs JavaScript pattern

| Language | Library | Status |
|---|---|---|
| Java | ICU 73+ PersonNameFormatter | stable, draft status |
| JavaScript | intl-nameformat (npm, partial CLDR support) | community port |
| Python | not native; partial via pyicu | limited |
| Swift | Foundation PersonNameComponents | basic; no CLDR integration |

The 2026 default: Java backend uses ICU; web frontend uses `intl-nameformat`. Server-rendered name formatting is the production pattern.

## The 4-step migration

For a team migrating from `first_name + last_name` to structured names:

1. **Add the new fields** to the data model (don't remove old)
2. **Dual-write** — populate new fields from old on save
3. **Display via PersonNameFormatter** — show formatted name, store as fallback
4. **Backfill** — gradually migrate old data via heuristics (last word = surname in en-US, first word = surname in zh-Hans, etc.)

The migration takes 1-2 quarters; the data correctness lasts forever.

## Verification

The tell that personal names are handled:

- Name is stored as structured fields, not a string
- The name locale is stored alongside the name
- ICU PersonNameFormatter (or equivalent) is used
- Double surnames are supported
- Per-locale formatting is in the UI

The tell it isn't:

- Single `name` string
- `first_name` + `last_name` only
- No name locale stored
- Hand-rolled locale-specific formatting
- "John Smith" for a Chinese user

## Gotchas

- **The name locale matters more than the formatting locale.** "Zhenfan Li" formatted in Japanese UI shows surnameFirst because the name is from a surnameFirst culture.
- **Double surnames are common in Hispanic cultures.** García Márquez = paternal García + maternal Márquez; both are part of the legal name.
- **Generational suffixes (Jr., Sr., III) are part of the name, not the title.** Different from credentials (post-nominal).
- **Credentials placement varies.** Western: "Charles Babbage, PhD" (suffix). Some cultures: prefix.
- **No "middle name" in CLDR.** Use `given2` for middle names; the order is locale-aware.

## Related

- `i18n/international-address-2026.md` — address formatting
- `i18n/cldr-data-2026.md` — CLDR backing data
- `i18n/icu-message-format.md` — message format
- `i18n/unicode-collation-2026.md` — sort order (different from name order)

## Source URLs (verified 2026-08-10)

- https://www.unicode.org/reports/tr35/tr35-personNames.html — UTS #35 Part 8 Person Names
- https://www.unicode.org/media/CLDR_Person_Name_White_Paper_June%202023.pdf — CLDR Person Name White Paper
- https://cldr.unicode.org/translation/miscellaneous-person-name-formats — CLDR Person Name Guide
- https://unicode-org.github.io/icu/userguide/format_parse/personnames/ — ICU PersonNameFormatter
- https://cldr.unicode.org/downloads/cldr-43 — CLDR 43 release notes
- https://www.npmjs.com/package/intl-nameformat — JS intl-nameformat
- https://developer.apple.com/documentation/foundation/personnamecomponents — Apple Foundation
- https://utw2025.unicode.org/events/utw/2023/documents/slides/2023_11_McKennaMichael_UTW-PersonNamesRealWorld.pdf — UTW 2023 talk
