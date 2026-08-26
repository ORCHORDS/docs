# JavaScript toSorted sparse-array densification

**Issue:** `Array.prototype.toSorted()` is non-mutating, but it does not preserve sparse holes. Its algorithm reads through holes, treats absent indices as `undefined` unless a prototype supplies a value, and creates an own data property at every output index, producing a dense array.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Decide whether holes and explicit `undefined` have different domain meaning before replacing `sort()` with `toSorted()`.
- Normalize sparse input intentionally or reject it at the boundary when downstream code relies on property presence.
- Use `Object.hasOwn()` or the `in` operator when testing sparsity; equality with `undefined` cannot distinguish a hole.
- Keep numeric, string, and domain comparators consistent, side-effect free, and deterministic.
- Avoid indexed values on `Array.prototype` or a custom prototype; read-through behavior can materialize inherited values.
- Include sparsity and own-property shape in serialization, validation, and memory regressions where large arrays are possible.

## Implementation and tests

Build fixtures containing leading, interior, and trailing holes; explicit `undefined`; inherited indexed properties; accessors; and a proxy. Compare `sort()` with `toSorted()` using values, length, `Object.keys()`, `Object.hasOwn(result, index)`, and prototype access. Assert the source remains unchanged and every index in the `toSorted()` result is an own property.

Test default string ordering, a numeric comparator, a comparator that returns zero for ties, and a comparator that throws. Verify stable ordering for a consistent comparator and fail the test if application code accidentally relies on comparator calls for `undefined`.

## Gotchas

The specification invokes `SortIndexedProperties` with `read-through-holes` for `toSorted()`, then creates a new array property for every index. By contrast, `sort()` uses `skip-holes` and deletes remaining indices so holes remain at the end.

The copy is shallow: object elements remain shared. “Non-mutating” describes the source array structure, not objects referenced by its elements or side effects from getters and comparators.

## Official sources

- [ECMAScript specification: Array.prototype.toSorted](https://tc39.es/ecma262/multipage/indexed-collections.html#sec-array.prototype.tosorted)
- [ECMAScript specification: SortIndexedProperties](https://tc39.es/ecma262/multipage/indexed-collections.html#sec-sortindexedproperties)
