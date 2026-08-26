# Unicode stream-safe normalization boundary

**Issue:** A streaming normalizer accepts an unbounded sequence of non-starters, creating excessive buffering or output that violates a downstream stream-safe contract.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UAX #15 defines Stream-Safe Text Format by limiting consecutive non-starters, using CGJ insertion when required. Apply it only at a declared interchange boundary; it is distinct from choosing NFC/NFD and can change the code-point sequence.

**Source:** [Unicode Standard Annex #15 — Stream-Safe Text Format](https://unicode.org/reports/tr15/#Stream_Safe_Text_Format)

## Controls

- normalize with a pinned Unicode implementation before enforcing the stream-safe limit;
- keep state across chunk boundaries so split input cannot bypass counting;
- document whether CGJ insertion is permitted by the protocol;
- retain original bytes separately when fidelity or signatures matter;
- cap input size independently.

## Verification

Test exactly-at-limit and over-limit runs, chunk splits, leading combining marks, Hangul, canonical-equivalent input, and repeated normalization. Confirm signing/hashing occurs on the intended representation.

## Gotchas

CGJ can affect collation and is not a generic visual fix. Stream-safe does not make text safe for identifiers or markup. Never silently transform signed or byte-exact content.
