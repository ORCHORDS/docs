# i18n-internationalization-architecture

**Issue:** Internationalization fails when treated as a late translation pass. String concatenation ("You have " + n + " items") breaks the moment a language needs different word order, plural rules, or gender agreement; hardcoded dates and numbers confuse users; English-length assumptions overflow layouts; and RTL locales mirror half the UI because spacing was written with physical properties. Retrofitting all of this after launch costs multiples of designing for it. The 2025-2026 frontend stack has converged on solid answers: ICU MessageFormat for grammatically correct messages, type-safe key systems (next-intl typegen, Lingui macros, Paraglide JS) that make missing keys and wrong arguments compile errors, native Intl APIs for formatting, and pseudo-localization as the cheapest high-value test for catching overflow and hardcoded strings before translators are ever involved.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Message authoring

1. **ICU MessageFormat for anything with structure.** Plurals, select (gender), selectordinal, and nested messages must be written in ICU syntax (for example {count, plural, one {# item} other {# items}}) rather than template interpolation — ad-hoc templating cannot express the six Croatian plural forms or Arabic duals, and machine-translating mangled syntax produces garbage. react-intl, next-intl, Lingui, and FormatJS all speak ICU.
2. **Semantic, structured keys, not source strings.** Key messages by namespace and intent (checkout.errors.card_declined) rather than using the English string as the key — rewording English then becomes a content change, not a migration of every locale file.
3. **Complete sentences as translation units.** Translators translate whole sentences, not fragments to be concatenated. If a sentence contains dynamic values, keep the structure inside one message with placeholders, never compose sentences from parts in code.
4. **Never format inside translation strings.** Values like dates, currency, and names go through Intl formatters (Intl.NumberFormat, Intl.DateTimeFormat, Intl.RelativeTimeFormat, Intl.ListFormat) with the active locale — hand-rolled formatting is always wrong somewhere.
5. **Metadata in descriptions.** Every message carries a developer note (context, character limits, tone) that translators read; a bare string with no context is where mistranslations breed.

## Type-safe keys and arguments

1. **Generate types from the source locale.** The modern pattern (next-intl's global type generation, typesafe-i18n, Paraglide JS) watches your default-locale messages and generates TypeScript types so t() calls validate both key existence and argument types at compile time — typos in keys stop being runtime blanks.
2. **Lingui macros for extraction.** Lingui's compile-time macros (t, plural, select) extract messages from source and type-check interpolated values, while shipping messages in industry-standard PO format that translation vendors already tool for.
3. **One source of truth, generated everything else.** Keys should live in message files (or extracted via macros), and TypeScript types, key constants, and docs should be generated artifacts — hand-maintained key enums diverge from reality within a sprint.
4. **Enforce completeness in CI.** A check that every locale file contains every key of the source locale (allowing a documented fallback list) fails PRs that ship untranslated screens silently; untranslated keys falling back to English are acceptable only when deliberate and visible.
5. **Argument inference.** The strongest setups (next-intl strict typing, Paraglide, typesafe-i18n) infer ICU argument types — a message declaring {count, plural, ...} requires a numeric count argument at the call site. Prefer this over passing untyped objects.

## Loading and runtime architecture

1. **Lazy locale bundles.** Ship only the active locale's messages per route; bundling all locales into the main chunk penalizes every user for languages they do not read. Dynamic import per locale (and per route namespace for large apps) keeps bundles bounded.
2. **Locale detection and routing.** Resolve locale from the URL path or subdomain (SEO-correct, shareable), with cookie memory for returning users and Accept-Language as a first-visit fallback — never auto-redirect away from an explicitly requested locale.
3. **Negotiate regional variants deliberately.** Support few locales done well (en, de, fr) rather than many half-done; regional variants (pt-BR versus pt-PT) can fall back along a chain with the fallback documented in code.
4. **Hydration consistency.** The server and client must render the same locale: resolve locale on the server, embed the chosen locale and its messages in the initial payload, and never let the client re-detect into a different locale mid-hydration.
5. **Time zones are not locales.** Persist and transmit timestamps in UTC or epoch millis; format to the user's timezone in the UI. Storing localized strings is a data-corruption bug.

## RTL and layout readiness

1. **dir attribute on the root.** Set dir="rtl" (or "auto") on the html element per locale and let the browser's bidi algorithm do the baseline mirroring; never flip layouts by hand with CSS transforms or JS conditionals.
2. **Logical CSS properties everywhere.** Use margin-inline, padding-block, inset-inline-start, border-inline-end, and text-align: start instead of left/right physical properties — the layout mirrors automatically. Physical values remain only for genuinely directional decoration.
3. **Direction-aware icons.** Icons implying motion (arrows, chevrons, progress) must flip in RTL via transform scaleX(-1) or directional icon variants; icons that must not flip (media playback, logos) are marked explicitly.
4. **Pseudo-RTL locale for testing.** A fake RTL locale (English with mirroring enabled) lets any developer exercise mirrored layouts without Arabic/Hebrew knowledge — pair it with pseudo-localization for full coverage.
5. **Bidi isolation for mixed content.** User-generated or data-driven strings embedded into localized UI need unicode-bidi isolation (CSS unicode-bidi: isolate or the bdi element) so an English username inside an Arabic sentence cannot scramble the line.

## Testing and workflow

1. **Pseudo-localization as the first test.** Transform source strings into padded, accented pseudo-text (and a length expansion factor) in a dev-only locale: it catches truncation, overflow, hardcoded strings, and broken layouts before any translator is hired — consistently recommended as the highest-value automated i18n check.
2. **Screenshot tests per direction and length.** Visual regression on key screens in at least three variants — source locale, pseudo-localized (long strings), and pseudo-RTL — catches the majority of i18n layout bugs in CI.
3. **Unit-test message rendering edge cases.** Test ICU messages with the boundary plural counts (0, 1, 2, and the locale's plural-rule boundaries), empty values, and long interpolations.
4. **Translation workflow with guardrails.** Use a TMS or structured file workflow where translators never touch code; validate round-tripped files against the source schema in CI (parse errors, broken ICU, missing placeholders) before merge.
5. **Machine translation with human review.** MT is acceptable for first drafts in 2025 toolchains, but never machine-translate ICU messages with embedded syntax unparsed, and never ship MT output unreviewed for user-facing legal or payment flows.
