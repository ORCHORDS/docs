# Targeted CDN cache-control precedence

**Issue:** A response sends `Cache-Control` and `CDN-Cache-Control` but operators assume a CDN combines their directives. RFC 9213 precedence instead lets a valid targeted field replace ordinary freshness policy for that cache, causing unexpected storage or Age behavior downstream.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## RFC 9213 model

Targeted cache-control fields are Structured Fields dictionaries. `CDN-Cache-Control` targets CDN caches. A supporting cache maintains an ordered target list; for each response it selects the first listed targeted field with a valid, non-empty value. It uses that value for caching policy and ignores `Cache-Control` and `Expires` for itself. If no targeted value is valid and non-empty, it falls back to ordinary HTTP cache controls.

A field not on a cache's target list must not change that cache's behavior and is passed through. Therefore one response can intentionally express different CDN, shared-cache, and browser policies.

Do not parse `CDN-Cache-Control` with an ordinary Cache-Control string parser. RFC 9213 uses Structured Fields parsing and has different error handling. An empty or invalid targeted field is ignored.

## Policy pattern

```http
Cache-Control: max-age=60, s-maxage=120
CDN-Cache-Control: max-age=600
```

A supporting CDN can consider this fresh for 600 seconds; other shared caches use 120 seconds and remaining caches use 60 seconds. The CDN policy is not additive to those values.

Controls:

1. Emit targeted policy from one reviewed layer so application, proxy, and CDN do not append conflicting field lines.
2. Keep sensitive/personalized responses non-storable in every applicable policy. A restrictive ordinary field does not protect against an accidentally permissive targeted field used by the CDN.
3. Verify the provider actually implements RFC 9213 and document its target-list precedence, including any vendor-specific targeted field.
4. Configure purge/invalidation before granting a longer CDN lifetime.
5. Treat unknown extension directives as ignored per their defined semantics; never use an invented “deny” directive as the sole privacy control.
6. Validate the serialized Structured Field in tests and at the edge.

## Freshness and Age

A CDN can serve an object under a longer targeted lifetime whose `Age` already exceeds downstream `Cache-Control: max-age`. Downstream caches may see it as stale immediately, reducing efficiency or triggering revalidation. Test the complete chain and document any compliant Age/Date mitigation used by the deployment.

## Verification

Probe origin, each CDN layer, an independent shared proxy, and browser-like cache. Test absent, empty, malformed, duplicate, vendor-specific and generic targeted fields; `no-store`/`private`; purge; revalidation; and an Age value between ordinary and targeted lifetimes. Inspect actual cache status and Age, not just response headers at origin.

## Gotchas

- The targeted field changes policy only for caches that select it.
- Header suffix convention alone does not define a registered targeted field.
- Multiple policies increase leakage risk and need one security review.
- Long TTL without reliable invalidation increases incident recovery time.

## Sources

- [RFC 9213 — Targeted HTTP Cache Control](https://www.rfc-editor.org/rfc/rfc9213.html)
