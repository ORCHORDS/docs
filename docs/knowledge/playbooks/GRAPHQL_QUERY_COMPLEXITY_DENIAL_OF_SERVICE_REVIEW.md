# GraphQL Query Complexity and Denial-of-Service Review

## Purpose

Verify that GraphQL and similar expressive data-query interfaces constrain expensive, deeply nested, or excessively broad queries so one request cannot consume disproportionate compute, database, memory, or downstream resources.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-4.3.1 requires a query allowlist, depth limiting, amount limiting, query-cost analysis, or equivalent protection against denial of service from expensive nested GraphQL or data-layer expressions.

## Inputs

- GraphQL schema and resolver inventory;
- query complexity, depth, amount, or allowlist configuration;
- representative production-like data shape and authorization context;
- observability for resolver, database, cache, downstream API, and compute cost.

## Procedure

1. **Identify expensive paths.** Map fields and resolvers that can fan out, paginate, recurse, aggregate, call external services, or perform costly computation.
2. **Inspect configured limits.** Record query-depth, field-count, alias, pagination, batching, cost-analysis, persisted-query, and request-size controls that are actually enforced.
3. **Test deep nesting.** Submit nested queries near and beyond the supported depth and verify over-limit requests fail before expensive execution.
4. **Test breadth and aliases.** Request many sibling fields or repeated aliased fields to confirm width cannot bypass intended cost controls.
5. **Test pagination abuse.** Attempt excessive page sizes, nested pagination, or repeated connections and verify bounded values are enforced by trusted server logic.
6. **Test expensive field combinations.** Combine individually valid fields whose aggregate resolver or database cost is materially higher than a normal query.
7. **Test fragments and variables.** Confirm fragments, reusable selections, directives, and variable-driven arguments do not bypass static or runtime cost analysis.
8. **Review persisted-query/allowlist behavior.** Where allowlists or persisted queries are used, verify unknown or modified operations cannot silently fall back to unrestricted execution.
9. **Observe downstream impact.** Measure resolver count, database work, memory, latency, and downstream calls so accepted thresholds reflect actual resource consumption.
10. **Review layered controls.** Confirm general rate limits and quotas complement query-level complexity controls rather than serving as the only defense.

## Evidence

Record tested query shapes, configured thresholds, rejection behavior, measured downstream cost, application/schema revision, and any accepted exceptions or remediation owners.

## Completion criteria

The review is complete when intentionally expensive query shapes are bounded before disproportionate resource consumption, nested and broad requests cannot bypass controls, and accepted limits are supported by observed resource evidence.

## Sources

- OWASP ASVS 5.0.0, V4.3 GraphQL: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x13-V4-API-and-Web-Service.md
- OWASP Web Security Testing Guide, GraphQL Testing: https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/12-API_Testing/01-Testing_GraphQL

## Scope note

Complexity protection does not replace authorization, input validation, rate limiting, database performance controls, or downstream service quotas.
