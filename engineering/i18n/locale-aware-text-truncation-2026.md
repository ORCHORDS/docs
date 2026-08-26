# locale-aware-text-truncation-2026

**Issue:** Every constrained UI surface — table cells, nav labels, chips, card titles — truncates text, and the naive implementations break internationally. String slicing by UTF-16 code units splits surrogate pairs and renders replacement characters inside emoji or CJK ideographs; slicing inside a ZWJ emoji sequence or a combining-mark cluster destroys the glyph; word-boundary logic built for spaces fails for CJK scripts that do not use spaces; CSS line-clamp cuts lines at script-inappropriate places; and the trailing ellipsis itself is locale-sensitive (… versus ..., with different conventions in CJK typography). Truncation is a rendering concern with Unicode-algorithm depth, and doing it wrong produces visible mojibake in exactly the locales where the UI otherwise works.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why naive slicing fails

1. **UTF-16 code unit slicing breaks astral characters.** JavaScript string indices count 16-bit units, so characters above U+FFFF (most emoji, rarer CJK ideographs) occupy two units; slice(0, 20) can cut between them, producing a lone surrogate that renders as a replacement box. Length checks (maxLength in UI libs) using .length overcount these strings by one per astral character.

2. **Grapheme clusters span multiple code points.** A user-perceived character can be a base plus combining marks (Hindi, Arabic, Thai), a flag pair, a skin-tone-modified emoji, or a ZWJ family sequence — all one grapheme cluster per UAX #29, many code points long. Truncating inside any of them visibly corrupts the glyph.

3. **Word-boundary heuristics assume spaces.** Truncation helpers that back off to the last space to avoid splitting words hang indefinitely on Japanese, Chinese, Thai, and Khmer text, which segments without spaces, and over-truncate German compounds. Script-aware segmentation (spaces where they exist, otherwise grapheme boundaries) is required.

4. **The truncation marker is not universal.** The single-character ellipsis … is standard in the West and CJK, but CJK typography often applies full-width forms and different conventions around what may end a line (kinsoku shori — a line may not begin with closing brackets or commas); adding ... blindly can produce line-initial punctuation that reads as broken typesetting in Japanese.

## Server-side and JS truncation done right

1. **Truncate on grapheme-cluster boundaries with Intl.Segmenter.** Segment the string with granularity: "grapheme" and cut between segments; the same API with granularity: "word" gives script-aware word boundaries where they exist. This handles surrogate pairs, ZWJ sequences, and combining marks in one primitive available in all modern runtimes.

2. **Budget length in graphemes, not .length.** Validation limits and character counters should count clusters via Segmenter (or Intl code-point iteration as a floor), so an emoji-heavy nickname is not rejected for being "over length" by invisible double-counting.

3. **Prefer end truncation, use middle truncation only for identifiers.** UI copy truncates at the end; filenames, IDs, and URLs benefit from middle truncation (report…2026.pdf) preserving the informative head and tail. Middle truncation has no native CSS support — implement it in JS on grapheme boundaries, or on the server when generating previews.

4. **Keep the full value accessible.** Pair every truncation with a tooltip (title attribute or accessible equivalent), aria-label carrying the full string, or an expand affordance. Screen readers otherwise read the visually truncated text; accessibility and i18n converge on the same requirement.

## CSS-side truncation

1. **Use text-overflow: ellipsis for single lines.** The nowrap plus overflow hidden plus text-overflow: ellipsis pattern truncates on the browser's own line-breaking, which respects script rules far better than JS slicing — but it hard-codes the … marker and offers no middle truncation.

2. **Use the standardized line-clamp for multiline.** The old -webkit-box hack is now standardized as the line-clamp property in current browsers; it cuts at line boundaries per the browser's segmentation. Verify per script: CJK line-breaking (kinsoku) is generally honored, but custom fonts with broken line-break metadata can still misbehave.

3. **Reserve expansion room for the marker.** When JS-truncating to a pixel or character budget, subtract room for the marker and localized suffix (such as "more"); otherwise the marker wraps alone to the next line, a classic layout bug in RTL and CJK.

4. **Do not truncate translated strings that are already short.** Design min-column widths from the longest supported locale (typically German or Finnish for European sets), so truncation fires only on genuinely unbounded content like user names, not on product-controlled labels.

## Testing and review checklist

1. **Fixture the pathological corpus.** Unit-test the truncation helper with: an emoji ZWJ family sequence at the cut point, a flag pair, Hindi with combining matras, Thai with stacked marks, Japanese without spaces, an RTL string with embedded Latin, and an empty string. Assert no lone surrogates and no split clusters in output (verifiable by re-segmenting the result).

2. **Visual-test truncation in pseudo-localized and real locales.** Capture screenshots of dense surfaces (tables, cards, chips) in a long-string pseudo-locale plus ja, de, ar, and th; look for clipping mid-glyph, line-initial punctuation, and unbalanced RTL truncation.

3. **Test RTL bidi neutral markers.** An ellipsis at the end of an RTL string containing Latin tail text can visually land on the wrong side because it is directionally neutral; assert marker placement under dir="rtl" with mixed-direction fixtures.

4. **Confirm the accessibility path.** With a screen reader, verify the full untruncated string is announced where truncation is used for visual fit; failing this converts a cosmetic device into an information-loss bug.
