# W3C WebAssembly Core 2 — Specification Governance

## Purpose

Establish governance on the W3C WebAssembly Core Specification, release 2, as a primary-source reference for any engineering program adopting WebAssembly as a portable compilation target for client- or server-side execution.

## Current status

- Published as a W3C Proposed Recommendation with the URL slug `wasm-core-2`, dated to the 2017-2019 base publication cycle updated through late 2023. The W3C document review page is https://www.w3.org/TR/wasm-core-2/.
- Discrepancy to note: the document abstract verbatim uses the phrase "release 3.0" while the canonical TR slug and git tag is "release 2" (CR-version WASM core spec); the version numbering chosen for the published document is "release 3.0" of the underlying core specification, which is referred to as "Core 2" in W3C TR naming. This naming disparity originates with the WebAssembly Community Group using internal release numbers that differ from W3C TR slug generations. Record this in any adoption governance log.
- Defined under the WebAssembly Community Group (CG), not the Working Group. Joint stewardship with the W3C.
- Status as of 2026-09-04: superseded at the W3C TR level by Core 3 only in the sense of which TR the CG publishes; Core 2/CR-2 remains the recommended stable core for porting and verification work where platform tooling lags.

## Sources

- Primary: W3C TR page https://www.w3.org/TR/wasm-core-2/ — abstract, definitions, validation algorithm, binary format, and execution semantics.
- Underlying specification: WebAssembly Community Group repository on GitHub (WebAssembly/spec) — https://github.com/WebAssembly/spec/
- Companion specs: W3C WebAssembly Web API (web-api), W3C WebAssembly JS Interface (js-api), W3C WebAssembly Interface Types (interface-types), W3C WebAssembly System Interface (WASI), W3C WASI Preview 2.
- Authoritative references appearing in Core 2: IEEE 754-2019 (binary floating-point), ECMA-262 (JavaScript), Unicode Standard.

## Scope note

WebAssembly Core 2 is the core (non-embedder) part of the WebAssembly specification. The companion specs (Web API, JS Interface, WASI) define how WebAssembly is hosted. This article's scope is limited to Core 2 governance. Key concepts that any governed adoption must understand:

1. Linear memory and typed function references. Core 2 formalizes the linear-memory model and introduces typed function references (`funcref`, `externref`) as well as the module-linking extension subset referenced from this specification.
2. Validation and execution. Core 2 defines the validation algorithm (a stack-machine verification over a structured control-flow form) and the execution semantics (an abstract store plus a frame stack). Any language-level embedding needs to align with these definitions when claiming "WASM-compliant."
3. Determinism and sandbox. The specification guarantees deterministic execution within a module's declared assumptions and isolates modules from one another via memory isolation; security claims in marketing should be tied to this specific guarantee, not to opcode-by-opcode equivalence.
4. Value types. The specification defines numeric types (i32, i64, f32, f64), vector types (v128 with SIMD lanes), and reference types. Embedders must agree on whether vector types are part of the conformance boundary.
5. Future-feature usage. Core 2 lists features in the spec that may or may not be present in a given engine (multi-value, reference types, SIMD, threads, tail calls, GC); any governance assertion about WASM interoperability must state which of these features are required.

Note the version-numbering discrepancy above: TR slugs and release-version strings diverge — record this in the adoption governance log so future audits can identify exactly which Technical Report a control references. Adoption claims for "WebAssembly 2.0" or "WASM 3.0" should be made by reference to a specific W3C TR slug (`wasm-core-2`) plus the published date.

This article does not cover W3C WebAssembly Web API, JS Interface, Interface Types, or WASI (each is a separate W3C TR with its own versioning).
