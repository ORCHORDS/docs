# WebAssembly Component Model Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application needs to run performance-critical code (image
processing, cryptography, data parsing) in the browser or at the edge,
but JavaScript is too slow. You want to reuse libraries written in
Rust, C++, or Go without rewriting them. Your plugin system requires
sandboxed, language-agnostic execution but Docker containers are too
heavy. Cross-language interoperability requires manual FFI glue code
that is fragile, unsafe, and hard to maintain.

## Context

WebAssembly (Wasm) is a portable binary instruction format that runs
at near-native speed in browsers, servers, and edge runtimes. The
Component Model, stabilized in 2025 alongside WASI 0.3, solved the
interoperability problem — components written in different languages
compose through typed interfaces (WIT) without manual glue code or
shared-memory hacks. In 2026, Wasm is the standard plugin format for
extensible systems (Envoy proxy filters, Kubernetes admission webhooks
via Kubewarden, database UDFs in SingleStore and Redpanda) and a
first-class compilation target for edge compute (Cloudflare Workers,
Fastly Compute, Fermyon Spin).

## Wasm execution models

```
Browser Wasm:
  → JavaScript interop via Web API bindings
  → Use case: compute-heavy client-side work
  → Runs in browser sandbox (same-origin, memory-safe)

Server-side Wasm (WASI):
  → System interface for file I/O, networking, clocks
  → WASI 0.3: async I/O, streams, component composition
  → Runtimes: Wasmtime, WasmEdge, Wasmer

Edge Wasm:
  → Sub-millisecond cold start (vs. 100ms+ for containers)
  → Platform: Cloudflare Workers, Fastly Compute, Fermyon Spin
  → Sandboxed per-request isolation
```

## Component Model architecture

```
┌─────────────────────────────────────────┐
│  Composed Application                   │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Auth     │ │ Business │ │ Storage │ │
│  │ (Rust)   │ │ (Go)     │ │ (C++)   │ │
│  └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       │ WIT        │ WIT        │ WIT   │
│  ┌────┴────────────┴────────────┴────┐  │
│  │  Component Model Runtime          │  │
│  │  (Wasmtime, WasmEdge)             │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### WIT (Wasm Interface Type) definition

```wit
// greeting.wit
package example:greeting@1.0.0;

interface greet {
  greet: func(name: string) -> string;
}

world greeter {
  export greet;
}
```

### Rust component implementation

```rust
// src/lib.rs
wit_bindgen::generate!({
    world: "greeter",
});

struct Component;

impl Guest for Component {
    fn greet(name: String) -> String {
        format!("Hello, {}!", name)
    }
}

export!(Component);
```

### Building and composing

```bash
# Build a Wasm component from Rust
cargo component build --release

# Inspect component interfaces
wasm-tools component wit target/wasm32-wasip2/release/greeter.wasm

# Compose two components
wasm-tools compose auth.wasm -d business.wasm -o composed.wasm
```

## Use cases in production (2026)

| Use case | Platform | Language | Benefit |
|---|---|---|---|
| Proxy filters | Envoy (Istio) | Rust, C++ | Hot-reload without proxy restart |
| Admission webhooks | Kubewarden (K8s) | Any → Wasm | Faster, sandboxed policy eval |
| Database UDFs | SingleStore, Redpanda | Rust, Go | Near-native perf, safe execution |
| Edge compute | Cloudflare Workers | Rust, JS, Python | Sub-ms cold starts |
| Plugin systems | VS Code, Zed, Figma | Any → Wasm | Language-agnostic, sandboxed |
| AI inference | WASI-NN | Rust, C++ | Portable model execution |

## Anti-patterns

- **Compiling everything to Wasm** — JavaScript-heavy UI code gains
  little from Wasm. Use Wasm for compute-bound work (parsing, crypto,
  image processing) and keep UI logic in JavaScript.
- **Ignoring the Component Model** — building Wasm modules with raw
  memory sharing and manual FFI. The Component Model provides typed
  interfaces, automatic memory management, and composability. Use WIT
  and `wit-bindgen` instead of raw imports/exports.
- **Oversized Wasm binaries** — shipping a 10MB Wasm binary for a
  simple function. Use `wasm-opt` for optimization, enable LTO, and
  strip debug symbols for production builds.
- **Scattering generated types** — letting WIT-generated bindings
  leak throughout the codebase. Use bindings as a thin adapter layer
  and put business logic behind your own modules.

## Gotchas

- **No direct DOM access** — Wasm cannot manipulate the DOM directly.
  Use JavaScript interop (`wasm-bindgen` in Rust, `@aspect-build/rules_js`
  in Bazel) to bridge Wasm compute with DOM updates.
- **WASI version compatibility** — WASI 0.2 (sync) and WASI 0.3
  (async) are not fully interchangeable. Check your runtime's WASI
  support before targeting a specific version.
- **Debugging limitations** — Wasm debugging support varies by
  runtime. Browser DevTools support source maps for C++/Rust Wasm;
  server-side debugging requires runtime-specific tooling (Wasmtime
  DWARF support).
- **Thread support** — Wasm threads (shared memory + atomics) are
  available in browsers behind `SharedArrayBuffer` (requires
  cross-origin isolation headers). WASI threading is still maturing.

## Verification

- Compute-heavy operations use Wasm components with WIT interfaces.
- Components compose across language boundaries without manual FFI.
- Wasm binaries are optimized (`wasm-opt -O3`) and under 1MB for
  typical components.
- Edge-deployed Wasm achieves sub-millisecond cold start times.
- Plugin systems use the Component Model for sandboxed execution.
- WASI version targets match the runtime's supported version.

## Related

- `documentation/docs/policies/cloudflare/workers-ai-edge-inference.md`
- `documentation/docs/policies/performance/edge-caching-cdn-invalidation.md`
- `documentation/docs/policies/architecture/hexagonal-clean-architecture.md`

## Source URLs (verified 2026-08-16)

- WebAssembly Component Model and WASI 0.3 — https://jsmanifest.com/wasm-component-model-wasi-javascript-developers
- Wasm Component Model 2026 Cloud Interop — https://techbytes.app/posts/wasm-component-model-2026-cloud-interop-deep-dive/
- State of WebAssembly 2026 — https://xuro.net/blog/state-of-webassembly-2026/
- Wasm Component Model Cheat Sheet — https://techbytes.app/posts/wasm-component-model-cheat-sheet/
