# streaming-json-parsing

**Issue:** JSON.parse is all-or-nothing: it requires the complete document in memory before returning anything. That design assumption breaks in two increasingly common situations in 2025-2026. First, huge payloads (multi-megabyte API dumps, log exports, dataset previews) blow up memory and block the main thread for hundreds of milliseconds when parsed monolithically. Second, LLM token streams emit partial JSON fragments as they generate, so tool-calling agents wait for the entire response before they can act, or risk throwing on incomplete documents. Incremental (streaming) JSON parsers fix both by emitting values as the bytes arrive, enabling early rendering, early validation abort, and constant-memory processing; knowing when to adopt one, and what correctness traps it introduces, is the issue.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why JSON.parse fails at the edges

1. **Monolithic allocation.** A 20 MB JSON string plus its fully materialized object graph can briefly triple memory usage. On mobile this triggers GC pauses and, in extremes, tab crashes; parsing 20 MB of JSON on a mid-range phone main thread can block for 300+ ms, directly visible as INP damage.
2. **No partial results.** JSON.parse gives you one callback-free result at the end. UIs that could render the first 50 rows of a 50,000-row array instead show spinners until the whole payload lands, then pay a second cost to render everything at once.
3. **Token streams are syntactically incomplete by design.** An LLM emitting structured output produces fragments like an opening brace and a half-written field for many seconds. Any parser that requires a terminated document is useless here; the 2025-2026 ecosystem (JSON River, vectorjson, GJP-style gradual parsers) exists precisely to close this gap between tokens and typed objects.

## Streaming parser patterns

1. **SAX-style event parsers.** Emitters fire events per token (object start, key, string value, array end). You maintain only the state you care about, so memory stays flat regardless of document size. Best for aggregation, filtering, and feeding rows into a virtualized list as they arrive.
2. **Path-based pull parsers.** Subscribe to specific paths (for example, items.*.price) and get values typed and delivered as they complete. This matches how UIs consume APIs: you rarely need the whole tree, just three fields from each array element. Partial-parse libraries in JS (clarinet-lineage tools, besteffort-style parsers) and the 2025 WASM SIMD entrants like vectorjson implement this shape.
3. **Gradual repair for LLM output.** Parsers built for model streams (GJP-4-GPT lineage) accept truncated input, close dangling brackets heuristically, and return the maximal valid prefix. Use them for progressive tool-call rendering, but never trust the final value until the stream closes; a "repaired" partial can differ from the completed document.
4. **Early-abort validation.** A streaming parser can validate the first N items of an array and reject the request while the server is still sending the rest. Agents streaming structured tool calls gain the most here: detect an invalid schema at token 40 instead of after a 4,000-token response, cancel the upstream request, and retry with corrected instructions.

## Design decisions

1. **Choose streaming-friendly wire formats first.** JSON Lines (newline-delimited records) is trivially incremental with no parser beyond split and JSON.parse per line, has a tiny memory footprint, and maps naturally to fetch ReadableStream chunks. If you control the producer, JSONL beats a giant JSON array for any endpoint that grows.
2. **Chunk boundaries do not respect record boundaries.** Network chunks cut mid-string and mid-escape-sequence. The parser must buffer a tail between chunks; never assume TextDecoder chunks align with values. Use a decoder with stream: true and feed the parser raw string increments.
3. **Off-main-thread parsing.** Run the streaming parser in a Web Worker and post completed records to the UI in batches (for example, 100 rows per postMessage). This converts a long task into steady small tasks and keeps INP healthy even for 50 MB documents.
4. **Backpressure beats buffering.** If the UI renders slower than the network delivers, pause the reader (cancel the ReadableStream read loop) instead of accumulating an unbounded queue; streaming only saves memory if you actually stream all the way to the pixels.

## Pitfalls

1. **Duplicate-key and ordering semantics.** JSON.parse keeps the last duplicate key; event parsers differ. Pin behavior in tests because subtle mismatches surface as production data bugs.
2. **Depth attacks.** A streaming parser with a deep nesting stack can still be DoSed by a 10,000-deep document; enforce a max depth and abort, mirroring what hardened monolithic parsers do.
3. **Precision and big numbers.** Numbers streamed as tokens must be parsed with the same precision rules as JSON.parse (or a lossless BigInt path if you need it); ad hoc string-to-number conversion in a custom parser is a classic correctness regression.
4. **Do not stream everything.** Small payloads (under roughly 100 KB) are faster with plain JSON.parse than any incremental machinery. Measure first; streaming JSON is a tool for the heavy tail, not the median request.
