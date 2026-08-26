# bidi-algorithm-unicode

**Issue:** Understanding the Unicode Bidirectional Algorithm and its CSS/HTML controls
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mixed LTR/RTL text renders in the wrong visual order without bidirectional controls.

## Pattern / Solution
Key Unicode control characters:
- LRM U+200E -- force next char LTR
- RLM U+200F -- force next char RTL
- LRI U+2066 -- LTR isolate (preferred)
- RLI U+2067 -- RTL isolate (preferred)
- FSI U+2068 -- first-strong isolate
- PDI U+2069 -- pop directional isolate

Prefer HTML over Unicode control chars:
```html
<p dir="rtl">
  أرسل بريدًا إلى <bdi>user@example.com</bdi> اليوم
</p>
```
```css
.neutral-number { unicode-bidi: isolate; direction: ltr; }
```

## Gotchas
- Embedding characters (LRE/RLE) do not reset at line breaks; isolates (LRI/RLI) do
- Numbers are "weak" bidi characters; they adopt surrounding direction
- `<bdi>` is equivalent to `<span dir="auto">` with `unicode-bidi: isolate`

## Related
- `arabic-persian-text-rendering.md`
- `bidi-rtl-layout-css.md`
