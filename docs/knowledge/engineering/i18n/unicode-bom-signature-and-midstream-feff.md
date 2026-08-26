# Unicode BOM signature and midstream U+FEFF

**Issue:** A text pipeline removes every U+FEFF character, preserves a byte-order mark in concatenated fragments, or uses BOM sniffing after another protocol has already declared an encoding. The result is lost text semantics, invisible comparison differences, or a stray character in the middle of a document.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Stream-boundary model

U+FEFF at the beginning of a Unicode byte stream can act as a byte order mark or encoding signature. UTF-16 and UTF-32 use byte order; UTF-8 has no byte-order ambiguity, although the UTF-8 BOM byte sequence can identify the encoding.

After decoding has begun, U+FEFF is not a second stream marker. Its historical zero-width no-break-space use is deprecated; Unicode recommends U+2060 WORD JOINER for that semantic. Do not globally delete U+FEFF from decoded text.

A BOM policy belongs at a byte-stream boundary:

1. Determine the encoding using the enclosing protocol and its precedence rules.
2. Decode bytes exactly once.
3. Consume one initial BOM only when the chosen decoder/policy recognizes it.
4. Preserve or explicitly reject later U+FEFF code points according to the content format; never silently strip all.
5. When concatenating files, decode each independent stream and handle its initial signature before concatenating Unicode strings. Raw byte concatenation can move a later BOM into content.

## Format contracts

Declare per format whether an initial BOM is allowed, required, or forbidden. Source code, CSV exports, command-line tools, JSON processors, and editor integrations can have different interoperability constraints. “UTF-8 everywhere” does not settle the BOM question.

Do not add a BOM to repair a mislabeled HTTP response. Fix the transport/content-type contract. Do not use the presence or absence of a BOM as authentication or file-type authorization.

For security-sensitive identifiers, surface unexpected leading or midstream U+FEFF before normalization/validation so an invisible code point cannot bypass review. Apply the identifier profile's default-ignorable policy rather than an ad hoc replace.

## Verification

Test empty streams, initial UTF-8/UTF-16LE/UTF-16BE signatures, declared encoding that conflicts with bytes, truncated signatures, concatenated BOM-bearing files, U+FEFF at the start and middle of decoded text, U+2060, repeated BOMs, streaming chunk splits through the BOM bytes, and round-trip export/import.

Assert byte offsets and code-point offsets are not confused in diagnostics. Record encoding decision, source, and whether an initial signature was consumed; avoid logging the surrounding personal text.

## Gotchas

- U+FEFF is a code point; the encoded BOM is a format-specific byte sequence.
- Stripping a decoded first character before determining the actual stream boundary can corrupt embedded fragments.
- A UTF-8 BOM is neither required for decoding nor proof that all following bytes are valid.
- Generic trimming functions should not be relied on for BOM policy.

## Sources

- [Unicode Standard 17.0, Chapter 23 — Special Areas and Format Characters](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-23/)
- [Unicode FAQ — UTF-8, UTF-16, UTF-32 and BOM](https://www.unicode.org/faq/utf_bom.html)
