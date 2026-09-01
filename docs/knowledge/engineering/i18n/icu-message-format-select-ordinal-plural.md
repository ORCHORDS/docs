# ICU MessageFormat Select, Ordinal, and Plural Constructs

Translating a sentence with a variable is not string substitution. The count "1 file" versus "2 files" needs different forms in English, Polish needs several plural forms, Arabic needs six categories, and some sentences switch whole words depending on gender or ordinal position ("you came first" versus "third"). ICU MessageFormat exists because these decisions belong in the translation file, not in application code. This article covers the `plural`, `select`, `selectordinal`, and nested-argument constructs, correct usage patterns, and the defects that appear when teams treat messages as templates.

## Scope

This article addresses ICU MessageFormat syntax as used in translation catalogs: `{count, plural, …}` with `=exact`, `zero`, `one`, `two`, `few`, `many`, `other` options; `{who, select, …}` for discrete choices; `{n, selectordinal, …}` for ordinal categories; nested sub-messages; and the `offset` clause. It covers API usage and validation. It does not cover the full ICU4J/ICU4C API surface, Fluent/Gettext alternatives, or machine-translation workflows.

## Workflow or implementation guidance

A MessageFormat string is a pattern with placeholders. Numeric placeholders can be `plural` or `selectordinal`; string placeholders can be `select`. The runtime picks a clause by computing the operand's plural category through CLDR plural rules for the active locale, or by matching an explicit `=value` clause first.

Key mechanics:

1. **Plural categories are locale-dependent.** English maps 1 → `one`, everything else → `other`. Polish uses `one`, `few`, `many`, `other` with rules keyed on the number's last digits. Arabic uses six categories. The clause names in the message are fixed; the mapping from number to category comes from CLDR via the runtime. This means an English source message with `one`/`other` is structurally valid for every locale; the French translator adds clauses as their language requires, and the harness warns when a locale's rules can select a category the message does not define.
2. **`select` is for closed sets.** Use it for gendered participant roles, casing states, formality registers (`{name, select, informal{…} formal{…}}`), never for open-ended values; a `select` without a matching option falls through to an error or `other`-like default depending on implementation, so every `select` must define the exhaustive option list plus a fallback.
3. **`selectordinal` uses ordinal categories.** English `1st/2nd/3rd/4th` becomes `{n, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}`. The categories again come from CLDR ordinal rules (English `one`=1, `two`=2, `few`=3, everything else `other`); they are not the same as cardinal plural categories, which is a classic source of wrong suffixes.
4. **`#` refers to the formatted number.** Inside a plural clause, `#` re-renders the operand with locale formatting (grouping, native digits under `-u-nu-` extensions). A literal `{count}` also works but does not inherit the plural operand's formatting context the same way in all runtimes; prefer `#` inside plural clauses.
5. **`offset` shifts category selection.** `{count, plural, offset:1 =0 {nobody} =1 {you} one {you and one other} other {you and # others}}` demonstrates the pattern for "X and Y others" strings, where category rules must apply to `count - offset`.
6. **Nesting composes.** A clause body is itself a message and may contain further placeholders, selects, and plurals. Deep nesting is legal but harms translator clarity; extract when clauses grow past one sentence.

A worked example, user-facing notification:

```
unread_banner: {count, plural,
  =0 {No unread messages}
  one {# unread message}
  other {# unread messages}}
```

The Polish translation supplies `one {# nieprzeczytana wiadomość}`, `few {# nieprzeczytane wiadomości}`, `many {# nieprzeczytanych wiadomości}`, `other {…}`. The application passes only the number; no branching code exists for any locale.

The cardinal sin this construct eliminates is code like `if (count === 1) msg = "1 message" else msg = count + " messages"` — which cannot be translated to Polish at all, because the boundary logic lives in the wrong place. Related anti-patterns: building keys like `messages.one`/`messages.other` in application logic (moves CLDR rules into code, per locale), and using `plural` for non-numeric choices (a `select`).

Fallback behavior deserves testing: when a runtime meets a number whose category is missing from the message, conforming implementations fall back to `other` (ICU4J throws in some strict configurations; web runtimes vary). Catalog tooling should therefore lint every translated message for category coverage against the locale's CLDR plural rule outcomes across a sample of numbers (0–10, 100, 1.5).

## Controls

- Lint translation catalogs at build time: parse each message, verify balanced braces, verify `plural`/`selectordinal` messages define at minimum the categories the locale's rules can produce plus `other`, and verify every `select` has a default option.
- Snapshot-render each message with a matrix of operands per locale (for Arabic: 0, 1, 2, 3, 11, 100, 101, 2.5) to freeze expected outputs at the pinned ICU/CLDR version.
- Keep plural operand values as numbers passed to the formatter, never pre-formatted strings; pre-formatting breaks category computation.
- Code-review rule: forbid `=== 1` string-selection logic in application code; the branch belongs in the message.
- Version and changelog the message catalog schema (ICU MessageFormat level, e.g., MessageFormat 1 syntax versus the newer MessageFormat 2) so tooling and runtimes agree.

## Validation evidence

- The `plural`, `select`, `selectordinal`, `offset`, and `#` semantics are defined in the ICU MessageFormat documentation and specified in UTS #35 (LDML), which normatively defines plural rule syntax and category names, published by the Unicode Consortium.
- CLDR plural rules data defines per-locale category formulas, and the ICU User Guide's Format/Parse → Messages chapter documents runtime behavior.
- A reproducible check: render the example banner with operands `[0, 1, 2, 5]` in `pl`, `ar`, `en`; the outputs use four, six, and two distinct clauses respectively — proving category selection is data-driven and the catalog must carry all forms.

## Failure modes and correction

- **Hardcoded singular/plural in code.** Symptom: untranslatable strings for many-locale languages. Correct by moving all number-conditional phrasing into `plural` clauses.
- **Missing category in translation.** Symptom: Arabic users see `other` text for counts like 2 or 11, or strict runtimes throw. Correct by catalog linting plus translator guidance listing required categories per locale.
- **Ordinal/cardinal confusion.** Symptom: "1th", "2nd place" errors in rank lists. Correct by using `selectordinal`, not `plural`, for ranks.
- **Pre-formatted numbers.** Symptom: category computed on `"1.0"` style strings yields wrong form or runtime error. Correct by passing numeric operands.
- **`select` on open sets.** Symptom: unknown value produces garbage or default-clone text. Correct by redesigning as separate messages or adding exhaustive options with a genuine fallback.

## Limitations

- MessageFormat solves phrasing, not grammar beyond number/gender/register switches; complex agreement (case government, clitic placement) still needs restructured copy.
- Runtimes differ in strictness and in MessageFormat 2 support; cross-platform catalogs need a compatibility target.
- `plural` operates on numbers; quantity units ("3 kg") follow unit formatting patterns better expressed with `unit` style placeholders in modern stacks.
- Machine-translation pipelines sometimes mangle nested syntax; pretranslation QA must re-validate structure.

## Canonical sources

- Unicode, ICU User Guide — Formatting Messages (MessageFormat, plural/select/selectordinal): https://unicode-org.github.io/icu/userguide/format_parse/messages/
- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — plural rules syntax and categories: https://unicode.org/reports/tr35/
