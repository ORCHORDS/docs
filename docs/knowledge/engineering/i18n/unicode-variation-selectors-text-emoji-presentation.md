# Unicode variation selectors for text and emoji presentation

**Issue:** A sanitizer removes U+FE0E or U+FE0F as invisible characters, or a renderer appends one to every symbol. Stored identifiers, cursor positions, and visual output then diverge across fonts and platforms even though the base code points appear identical.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

Unicode emoji presentation sequences use variation selector-15, U+FE0E, to request text presentation and variation selector-16, U+FE0F, to request emoji presentation for registered base characters. The selector is part of the code-point sequence; it is not standalone decoration.

Use selectors only where Unicode defines the variation sequence and the product intentionally requests a presentation. Font, shaping, platform, and user-agent support still determine whether the requested glyph is available.

## Controls and implementation

1. Preserve variation selectors during input, normalization, storage, transport, clipboard, and rendering. Do not strip all default-ignorable code points as a generic cleanup step.
2. Validate a base-plus-selector sequence against the current Unicode emoji variation-sequence data. Do not append FE0E or FE0F to arbitrary characters.
3. Keep presentation policy at the display boundary. Do not rewrite a durable identifier or search key merely to force a colorful glyph in one UI.
4. Segment text by extended grapheme cluster for cursoring, deletion, truncation, and selection. Code-unit or code-point slicing can detach the selector from its base or split a larger ZWJ sequence.
5. Define comparison semantics per field. Exact identifiers may distinguish sequences; user-facing search may intentionally fold selected presentation differences, but it must preserve the original value and document the equivalence.
6. Use a font stack with coverage for the intended style and tolerate fallback when a requested presentation is unavailable. Never infer semantic meaning solely from color or glyph shape.
7. Version Unicode data used for validation and regression-test changes before upgrading. New registrations can alter which sequences are recognized.
8. Escape diagnostics by code point where invisible differences matter, without exposing unrelated user content.

## Verification

Test registered text and emoji variation sequences, unsupported base-plus-selector pairs, selectors at string start, repeated selectors, supplementary-plane bases, keycap and ZWJ sequences, normalization forms, database round trip, clipboard, fallback fonts, monochrome environments, and grapheme deletion.

Compare code points as well as screenshots across supported operating systems. Confirm sanitization preserves the sequence and that a missing emoji glyph degrades to readable content rather than data loss.

## Gotchas

- FE0E requests text style; FE0F requests emoji style. Neither guarantees a particular artwork.
- Emoji_Presentation defaults and explicit variation sequences are related but not interchangeable.
- Variation selectors are not combining marks to remove for “accent-insensitive” search.
- A selector can participate inside a longer grapheme cluster, including emoji ZWJ sequences.

## Official sources

- [Unicode Technical Standard #51 — Emoji Presentation Style](https://www.unicode.org/reports/tr51/#Presentation_Style)
- [Unicode Character Database — Standardized Variation Sequences](https://www.unicode.org/Public/UCD/latest/ucd/StandardizedVariants.txt)
