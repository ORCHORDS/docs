# rtl-cjk-email-localization

**Issue:** A sending platform localized for Arabic, Hebrew, Urdu, Chinese, Japanese, and Korean recipients produces broken emails: RTL messages render left-aligned with mirrored button padding missing, mixed Arabic/English subject lines display punctuation in the wrong place, CJK body copy wraps mid-word with collapsed line-height, and any non-Latin content sent without UTF-8 encoding arrives as mojibake (`Ø£Ù‡Ù„Ø§` instead of أهلا). Email clients apply weak bidi and CJK defaults compared to browsers, so localization quality depends on explicit `dir`, encoding, and font-stack handling in the template pipeline that most default (English-oriented) templates never set.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Direction and bidi handling

1. **Set `dir="rtl"` on the `<html>` element plus a wrapper.** Belt-and-suspenders: `<html lang="ar" dir="rtl">` plus `dir="rtl"` on the outer wrapper table, because some webmail clients (Gmail, Outlook.com) strip the html tag's attributes when sanitizing and only the body-level wrapper survives.
2. **Add CSS fallback `direction: rtl; text-align: right;`** on the wrapper cell. Outlook (Word rendering engine) ignores `dir` inheritance quirks differently than WebKit clients; the CSS pair covers both.
3. **Force LTR islands explicitly.** Phone numbers, emails, code snippets, and tracking IDs inside RTL copy need `dir="ltr"` spans or `<bdi>` isolation, otherwise "Order #12345" renders as "#12345 Order" with punctuation jumping to the wrong side.
4. **Do not rely on Unicode control characters alone.** RLM/LRM marks fix punctuation placement in subject lines (where HTML is impossible), but in bodies prefer markup — control chars are invisible, easy to corrupt in template editing, and hard to debug.
5. **Bidi in subject lines needs the plain-text trick.** For subjects like "خصم 50% — Sale", wrap the Latin run with U+200E (LRM) or U+2066 (LRI) so the percent and dashes don't flip; test in Gmail iOS, which has the weakest bidi heuristics.
6. **Set `lang` correctly per message.** `lang="ar"`, `lang="he"`, `lang="fa"` change screen-reader pronunciation and font selection; a wrong or missing `lang` on RTL content yields unintelligible VoiceOver output.

## RTL layout mirroring

1. **Mirror the whole layout, not just text alignment.** Logo moves to the right, hero image flips, multi-column tables reverse column order, and navigation items flow right-to-left — a logical mirror of the LTR design, not a text-align patch.
2. **Use `padding-right`/`padding-left` mindfully — they do not flip.** Unlike web `padding-inline`, email CSS physical properties stay fixed; maintain mirrored variants of button and cell padding (`padding: 12px 24px` symmetric padding avoids the problem entirely where possible).
3. **Flip directional icons and backgrounds.** Arrow "→" in a CTA becomes "←"; CSS `transform: scaleX(-1)` works in WebKit clients but fails in Outlook — for Outlook, serve a pre-flipped image via mso conditional comments.
4. **Avoid italics for Arabic, Hebrew, and Urdu.** Connected scripts visually break apart under italic synthesis (fonts usually lack true italics); use weight (bold) or color for emphasis instead.
5. **Keep two template variants rather than one "universal" template.** Real-world RTL campaigns maintain an LTR base and an RTL variant sharing components; CSS logical properties (`margin-inline-start`) are not supported broadly enough in email clients to rely on for automatic flipping.
6. **Right-align the preheader and From/subject preview considerations.** Webmail preview snippets render LTR-truncated; front-load the localized content so the truncation cuts the tail, not the greeting.

## CJK typography and encoding

1. **Always send UTF-8 with explicit charset declared.** `Content-Type: text/html; charset=utf-8` on the MIME part and `<meta charset="utf-8">` in the head; legacy Shift_JIS/Big5/EUC-KR charsets cause mojibake when the template pipeline assumes UTF-8 (and vice versa — never mix charsets between subject encoding and body).
2. **Encode headers separately.** Non-ASCII subjects and display names must use RFC 2047 encoded-words (`=?UTF-8?B?...?=`) or RFC 2231 continuation; raw UTF-8 bytes in headers are mangled by older MTAs.
3. **Treat zh-CN, zh-TW, ja, and ko as separate locales.** Simplified vs Traditional Chinese differ in script and terminology, Japanese and Korean grammar change sentence structure and formality levels — "one CJK template with translated strings" produces unnatural copy; use per-locale template variants.
4. **Use system CJK font stacks, never webfonts.** Full CJK fonts are 5-20MB (webfont subsetting is impractical in email where most clients block webfonts); specify stacks like `"Hiragino Kaku Gothic ProN", "Yu Gothic", Meiryo, sans-serif` (ja), `"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif` (zh-CN), `"Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif` (ko).
5. **Increase line-height for CJK (1.7-2.0).** Dense ideographic glyphs with diacritics (Japanese furigana spacing) collide at Latin-typical 1.4 line-height; also bump body size to 16-18px because CJK strokes lose legibility smaller.
6. **Respect CJK line-breaking rules.** Chinese/Japanese text breaks between any characters but must not start a line with closing brackets (」、），etc.) or end with opening ones; avoid `word-break: break-all` on mixed Latin/CJK runs in buttons, which severs Latin words, and avoid fixed narrow columns that force bad breaks.
7. **Localize number and date formats.** Japanese addresses and dates (令和 or 2026年8月15日), currency position (¥1,080 vs 1,080円), and full-width vs half-width characters differ per locale; do not concatenate translated fragments with Latin punctuation like ",".

## Pipelines and testing

1. **Store locale at subscriber level, not inferred from domain.** A `.jp` email address may prefer English; collect language at signup (or first-click inference) and render per-recipient locale from the same campaign definition.
2. **Use ICU MessageFormat for pluralization and gender.** Arabic plural rules (zero/one/two/few/many/other) and RTL-aware interpolation break naive `string.replace` templating; ICU handles plural classes, nested select, and bidi-safe interpolation.
3. **Test on real client matrix for each script.** Minimum: Gmail web + iOS (weak bidi, strips html attrs), Outlook Windows (Word engine — worst CSS support for direction), Apple Mail (best behavior), plus a QQ Mail / Naver Mail pass for zh/ko audiences.
4. **Screenshot-diff RTL and CJK variants in CI.** RTL mirror bugs and CJK wrap/encoding regressions are visual; a per-locale screenshot suite against Litmus/Email on Acid or a headless renderer catches them before campaign send.
5. **Keep unsubscribe and legal notices in the recipient's locale.** CAN-SPAM/GDPR-required notices mistranslated or in English inside an otherwise localized mail cause complaints; RFC 8058 one-click headers must also carry the localized List-Unsubscribe mailto/https targets.
