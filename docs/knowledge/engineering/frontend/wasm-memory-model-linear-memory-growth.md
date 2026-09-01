# Wasm Linear Memory Model And Growth Management

## Scope

The WebAssembly linear-memory model as it appears in frontend code: one contiguous byte-addressable `ArrayBuffer`, pages of 64 KiB, the `memory.grow` reallocation contract, `memory.buffer` detachment on growth, typed-array view invalidation, and the strategies for sizing and growing memory in toolchain-generated modules (`wasm-memory.grow` vs imported memories vs multi-memory). Covers the JS↔Wasm boundary where these mechanics are observable; excludes compilation/instantiation streaming workflow and GC-proposal objects, which are separate surfaces.

## Workflow or implementation guidance

A Wasm memory is a flat `ArrayBuffer` addressed by byte offset — no pointer arithmetic safety net, no object headers. It is allocated in pages of exactly 65,536 bytes, and every access a module makes compiles to a bounds-checked load or store against the current byte length. The JS-side handle is `WebAssembly.Memory`, whose `.buffer` is the live view.

The single most consequential rule: growing a memory replaces the backing buffer. `memory.grow(n)` returns the previous page count on success or `-1` on failure, and after a successful grow, the old `ArrayAssembly`'s `ArrayBuffer` is detached — `byteLength` becomes 0 and every typed array previously created over it is invalidated:

```js
const mem = new WebAssembly.Memory({ initial: 1 });       // 64 KiB
const view = new Uint8Array(mem.buffer);
mem.grow(1);                                              // now 128 KiB
view[0] = 1;          // writes to a detached buffer: silently a no-op on view of length 0
const fresh = new Uint8Array(mem.buffer, 0, 0x10000);     // views must be rebuilt after grow
```

Toolchains that keep data structures in linear memory (Emscripten, Rust, AssemblyScript) all build their allocators on this primitive: `malloc` calls in compiled code bottom out in `memory.grow` when the free lists are exhausted, so a C program's OOM manifests as `grow` returning `-1` (or throwing in the JS API when allocation fails outright), not a JS exception with a stack into your code.

Managing this from the embedding side comes down to three postures. First, preallocate: `new WebAssembly.Memory({ initial: 512 })` (32 MiB up front) and pass it as an import so growth never happens during latency-sensitive phases — the right call for fixed-workload DSP or codecs. Second, allow growth but re-derive views on every boundary crossing: never cache a typed array across a call into the module that can allocate. Third, cap growth: `maximum` in the memory descriptor makes the engine reject growth beyond the cap, converting silent sprawl into an observable failure at a boundary you choose:

```js
const memory = new WebAssembly.Memory({ initial: 16, maximum: 256 }); // 1 MiB..16 MiB
const imports = { env: { memory } };
const { instance } = await WebAssembly.instantiate(moduleBytes, imports);
```

Imported memories also fix the shared-state problem: multiple instances can receive the same `Memory` object and see one address space, which is how a main-thread module and workers coordinate when the memory is `shared: true` — a shared memory's buffer is a `SharedArrayBuffer`, grow atomically extends it, and views stay valid because the buffer is never detached (the spec pins it in place). Shared memory requires cross-origin isolation (COOP/COEP) to exist at all in the document.

The `grow` cost model differs by engine and phase: within the engine's reservation the extension can be cheap; beyond it, the runtime allocates a new region and copies. A grown-from-16-pages-to-thousands memory has paid that copy repeatedly — prefer a `maximum`-sized initial allocation when the peak is known, and prefer fewer large grows over many small ones when it is not. Reallocation timing also janks: a copy of tens of MiB is a main-thread task; on the audio thread (`AudioWorklet`) it is a dropout, which is why audio modules are the canonical preallocate case.

Memory transfer: `postMessage(mem.buffer)` of a non-shared buffer detaches it in the sender (transfer semantics), leaving the module that still references that memory reading zeros unless the memory was shared. The fix pattern is either `SharedArrayBuffer` growth coordination or restructuring so one owner owns the memory.

## Controls

- Declare memory with an explicit `maximum` (or fixed size) in the descriptor; let the cap be the failure signal instead of the system OOM path.
- No cached typed-array views across calls that may allocate; rebuild views from `memory.buffer` at each boundary, or wrap access behind a getter that checks `buffer.byteLength`.
- Preallocate steady-state size for real-time paths (audio, decode loops) so no `grow` occurs during processing.
- Export the module's memory (`WebAssembly.Module.exports` check for `memory`) and surface `buffer.byteLength` in telemetry; growth events and current page count are the leading indicators of leaks in compiled code.
- For multi-instance coordination, create the `Memory` on the JS side and import it — never let two instances each export their own and expect to share.

## Validation evidence

- Detachment unit test: create a view, call `memory.grow(1)`, assert the old view's length is 0 and a rebuilt view over `memory.buffer` sees bytes the module wrote — this pins the invalidation rule for reviewers.
- Growth-failure test: set `maximum`, drive the module's allocator past the cap, and assert the surfaced error is the `WebAssembly.RuntimeError`/grow-failure path with your telemetry attached, not a silent hang.
- Latency trace: instrument grow events with `performance.now()` deltas around a workload loop; assert no grow occurs inside the audio callback or animation frame in the steady-state profile.
- Transfer test: post a non-shared `mem.buffer` to a worker, assert the sender-side buffer detaches and the module reads zeros (expected failure mode), then repeat with `SharedArrayBuffer` and assert visibility both sides.

## Failure modes and correction

- Silent data corruption or zeroed reads after a worker call: a non-shared buffer was transferred, detaching it for the module still holding the old reference. Use shared memory or stop transferring; never transfer a memory backing a live module.
- `TypeError: Cannot perform Construct on a detached ArrayBuffer` at what looks like a random time: a cached view outlived a `grow`. Rebuild views after any call into the module that can allocate, or switch to `SharedArrayBuffer`-backed memory where views never invalidate.
- Module reports OOM far below the machine's capability: `maximum` was set too low at instantiation or the toolchain emitted a fixed memory in the wasm binary. Re-link with a larger descriptor, or recompile with the toolchain's allow-grow flag.
- Jank spikes or audio dropouts correlated with load: `grow` reallocation copying on the hot thread. Preallocate to peak, or move the workload to a worker so the copy is off the main thread.
- Two instances "share" data but see different contents: each instantiated its own memory because none was imported; import one shared `Memory` object into both.
- Address-space confusion after growth: offsets are valid, cached base pointers are not — recompute any stored `byteOffset`/`length` pairs after each grow event, since lengths in pages changed.

## Limitations

- 32-bit memories top out at 4 GiB (65,536 pages); the memory64 proposal extends this but engine and toolchain coverage must be verified per target before relying on it.
- Growth of a non-shared memory is always buffer-replacing; there is no in-place guarantee an embedding can rely on, so view invalidation must be treated as unconditional.
- The GC proposal's managed objects live outside linear memory entirely; this article's mechanics do not apply to those heaps.
- Engine-specific copy-on-grow heuristics mean "grow is cheap" claims must be measured on each target runtime, not assumed.
- `SharedArrayBuffer` requires cross-origin isolation headers site-wide, which conflicts with third-party embeds that can't be COEP-filtered.

## Canonical sources

- WebAssembly CG, Memory instructions (spec): https://webassembly.github.io/spec/core/exec/instructions.html#memory-instructions
- MDN, `WebAssembly.Memory`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/WebAssembly/Memory
- MDN, `Memory.grow()`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/WebAssembly/Memory/grow
- WebAssembly CG, Threads and shared memory overview: https://webassembly.org/roadmap/
