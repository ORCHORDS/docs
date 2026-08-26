# CLDR parent locales and default-content resolution

**Issue:** A locale-data loader truncates tags mechanically, missing CLDR parent overrides or serving duplicate default-content bundles.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

LDML supplemental data defines `parentLocales` and default-content locales. Build fallback and bundle aliasing from the pinned CLDR release rather than assuming every tag falls back by removing the rightmost subtag.

**Source:** [Unicode LDML Supplemental — locale inheritance](https://unicode.org/reports/tr35/tr35-info.html#Locale_Inheritance)

## Controls

- pin CLDR and generate a deterministic parent graph;
- detect cycles/missing parents at build time;
- keep resource fallback separate from language negotiation;
- treat default-content locales as aliases only where CLDR specifies;
- preserve user-selected locale identity for UI/account settings.

## Verification

Test explicit parent overrides, script locales, region locales, root fallback, default-content aliases, missing resources, and CLDR upgrades. Server/client resolution must agree.

## Gotchas

BCP 47 syntax alone does not define CLDR inheritance. A parent for resource lookup is not necessarily the best-match user locale. Version changes require bundle rebuilds.
