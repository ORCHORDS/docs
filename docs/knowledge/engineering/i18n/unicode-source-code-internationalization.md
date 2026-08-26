# Unicode source-code internationalization

**Issue:** Source code can contain non-ASCII identifiers, literals, comments, and invisible formatting. Toolchains that disagree on encoding, normalization, or display can create review and build ambiguity.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Mandate UTF-8, a pinned Unicode-aware identifier profile, visible escaping for dangerous controls, and compiler/linter agreement. Preserve human-language comments while keeping externally consumed protocol tokens stable. Render bidi controls and confusables visibly in review tools.

## Verification

Test mixed scripts, bidi controls, normalization variants, identifiers differing only by confusables, generated code, compiler versions, diffs, search, and archives.

## Gotchas

Unicode-friendly source is not permission for ambiguous identifiers; comments/literals and identifiers need different policies.

## Sources

- Unicode Consortium, [UTS #55 Unicode Source Code Handling](https://unicode.org/reports/tr55/)
