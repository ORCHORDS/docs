# Unicode noncharacters interchange policy

**Issue:** A validator rejects every Unicode noncharacter as malformed text, while another component uses one as an internal sentinel and accidentally persists it. The two policies conflict at an API or storage boundary, causing data loss, spoofed end markers, or inconsistent round trips.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

Unicode permanently reserves 66 noncharacter code points: U+FDD0 through U+FDEF and the last two code points of each plane. They are valid code points in well-formed Unicode strings but are not assigned abstract characters and have no standard interchange meaning.

Generic Unicode processing must not confuse “noncharacter” with malformed UTF encoding. An application protocol may forbid or replace them at an open interchange boundary, but that is an explicit content policy, not a decoder rule.

## Controls and implementation

1. Decode UTF-8, UTF-16, or UTF-32 strictly first. Report malformed code-unit sequences separately from decoded noncharacters.
2. At a generic transport, database, or proxy boundary, preserve well-formed code points unless the owning protocol specifies a restriction. Do not silently delete them.
3. At a user-content boundary whose product contract has no use for noncharacters, either reject with a precise validation error or replace using the documented replacement policy. Apply the same decision on every ingestion path.
4. Never use a noncharacter as an in-memory sentinel in a value that can cross serialization, IPC, logging, storage, clipboard, or plugin boundaries. Keep sentinel state outside the text value.
5. Do not interpret decoded U+FFFE as evidence that bytes must be swapped. Byte-order detection belongs before decoding at the byte-stream boundary.
6. Treat the code-point test as an explicit predicate, not a font-rendering or “unprintable” test. Unassigned, private-use, control, default-ignorable, and noncharacter categories have different contracts.
7. Preserve diagnostics as code point and position without logging surrounding private text. If replacing, make replacement observable to the caller.
8. Include noncharacters in parser and security fuzz corpora so delimiter, truncation, normalization, and serialization code cannot give them hidden semantics.

## Verification

Cover U+FDD0, U+FDEF, U+FFFE, U+FFFF, the last two code points of supplementary planes, neighboring ordinary code points, malformed UTF, BOM handling, normalization, JSON and database round trips, copy/paste, logging, and protocol-specific rejection.

Assert generic components round-trip permitted values exactly, strict profiles reject consistently, and no layer truncates at a noncharacter or mistakes it for an internal EOF marker.

## Gotchas

- Noncharacters are not the same as unpaired UTF-16 surrogates; the latter are not Unicode scalar values.
- “Should not be interchanged” is not a license for a generic intermediary to corrupt data.
- U+FFFD is the replacement character and is not a noncharacter.
- A future Unicode version will not assign a character to a permanently reserved noncharacter.

## Official sources

- [Unicode FAQ — Private-use characters, noncharacters, and sentinels](https://www.unicode.org/faq/private_use.html)
- [Unicode Corrigendum #9 — Clarification About Noncharacters](https://www.unicode.org/versions/corrigendum9.html)
