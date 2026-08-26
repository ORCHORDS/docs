# pytest RaisesGroup exception-structure contracts

**Issue:** Catching `ExceptionGroup` and checking only flattened exception types can let an extra nested error, wrong grouping boundary, or unexpected message pass unnoticed.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use pytest's `RaisesGroup` and `RaisesExc` matchers to express the expected exception-group shape instead of manually traversing or flattening `.exceptions`. Make nesting, allowed subclasses, messages, and cause/context expectations explicit where they are part of the behavior. Prefer a strict shape for security, transaction, and concurrency boundaries so an additional exception cannot hide inside a broadly accepted group.

Keep each matcher small and named after the failure contract. When using it with `pytest.raises`, `pytest.mark.xfail(raises=...)`, or matcher checks, assert the same semantic outcome; xfail should document a specific known defect rather than accepting any grouped failure.

## Verification

Test the exact group, wrong leaf type, extra leaf, deeper and shallower nesting, subclass, message mismatch, cause/context, and an ordinary non-group exception. Include the matcher failure explanation in test review to ensure a future failure remains diagnosable.

## Gotchas

- Exception groups preserve structure; flattening loses concurrency provenance.
- Broad subclass matching can admit unrelated errors.
- xfail that accepts the wrong structure can turn a regression into an expected result.

## Official source

- [pytest assertion and exception-group guidance](https://docs.pytest.org/en/stable/how-to/assert.html#assertions-about-expected-exception-groups)
