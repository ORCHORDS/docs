# Treat RFC 9535 JSONPath Results as Node Lists

**Issue:** JSONPath selects an ordered node list, not a universal scalar value. Duplicate nodes, missing selections, object order, and singular-query assumptions affect updates and authorization.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Use RFC 9535 syntax and classify expressions as singular or nonsingular.
- Define whether consumers need node identity, normalized paths, values, or all three.
- Preserve result ordering and duplicates unless application semantics explicitly transform them.
- Bound recursive descent and filter complexity for untrusted expressions.
- Separate selection from mutation and authorization.

## Verification
- Run RFC examples plus missing members, arrays, duplicate selection, Unicode names, deep recursion, filters, and reordered objects.
- Compare implementations on normalized paths and node lists.
- Fuzz expression depth and resource limits.

## Gotchas
A one-element result is still a node list. JSON object member order is not a semantic sorting guarantee.

## Official sources
- [RFC 9535](https://www.rfc-editor.org/rfc/rfc9535.html)
