# Cache Correctness for Agent Retrieval and Tool Calls

## Scope

Caching can reduce latency and dependency load, but an agent may reuse data under a different identity, authorization state, tool version, or task context. This article covers correctness and safety for cached retrieval and read-only tool results. It excludes long-term conversational memory and protocol list-result caching already covered elsewhere. The key rule is that a cache hit must be semantically equivalent to an authorized fresh read within a documented freshness policy.

HTTP caching provides mature semantics for cache keys, freshness, validators, invalidation, and shared-cache restrictions. OWASP authorization guidance requires permission checks on every request and denial by default. An agent cache should combine these principles rather than treating a result digest as sufficient authority.

## Workflow

1. Classify an operation as cacheable only if it is read-only, deterministic enough for the use, and approved by the data owner. Side-effecting calls are never converted into cache hits.
2. Build a canonical key from operation identity, normalized inputs, representation variant, tool and schema revision, tenant boundary, and authorization partition. Exclude irrelevant ordering while preserving meaning.
3. Perform authorization before lookup or bind the entry to an authorization decision whose subject, resource, action, policy revision, and expiry are all still valid.
4. On lookup, verify freshness, integrity metadata, schema revision, and visibility scope. A stale entry may be used only under an explicit stale policy and must be labeled.
5. Revalidate with an origin validator when supported. Treat a changed validator as a new representation and validate it before publication.
6. Prevent stampedes with bounded request coalescing. Coalesced callers retain independent authorization and cancellation outcomes.
7. On writes or policy changes, invalidate by resource identity or advance a namespace revision. Prefer versioned keys where complete deletion cannot be guaranteed.
8. Return cache status and data age to downstream decision logic when freshness affects action safety.

## Controls, data, and evidence

Separate tenant namespaces physically or cryptographically where practical. Never key only on natural-language query text. Include locale, content negotiation, feature policy, and tool version when they affect output. Apply maximum object size, total capacity, eviction policy, and encryption appropriate to the data classification. Validate cached objects again when a consumer expects a newer schema.

A cache entry should store canonical key digest, origin, resource identity, authorization partition, creation and validation times, freshness lifetime, validator, schema and tool revisions, integrity digest, and invalidation generation. Avoid copying credentials into keys or values. Evidence includes cacheability approvals, key-design reviews, authorization-isolation tests, invalidation drills, stale-use policy, and hit/miss metrics partitioned by bounded operation labels.

## Validation tests

Have two tenants issue identical queries and verify neither receives the other's entry. Revoke a user's access while an entry remains fresh; the next lookup must deny or require a still-valid bound authorization decision. Change output schema and confirm old entries miss or fail validation. Test variant dimensions such as locale and accepted media type.

Issue concurrent misses and confirm one bounded origin request serves only independently authorized callers. Cancel the leader and ensure coalesced work has a defined ownership rule. Simulate origin failure with stale data inside and outside the allowed window. Verify stale data cannot authorize irreversible action if policy permits it only for display. Test invalidation races with an update arriving while a read is filling the cache; generation checks must prevent the older value from being published after the update.

## Failure handling

If cache metadata is incomplete or corrupt, treat the entry as a miss and quarantine or evict it. If authorization infrastructure is unavailable, do not serve protected shared entries merely because they were previously authorized. A narrow public-data cache can remain available when its classification is independently established.

When invalidation delivery is delayed, version checks at read time should prevent stale generations from being accepted. If cross-tenant contamination is detected, disable the affected namespace, preserve metadata and digests, invalidate impacted entries, assess disclosures, and restore service only after isolation tests pass. If the origin is unavailable, surface `stale` or `unavailable` explicitly; never represent cached age as fresh retrieval.

## Limitations

Invalidation cannot be perfectly instantaneous across all distributed stores. Authorization-dependent representations can make shared caching inefficient. A valid cache entry may still contain incorrect source data. Validators identify representation changes but do not necessarily express business validity. Probabilistic eviction and eventual consistency complicate reproducibility. Caching also cannot replace source availability planning or data-quality controls.

## Canonical sources

- **IETF, HTTP Caching (RFC 9111):** https://www.rfc-editor.org/rfc/rfc9111.html
- **IETF, HTTP Semantics (RFC 9110):** https://www.rfc-editor.org/rfc/rfc9110.html
- **OWASP, Authorization Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
