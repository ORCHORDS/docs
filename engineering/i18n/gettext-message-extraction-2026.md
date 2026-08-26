# gettext-message-extraction-2026

**Issue:** A Python project supports 12 languages. Translations are scattered across hand-edited JSON files. A new string is added; the team forgets 11 of the 12 locales. Translations drift.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Hand-managed translation files drift the moment a developer adds a string without remembering all locales. The 80/20 problem: 80% of strings are translated in most locales, 20% are missing or stale. Users see English where they expect their language.

## Root cause

GNU gettext is the canonical workflow for i18n. It separates message extraction, translation, and runtime lookup into discrete steps. The tools (`xgettext`, `msgmerge`, `msginit`, `msgfmt`) handle the boilerplate; the developer marks strings for translation; the rest is mechanical.

## The five-step workflow

1. **Mark strings in source** with the gettext function (`_("text")` in Python, `gettext()` in C, etc.)
2. **Extract messages** with `xgettext` → creates a `.pot` (Portable Object Template) file
3. **Start translations** with `msginit` → creates a `.po` file per locale
4. **Update translations** with `msgmerge` when new strings are added → updates each `.po` file
5. **Compile to runtime format** with `msgfmt` → creates a `.mo` (Machine Object) binary file

```bash
# Extract
xgettext main.py -d messages -p locale
mv locale/messages.po locale/messages.pot

# Start Greek translation
msginit -i locale/messages.pot --locale=el_GR -o locale/el/LC_MESSAGES/messages.po

# Update Greek after source change
msgmerge locale/el/LC_MESSAGES/messages.po locale/messages.pot -o locale/el/LC_MESSAGES/messages.po

# Compile to runtime
msgfmt locale/el/LC_MESSAGES/messages.po -o locale/el/LC_MESSAGES/messages.mo
```

## The four file types

- `PACKAGE.pot` — template, extracted from source; serves as the source of truth for new translations
- `LANGUAGE.po` — translation file per locale; updated with `msgmerge` when `.pot` changes
- `LANGUAGE.mo` — binary compiled catalog loaded at runtime
- `.mo` files are typically generated at compile time, not version-controlled

## The modern alternatives

For JavaScript/TypeScript projects, the equivalents:

- **i18next-cli** — `npx i18next-cli extract` reads source files, updates JSON translation files
- **i18next-scanner** — older, transform-stream based
- **babel-plugin-i18next-extract** — Babel-time extraction
- **FormatJS** — for ICU MessageFormat strings

For Python, the standard is `pybabel extract` (from Babel) plus `gettext` for runtime.

For Java, `xgettext` works on `.java` files. For C/C++/Go/Rust, native gettext libraries exist for each.

## The runtime pattern

```python
import gettext
el = gettext.translation('messages', localedir='locale', languages=['el'])
el.install()
_ = el.gettext

print(_("Welcome to our application"))
# Greek translation if available; English fallback if not
```

`gettext.NullTranslations` returns the input unchanged when no translation is found. Fall back to the source string (English) automatically.

## The CI integration

The extraction step should run in CI on every PR that touches source files:

```yaml
# .github/workflows/i18n.yml
- name: Extract messages
  run: xgettext src/**/*.py -d messages -p locale
- name: Check for unmerged translations
  run: |
    if ! git diff --exit-code locale/messages.pot; then
      echo "Run 'xgettext' locally and commit locale/messages.pot"
      exit 1
    fi
```

A PR that adds a new translatable string but does not commit the updated `.pot` fails CI. The translation team is notified that new strings need translation.

## The pitfalls

- **Not running `xgettext` on every change** — the `.pot` goes stale; `msgmerge` on stale templates misses new strings
- **Editing `.po` files without re-merging** — manual edits are overwritten when the team runs `msgmerge`
- **Forgetting `msguniq`** — duplicate entries in the `.po` file confuse translators and inflate the catalog
- **Not regenerating `.mo` files** — runtime loads stale translations
- **Hand-editing `.mo` files** — these are compiled binaries; use `msgunfmt` to reverse and edit the `.po`

## The version control discipline

- Version-control `.po` and `.pot` files
- Do not version-control `.mo` files (regenerate at build time)
- Use `msginit --no-translator` for CI-generated files
- Use `msgcat` to merge multiple `.po` files (for modular projects)

## Verification

The tell that gettext workflow is working:

- Every translatable string in source is marked with `_()` or equivalent
- `xgettext` runs in CI; PRs without updated `.pot` fail
- `msgmerge` is part of the translation team's release process
- `.mo` files are regenerated at build time, not hand-edited
- The runtime falls back to the source string when translation is missing

The tell it isn't:

- Translations live in hand-edited JSON files
- New strings are added without updating the catalog
- Translators get stale `.po` files; missing translations pile up
- The runtime crashes on untranslated strings

## Gotchas

- **Run `xgettext` on every source change.** The `.pot` is the source of truth.
- **`msgmerge` is not optional.** Without it, new strings never enter translation.
- **`.mo` files are binaries.** Don't version-control them; regenerate at build.
- **`msguniq` deduplicates.** Saves translation time and shrinks the catalog.
- **The runtime fallback is the source string.** No need to ship every string in every locale; English is the default.
- **CI catches missing extractions.** A PR that adds a string without updating `.pot` fails the build.

## Related

- `i18n/icu-message-format.md` — for plural/gender strings
- `i18n/pseudo-localization.md` — for testing before translations
- `i18n/locale-negotiation.md` — for choosing which locale to serve

## Source URLs (verified 2026-08-10)

- https://www.gnu.org/software/gettext/manual/gettext.txt
- https://www.gnu.org/software/gettext/manual/html_node/xgettext-Invocation.html
- https://www.i18next.com/how-to/extracting-translations
- https://github.com/i18next/i18next-cli
- https://phrase.com/blog/posts/learn-gettext-tools-internationalization/
