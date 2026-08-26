# chinese-japanese-cjk-fonts

**Issue:** Handling CJK font selection and rendering for Chinese, Japanese, Korean
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The same Unicode codepoint can render differently in Chinese, Japanese, and Korean (Han unification). Incorrect font selection shows wrong glyph variants.

## Pattern / Solution
Use `lang` attribute:
```html
<p lang="zh-Hans">草</p>  <!-- Simplified Chinese -->
<p lang="ja">草</p>        <!-- Japanese variant -->
```
CSS font stacks:
```css
:lang(zh-Hans) { font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
:lang(zh-Hant) { font-family: 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; }
:lang(ja) { font-family: 'Noto Sans JP', 'Hiragino Kaku Gothic ProN', 'Yu Gothic', sans-serif; }
:lang(ko) { font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
```
Word wrapping:
```css
.cjk-text { word-break: break-all; overflow-wrap: anywhere; }
:lang(ja) { line-break: strict; word-break: keep-all; }
```

## Gotchas
- `word-break: break-all` is correct for CJK but breaks Latin words mid-word
- Vertical text: `writing-mode: vertical-rl; text-orientation: mixed`
- Web fonts for CJK are 2-5 MB; use `unicode-range` subsetting

## Related
- `thai-line-breaking.md`
- `indic-script-rendering.md`
