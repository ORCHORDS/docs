# Server-Timing observability without data exposure

**Issue:** Browser timings show when a response arrived, but not where server-side time was spent. Adding diagnostics carelessly can expose topology, identifiers, cache state, or internal operation names to arbitrary page contexts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Use the standard boundary

The `Server-Timing` response header carries named server-side metrics. Browser performance entries expose them as `PerformanceServerTiming` values on navigation and resource timings. Use short, stable metric names with millisecond durations, such as `app`, `db`, `cache`, and `edge`; define their meaning and ownership in an internal metric catalogue.

## Safe rollout

- Start with a small allowlist of aggregate durations, not request IDs, hostnames, user identifiers, query text, error details, or sensitive topology.
- Keep metric names and descriptions compact: headers add response bytes and descriptions can leak implementation detail.
- Measure full request timing separately from component timings; components may overlap and therefore must not be naively summed.
- Use the same metric definitions in server telemetry and browser/RUM processing so that regressions can be correlated.
- Gate detailed metrics by environment, route class, or authenticated diagnostic access when public exposure is not required.
- For cross-origin resources, expose timing only with a deliberate `Timing-Allow-Origin` policy. Do not add a wildcard simply to make dashboards easier.
- Test caching, CDN, error, streaming, and trailer paths: intermediaries can add or alter timing and metrics must retain an unambiguous owner.

## Review checklist

1. Does every metric have a documented unit, owner, and privacy classification?
2. Are public responses free of internal system names and customer data?
3. Can the frontend distinguish a missing metric from a true zero duration?
4. Does the RUM pipeline sample and retain this data proportionately?
5. Are alert thresholds based on service SLOs rather than a single component histogram?

## Sources

- [W3C Server Timing](https://www.w3.org/TR/server-timing/)
- [W3C Resource Timing](https://www.w3.org/TR/resource-timing-2/)

## Tags

`performance` `observability` `server-timing` `rum` `privacy`
