# CLDR Calendar Preference Data

Which calendar a user expects is not a global constant. Japan defaults to Gregorian for many contexts but has a live imperial calendar (`japanese`) for official and ceremonial dates; Thailand defaults to Buddhist (`buddhist`); Saudi Arabia historically preferred Islamic (`islamic-umalqura` for civil purposes in recent CLDR data); Iran uses Persian (`persian`); Ethiopia uses Ethiopic (`ethiopic` and `ethiopic-amete-alem`); Israel mixes Gregorian with Hebrew (`hebrew`) for religious contexts; Taiwan and Korea carry `roc` and `dangki` variants. CLDR publishes this per-territory preference ordering in supplemental `calendarData` and the related calendar preference list, and every product that renders dates for a global audience must either consult it or hardcode wrong defaults. The recurring incident: a date picker or invoice header shows Gregorian everywhere, or shows a non-Gregorian calendar to users who expected Gregorian, because the pipeline conflated locale language with calendar preference, which is territory-shaped data, not language-shaped.

## Scope

Covers reading CLDR supplemental calendar data, mapping territories to preferred calendar ordering, selecting a calendar for display via the locale identifier (`-u-ca-` keyword) or explicit formatter configuration, and persisting user calendar choice separately from locale. Applies to date formatting with ICU and ECMA-402 `Intl.DateTimeFormat`, calendar-aware date pickers, and record systems that store civil dates plus calendar display preferences. Out of scope: the arithmetic of each calendar system (epoch, month lengths, leap rules) and historical date conversion accuracy beyond display selection, both covered by calendar-specific articles in this leaf.

## Workflow or implementation guidance

Begin from data, not intuition. CLDR's supplemental data exposes per-territory calendar preference (historically as `calendarPreferenceData` in supplementalData.xml, with per-territory ordered lists like `gregorian buddhist` for TH or `gregorian japanese` style orderings for JP contexts) alongside `calendarData` elements carrying era and month-length facts for non-Gregorian calendars. Resolve the user's territory: from the region subtag of their locale if present, from likely-subtags maximization if not, or from an explicit country setting where the product has one. Then intersect the territory's preferred ordering with the calendars your runtime actually supports, and pick the first supported entry. Gregorian is the universal fallback because every territory list includes it somewhere and every implementation supports it.

Wire the selection through the standard keyword, not a branch. The `-u-ca-` extension subtag is the portable carrier: `th-TH-u-ca-buddhist`, `fa-IR-u-ca-persian`, `ar-SA-u-ca-islamic-umalqura`, `en-US-u-ca-gregorian`. In ECMA-402, `new Intl.DateTimeFormat('th-TH-u-ca-buddhist')` yields a formatter whose year is the Buddhist Era value, and `resolvedOptions().calendar` reports the resolved calendar so the choice is assertable. In ICU, `ucal_setAttribute` or the locale keyword achieves the same. Constructing the keyword rather than if/else chains means the choice flows through storage, logs, and APIs as part of the locale string, which is the unit every standards-compliant consumer already understands.

Persist preference separately from locale when users override. A Thai user in a `th` locale may still want Gregorian for a work tool; an Iranian user may want Gregorian for invoicing and Persian for personal dates. Store an explicit calendar setting keyed to the surface (default, per-feature overrides) and compose it into the locale at format time. Never derive calendar from the language subtag alone: `ar` spans territories with different defaults, `en` spans the world, and hardcoding `ar implies islamic` produces wrong output for Arabic speakers in nominally Gregorian territories.

Handle era display deliberately. Non-Gregorian calendars carry eras (Japanese imperial eras, Chinese and Korean eras, Ethiopian Amete Mihret versus Amete Alem). CLDR `calendarData` supplies the era definitions the formatter needs; your responsibility is deciding when to show the era and ensuring abbreviated era names are legible in the target width. Also pin the CLDR version: preference lists have changed between releases (most visibly around Islamic calendar adoption for Saudi civil use), so a deployment's behavior should be reproducible against the pinned CLDR release, and upgrades should diff the preference data.

Finally, convert at the boundary. Store instants or civil dates in a canonical form (UTC instant plus, where legally meaningful, the civil date in a named calendar), and convert to display calendars only at render time. Round-tripping a display string back into storage is where era ambiguity and year-boundary drift creep in.

## Controls

- Resolve the calendar from territory preference data intersected with supported calendars, with Gregorian as guaranteed fallback.
- Compose the selection into the locale string via `-u-ca-` and assert `resolvedOptions().calendar` in tests.
- Persist user calendar overrides as first-class settings per surface, never infer them from the language subtag.
- Store canonical instants or civil dates; convert to display calendars only at the edge.
- Pin the CLDR release and diff `calendarData` and calendar preference entries on upgrade.
- Test a matrix of territories (TH, SA, IR, ET, IL, JP, TW, KR, plus a Gregorian default) against expected default calendars.

## Validation evidence

Verified by resolving formatters for a fixed locale set and asserting the resolved calendar and formatted years. `new Intl.DateTimeFormat('th-TH').resolvedOptions().calendar` returns `buddhist` on runtimes carrying the territory default; `new Intl.DateTimeFormat('th-TH-u-ca-gregorian').resolvedOptions().calendar` returns `gregorian`, demonstrating the keyword overrides the default; `new Intl.DateTimeFormat('fa-IR-u-ca-persian')` formats a known instant with the Persian year offset rather than the Gregorian year. Territory preference orderings were read from the CLDR supplemental data in the pinned release rather than recalled from memory. Era presence was confirmed by formatting a date with era included for a Japanese-calendar locale and observing a non-Gregorian era designator in the output parts.

## Failure modes and correction

Buddhist year shown to a user expecting Gregorian: territory default won over user preference; add the explicit override setting and compose `-u-ca-gregorian`. Gregorian shown in Thailand by default: the pipeline stripped the region or the `-u-ca-` keyword during negotiation; preserve the full tag end to end. Islamic calendar shown for `ar` users in Europe: calendar inferred from language; key the default to territory instead. Year number correct but era wrong or missing for `japanese`: era width or display choice not configured; include era in the format options where the product contract requires it. Behavior changed after a dependency upgrade: CLDR preference data moved; pin the release and review the diff rather than trusting floating `latest`.

## Limitations

Calendar preference is civil-convention data and individuals legitimately deviate from territory defaults; treat the data as a default, not a mandate. Islamic calendar variants (observational versus tabular versus Umm al-Qura) are a domain where CLDR's chosen default may not match a specific institution's requirement. The article does not cover calendar arithmetic or historical conversion accuracy, only preference selection and display plumbing.

## Canonical sources

- Unicode CLDR LDML Part 4: Dates, calendar data and elements: https://unicode.org/reports/tr35/tr35-dates.html
- Unicode CLDR LDML Part 7: Default Data, calendar preference per territory: https://unicode.org/reports/tr35/tr35-info.html#Calendar_Data
- Unicode CLDR supplemental data repository including calendar data: https://github.com/unicode-org/cldr/blob/main/common/supplemental/supplementalData.xml
