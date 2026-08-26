# data-i18n-marker-pattern

**Issue:** Inline English text in JSX without `data-i18n` makes leaks invisible
**Date:** 2026-08-09
**Status:** documented (use this convention)

## Symptom
You write a `<p>` tag with English text directly:
```jsx
<p>Welcome to the platform. This is your dashboard.</p>
```

The text is hardcoded. Translators don't see it in the i18n
extraction tools. It ships in English in all 20 locales. The
visual QA pass catches it — 50 leaks per page across 9 pages =
450 hardcoded English strings to fix.

## Root cause
i18n extraction tools (next-intl, i18next, etc.) only see keys
that are explicitly passed to `t()`. Hardcoded text in JSX is
invisible to the toolchain.

**Source:** next-intl docs — usage:
https://next-intl-docs.vercel.app/docs/usage/messages

## Fix
Add `data-i18n="key.path"` to every text-bearing element. Wrap the
content in `{t("key.path")}`. This is two things:

1. **The `data-i18n` attribute** — a marker for the i18n
   extraction tool to know "this element should be translated."
2. **The `t()` call** — the runtime call that swaps in the
   translated value.

```jsx
<p data-i18n="home.welcome">
  {t("home.welcome", "Welcome to the platform. This is your dashboard.")}
</p>
```

The second arg of `t()` is the **default value** (used as a
fallback if the key is missing). It also serves as the source-of-
truth string for the translation tool to read.

## Why both?

- **`data-i18n`** — visible to extraction tools (some tools only
  look at attributes, not text content)
- **`t()`** — actually swaps the text at runtime
- **The default value** — fallback for missing translations AND
  the source string for translators

The pattern: every translatable text node has BOTH a `data-i18n`
attribute AND a `t()` call.

## Placeholders

For input placeholders, use `data-i18n-attr="placeholder:key"`:

```jsx
<input
  type="text"
  placeholder={t("home.searchPlaceholder", "Search...")}
  data-i18n-attr="placeholder:home.searchPlaceholder"
/>
```

For other attributes (aria-label, title), same pattern with
`data-i18n-attr="aria-label:key"`.

## Extraction tool behavior

A custom i18n extraction script can parse the JSX:
1. Find all elements with `data-i18n` attribute → record key
2. Find the `t()` call next to it → record source string
3. Generate the JSON entry

Tools like `babel-plugin-i18next` or `next-intl`'s built-in
extractor do this automatically if you follow the convention.

## Verification
- **Test:** `test/data-i18n.test.ts > no hardcoded English in JSX
  for 20 locales` — pass
- **Visual QA:** Screenshot 9 pages × 20 locales; 0 English leaks
- **CI:** Lint rule rejects new code with English text + no
  `data-i18n` (ESLint plugin: `eslint-plugin-i18next` or custom)

## Gotchas
- **Numbers, dates, and proper nouns are NOT translated.** Don't
  add `data-i18n` to a timestamp display — it's already
  locale-formatted via `Intl.DateTimeFormat`.
- **Hardcoded data arrays need `i18nKey` fields.** If you have
  `<li>Apple</li><li>Banana</li>`, the strings are in a data
  array. Refactor to:
  ```ts
  const items = [
    { i18nKey: 'fruits.apple', name: 'Apple' },
    { i18nKey: 'fruits.banana', name: 'Banana' },
  ];
  ```
  And in JSX: `<li data-i18n={item.i18nKey}>{t(item.i18nKey, item.name)}</li>`
- **Don't use `data-i18n` for non-translatable content.** It
  confuses the extraction tool and adds noise. Only mark
  text-bearing elements.
- **For RTL brand text, pair with `<bdi>`** (see
  `rtl-safe-component-patterns.md`).

## Related
- `flat-dotted-vs-nested-keys.md`
- `brand-literals-stay-english.md`
- `icu-plural-rules-20-locales.md`
- `rtl-safe-component-patterns.md`
