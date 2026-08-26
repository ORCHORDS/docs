# WebAssembly Streaming Compilation Delivery Contract

**Issue:** A browser downloads an entire Wasm module into an ArrayBuffer before compiling it, forfeiting streaming work and sometimes failing when the server sends the wrong MIME type or CSP blocks compilation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Prefer `WebAssembly.instantiateStreaming(fetch(url), imports)` when compilation and instantiation can proceed together; use `compileStreaming()` when a reusable `WebAssembly.Module` is needed first. Serve Wasm with `Content-Type: application/wasm`, correct content length/encoding, cache validators, and a CSP that intentionally permits required Wasm execution.

Feature-detect and fall back to fetching an ArrayBuffer only when necessary. Cache versioned module URLs at the HTTP layer, keep import-object construction lightweight, and separate network, compile, instantiate, and initialization timing so optimization targets the correct stage.

## Verification

Test cold/warm HTTP cache, correct and incorrect MIME type, compressed transfer, CSP allow/deny, slow streaming response, corrupt/truncated module, import mismatch, unsupported streaming APIs, and service-worker interception. Use performance traces to confirm compilation overlaps delivery and ensure the fallback does not silently double-fetch.

## Gotchas

Streaming compilation cannot overcome an oversized module, expensive instantiation, or long application initialization. A service worker that buffers the response can erase the benefit. A compiled module is origin/runtime state, not a portable artifact across engines. Never weaken CSP broadly merely to make Wasm execute.

## Sources

- [WebAssembly JavaScript Interface specification](https://webassembly.github.io/spec/js-api/)
- [MDN WebAssembly.instantiateStreaming](https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/JavaScript_interface/instantiateStreaming_static)
- [MDN WebAssembly.compileStreaming](https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/JavaScript_interface/compileStreaming_static)
