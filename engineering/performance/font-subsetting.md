# font-subsetting

**Issue:** Full font files downloaded for text using only a fraction of glyphs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A full Latin + Extended font can be 200-400 KB. Subsetting removes unused glyphs. For ASCII-only content, a subset can be under 20 KB.

## Pattern / Solution
1. Use pyftsubset (fonttools) to create subsets: pyftsubset font.ttf --unicodes=U+0000-00FF --flavor=woff2.\n2. Use unicode-range descriptor in @font-face so browsers only download the relevant subset.\n3. Google Fonts automatically subsets via text= parameter for single-use strings.\n4. For variable fonts, subset axes to only those used.\n5. Self-host subsetted fonts to avoid Google Fonts DNS lookup.

## Gotchas
- Subsetting too aggressively breaks rendering for user-generated content with unexpected characters.\n- Some fonts have licensing restrictions on subsetting -- check the license.\n- Variable fonts with only weight axis still cover most use cases with a single file.

## Related
font-display-swap, font-preloading, compression-gzip-brotli
