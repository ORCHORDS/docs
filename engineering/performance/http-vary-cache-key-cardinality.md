# HTTP Vary cache-key cardinality

**Issue:** An origin adds high-entropy request headers to `Vary` until cache correctness “looks safe.” Each request becomes a new variant, hit rate collapses, and inconsistent `Vary` values can serve a default representation for requests that needed a negotiated one.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## RFC 9111 matching rules

A stored response containing `Vary` cannot be reused without revalidation unless every nominated request header matches the corresponding header from the original request. Matching can normalize whitespace, combined field lines, and values only where that header's semantics declare transformations equivalent.

An absent nominated header matches only another absence. A `Vary: *` stored response always fails to match. `Vary` extends the cache key; it does not itself make a response cacheable or private.

## Design controls

1. List the smallest request-header set that actually selects representation bytes or representation-relevant metadata.
2. Emit the same correct `Vary` contract on every response for a negotiable resource, including the default path, errors where reusable, 304 responses, and edge-generated variants.
3. Do not vary on raw high-cardinality values such as `User-Agent`, trace IDs, cookies, authorization, or arbitrary client hints. Derive a bounded server-side representation bucket and expose only a stable low-cardinality selector when the protocol permits.
4. Keep personalization out of shared caches unless the cache key and storage authorization are deliberately designed. `Vary: Cookie` usually partitions into near-unique variants and can still be unsafe when intermediaries handle it unexpectedly.
5. Canonicalize at the representation-selection layer; do not assume all caches implement vendor-specific key transforms.
6. Bound language and encoding negotiation. Normalize supported choices to a small resource set and return the matching `Content-Language`/`Content-Encoding`.
7. Purge all variants when changing the `Vary` set or bucketing algorithm.

## Cardinality budget

Estimate the product—not sum—of values for every nominated header on each URL. A route varying by 8 language buckets, 3 encodings, 4 device representations, and 5 experiments can create 480 entries before query strings or regions.

Instrument unique variant keys, requests per key, hit ratio, eviction rate, origin fetches, and response hash by bucket. Reject a new dimension unless its correctness/benefit justifies the multiplicative cost.

## Verification

For each route, generate the Cartesian product of present/absent headers, allowed values, whitespace/case variants permitted by field semantics, unsupported values, and default requests. Assert equivalent requests reuse a representation and non-equivalent requests never do. Include `Vary: *`, conditional revalidation, multiple cache layers, 304 merging, and a default response with no preference headers.

## Gotchas

- Omitting `Vary` on the default response can poison later negotiated requests.
- Header name case is insensitive; field value normalization depends on that field's specification.
- A cache may include additional partitioning beyond `Vary`.
- Cache hit ratio can rise while correctness falls; use representation mismatch canaries.

## Sources

- [RFC 9111 — HTTP Caching, Section 4.1](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1)
