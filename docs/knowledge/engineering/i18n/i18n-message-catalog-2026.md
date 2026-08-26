# i18n-message-catalog-2026

**Issue:** A team builds a multilingual product. The team debates PO files vs JSON vs YAML vs XLIFF. The team needs the 2026 decision framework for message catalog format and tooling.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 message catalog formats compared

| Format | Tooling | Plural | ICU | Best for |
|---|---|---|---|---|
| JSON | Native (everywhere) | Manual `{count, plural, ...}` | Yes (i18next) | JS/TS apps, simple i18n |
| YAML | Native (most langs) | Manual | Yes | Ruby/Python, dev-friendly |
| PO/POT (gettext) | gettext, Poedit, Weblate, Crowdin | Native (`msgid_plural`) | Limited (custom format) | C/C++, Linux apps |
| XLIFF 2.0 | Translators, CAT tools | Native | Yes (notes) | Translator handoff, complex workflows |
| ARB | Flutter only | Yes | Yes | Flutter apps |

## The 5-step decision rule

1. JS/TS web app → JSON with i18next or ICU MessageFormat.
2. Flutter app → ARB.
3. C/C++ or system-level → PO/POT with gettext.
4. Translator handoff to LSP or in-house translators → XLIFF 2.0.
5. Multi-tooling or compliance needs → XLIFF 2.0 (industry standard for TMS).

## The 5 best practices

1. **Source-language catalog as ground truth.** All translations derive from it.
2. **Plural rules via CLDR**, not hardcoded.
3. **ICU MessageFormat for any non-trivial string** (gender, plural, select).
4. **One key per source string** with description and context for translators.
5. **Version the catalog** in git alongside the source code.

## Gotchas

- PO files have plural forms indexed by `nplurals`; mismatch with CLDR causes silent loss.
- XLIFF 2.0 with inline MT is the 2026 default for enterprise LSPs.
- JSON keys with dots are interpreted as nested objects by i18next by default.
- ARB files are Flutter-specific; no other ecosystem.

## Source URLs (verified 2026-08-10)

- https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html
- https://docs.oasis-open.org/xliff/xliff-core/v2.0/os/xliff-core-v2.0-os.html
- https://docs.flutter.dev/ui/accessibility-and-internationalization/internationalization
- https://www.i18next.com/misc/json-format
