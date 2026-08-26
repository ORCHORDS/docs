# structuredClone Transfer Detaches the Source Buffer

**Issue:** Using the transfer option moves ownership of transferable objects. Code that later reads the original ArrayBuffer can observe a zero-length detached buffer rather than an independent copy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Choose explicitly between cloning and transfer for each ownership boundary.
- After transfer, clear or invalidate every source reference and prevent concurrent consumers.
- Keep shared ownership on SharedArrayBuffer under a separate synchronization policy.
- Validate transfer lists so the same transferable is not assumed usable by multiple subsystems.

## Verification

- Transfer an ArrayBuffer and assert the source byteLength becomes zero while the clone retains bytes.
- Attempt duplicate or unsupported transfer-list entries and assert failure.
- Race queued source consumers around the transfer boundary.

## Gotchas

- Transfer is not deep-copy semantics.
- Detachment can surface far from the transfer call when aliases remain.

## Official sources

- https://html.spec.whatwg.org/multipage/structured-data.html#structured-cloning
