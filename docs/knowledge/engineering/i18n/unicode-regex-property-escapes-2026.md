# unicode-regex-property-escapes-2026

**Issue:** A signup form validates names with `/^[a-zA-Z' -]+$/` and instantly rejects "José", "李明", "Aoife Ní Bhriain", and anyone with a combining accent; a hashtag regex misses emoji; a slug sanitizer strips Cyrillic entirely. ASCII character classes are the most common quiet i18n bug in validation code. This article covers Unicode property escapes (`\p{...}` with the `u` flag) and the newer `v` flag (unicodeSets with set notation and properties-of-strings), the 2026 standard way to write script-aware, locale-correct regex in JavaScript.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 property classes that matter

1. **`\p{L}` / `\p{Letter}`.** Any letter in any script — the drop-in replacement for `[a-zA-Z]` in name/title validators. `\P{L}` is its negation. Requires the `u` flag: `/^\p{L}+$/u.test('李明')` is true.
2. **`\p{Script=...}` and `\p{Script_Extensions=...}`.** Restrict input to a writing system: `\p{Script=Latin}`, `\p{Script=Han}`, `\p{Script=Arabic}`. `Script_Extensions` (`\p{scx=...}`) additionally matches characters shared between scripts (e.g., the Japanese long-vowel mark used across scripts), which is usually what you want for mixed CJK input.
3. **`\p{M}` / `\p{Mark}`.** Combining marks — diacritics that render attached to a preceding base. "É" can be one code point (precomposed) *or* `E` + U+0301, so name validators must accept `[\p{L}\p{M}]` to handle decomposed (NFD) input from iOS and some keyboards.
4. **`\p{N}` / `\p{Number}`.** Digits beyond ASCII 0-9: Arabic-Indic ٠١٢, Devanagari, fullwidth ０１２. Use it when the field accepts localized numerals; combine with `Intl.NumberFormat` parsing on the way out.
5. **`\p{Alphabetic}` and `\p{XID_Start}`/`\p{XID_Continue}`.** `Alphabetic` is the Unicode notion of "letter-ish" (includes marks and some letters `\p{L}` misses); `XID_Start`/`XID_Continue` define what counts as an identifier character and are the correct basis for username/handle validation rather than `\w`, which is ASCII-only by spec.

## The 5 v-flag upgrades

1. **`v` implies and supersedes `u`.** `//v` enables everything `u` does plus set notation and string properties; the ESLint `require-unicode-regexp` docs already steer toward `v`. Note `v` and `u` are mutually exclusive on one literal.
2. **Set subtraction `--`.** `[\p{L}--\p{Script=Latin}]` = any letter *except* Latin — useful for "must not accidentally mix scripts" checks or building curated allowlists.
3. **Set intersection `&&`.** `[\p{Script=Latin}&&\p{L}]`, or intersect a range with a property class to carve out exactly the characters you mean, inside nested classes `[[a-z]&&[^aeiou]]`.
4. **Properties of strings.** `\p{RGI_Emoji}` and `\p{Basic_Emoji}` match multi-code-point emoji as units — the only clean way to regex-match 👨‍👩‍👧‍👦 (family with ZWJ) or flag pairs without hand-rolling alternations.
5. **Escaped literals in classes.** Under `v`, characters like `( ) [ ] { } / - |` inside classes must be escaped with double punctuation (`\(`), tightening patterns that silently mis-parsed before.

## The 5 validation patterns

1. **Person names.** `/^[\p{L}\p{M}'’. -]+$/u` — letters in any script, combining marks for decomposed accents, typographic apostrophes. Better still: validate almost nothing (names contain digits legitimately in some cultures; see `personal-name-formatting-2026.md`) and sanitize for storage instead.
2. **Single-script fields.** `/^\p{Script=Latin}+$/u` for fields that are genuinely Latin-only (say, an ISO-derived code), with a visible explanation — but let users paste CJK into names and notes, so apply script limits narrowly.
3. **Mixed-script confusable guard.** Detect suspicious mixes (Cyrillic 'а' inside Latin text) with `/\p{Script=Cyrillic}/u` checks for phishing screens — warn, don't block.
4. **Unicode slugs.** Replace `[^a-z0-9-]` stripping with `/[^\p{L}\p{N}-]+/gu` collapses to keep international slugs, or NFC-normalize first so `é` survives as one code point.
5. **Emoji-aware counters and mentions.** Use `\p{RGI_Emoji}` under `v` for hashtag/content regexes, and pair with `Intl.Segmenter` grapheme counting so "👩‍💻" counts as one character in length limits.

## The 5 pitfalls

- **`\p{...}` without `u`/`v` matches literal "p".** `/^\p{L}+$/` (no flag) compiles fine and tests true for "pL"-ish strings — a silent false-accept. Enforce `require-unicode-regexp` in ESLint to catch it.
- **Precomposed vs decomposed.** NFC input matches `[\p{L}]` alone; NFD input needs `\p{M}` too. Normalize (`str.normalize('NFC')`) before validating, or always include `\p{M}` — see `unicode-normalization-nfc-nfd.md`.
- **`i` flag does not fold non-ASCII case without `u`.** `/^[a-z]+$/i` still excludes "É"; `/^\p{L}+$/ui` folds Unicode simple case. Greek final sigma and German ß still surprise — test with real samples.
- **Length is not match-count.** A passing regex does not make `" workspace ".length` the user's perceived length; grapheme clusters (ZWJ emoji, Hangul jamo, Indic conjuncts) need `Intl.Segmenter`, not `String.length`.
- **`v` flag syntax is strict.** Malformed escapes that `u` tolerated (`\p{Foo}`, unescaped `(`) now throw `SyntaxError` at parse time — good (fails loudly), but legacy `RegExp("...", "u")` dynamic constructors need flag audits during migration.

## Source URLs (verified 2026-08-15)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Regular_expressions/Unicode_character_class_escape
- https://v8.dev/features/regexp-v-flag
- https://mathiasbynens.be/notes/es-unicode-property-escapes
- https://eslint.org/docs/latest/rules/require-unicode-regexp
- https://schalkneethling.com/posts/unicode-character-class-escapes-a-javascript-hidden-superpower/

## Related

- `i18n/unicode-normalization-nfc-nfd.md` — normalize before you validate
- `i18n/locale-aware-input-validation.md` — locale-specific formats on top of these primitives
- `i18n/personal-name-formatting-2026.md` — why minimal name validation is the real best practice
- `i18n/grapheme-cluster-iteration.md` — counting what these regexes accept
