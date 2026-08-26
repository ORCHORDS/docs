# font-display-swap

**Issue:** Custom fonts cause invisible text (FOIT) during loading
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
font-display: swap shows a fallback font immediately and swaps to the custom font when loaded. Eliminates Flash of Invisible Text (FOIT) at the cost of Flash of Unstyled Text (FOUT).

## Pattern / Solution
1. Add font-display: swap to all @font-face declarations.\n2. Choose a fallback font with similar metrics to reduce layout shift on swap.\n3. Use font-display: optional when the custom font is purely aesthetic.\n4. Use font-display: fallback for a short 100ms block before swap.\n5. Tools like fontpie generate size-adjust and ascent-override to match fallback metrics.

## Gotchas
- font-display: swap can cause CLS when the custom font has different metrics than the fallback.\n- font-display: optional means users may never see the custom font; test fallback appearance.\n- Google Fonts supports font-display via &display=swap query parameter.

## Related
cls-prevention, font-subsetting, font-preloading
