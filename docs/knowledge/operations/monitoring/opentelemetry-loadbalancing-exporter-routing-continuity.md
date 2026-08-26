# OpenTelemetry load-balancing exporter routing continuity

**Issue:** Round-robin telemetry routing can split one trace or service across stateful downstream processors, while membership churn in consistent routing can still move active keys and fragment data.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Select the `loadbalancing` exporter's routing key from the downstream operation: use trace identity when a tail-sampling tier must see complete traces, or a reviewed service/resource/metric/attribute key for compatible log and metric aggregation. Keep the chosen attribute present and stable at the routing point. Pin the Collector Contrib component version because supported keys and configuration evolve.

Choose static or DNS backend discovery deliberately, monitor the resolved membership set, and budget for key movement during scaling or DNS changes. The exporter hashes a routing key; it does not select the least-loaded backend. Put bounded queues, retry, memory limits, and backend health handling around the exporter, and avoid a configuration where one missing routing attribute creates an unintended hotspot.

## Verification

Send multi-service, multi-span fixtures and prove every required unit reaches one downstream collector. Add/remove DNS endpoints, restart collectors, remove the routing attribute, create skewed keys, and fail a backend. Measure distribution, incomplete traces, duplicate/lost telemetry, queue growth, retries, and recovery time.

## Gotchas

- Consistent hashing reduces movement; it does not eliminate movement.
- A service key may be correct for aggregation but wrong for trace completeness.
- Balanced key counts do not guarantee balanced CPU or byte load.

## Official source

- [OpenTelemetry Collector load-balancing exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/loadbalancingexporter)
