# Node Buffer slice shares backing memory

**Issue:** Code uses `Buffer.prototype.slice()` expecting TypedArray copy semantics, then a write through either result silently changes the other view or exposes pooled bytes through an incorrectly handled backing `ArrayBuffer`.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Cause

Unlike `TypedArray.prototype.slice()`, Node's deprecated `Buffer.prototype.slice()` creates a view over the original Buffer without copying. `Buffer.prototype.subarray()` intentionally has the same shared-memory behavior and is the preferred API only when aliasing is wanted. `Buffer.from(arrayBuffer, byteOffset, length)` also creates a view of the supplied backing buffer.

## Controls

- Name APIs and variables to make ownership explicit: `view`, `borrowed`, or `copy`.
- Use `buf.subarray(start, end)` for an intentional zero-copy view.
- Use `Buffer.from(buf.subarray(start, end))` when an independent Buffer is required.
- Never expose `buf.buffer` without also preserving and validating `buf.byteOffset` and `buf.byteLength`; pooled Buffers can reference a larger allocation.
- Copy at trust, lifetime, queue, cache, worker, and cryptographic-key boundaries unless shared ownership is part of the contract.
- Treat returned mutable Buffers as owned values or document that the caller may mutate shared storage.
- Retain the parent Buffer while a view remains in use and avoid holding a tiny view that pins a large allocation.

## Verification

```js
import { Buffer } from "node:buffer";
import assert from "node:assert/strict";

const source = Buffer.from([1, 2, 3, 4]);
const view = source.subarray(1, 3);
const copy = Buffer.from(view);

view[0] = 9;
assert.equal(source[1], 9);
assert.deepEqual([...copy], [2, 3]);
```

Add mutation tests in both directions and a pooled-Buffer test that checks exact offset and length. Run tests under every supported Node line because native addons and serialization layers can introduce additional ownership boundaries.

## Gotchas

Replacing `slice()` mechanically with `subarray()` removes a deprecation warning but does not remove aliasing. `Object.freeze()` does not make Buffer bytes immutable. A zero-copy view can be correct and faster, but it must have one documented owner and lifetime.

## Official sources

- [Node.js Buffer documentation](https://nodejs.org/api/buffer.html#buffers-and-typedarrays)
- [Node.js buf.slice documentation](https://nodejs.org/api/buffer.html#bufslicestart-end)
