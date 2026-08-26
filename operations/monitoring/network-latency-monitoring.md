# network-latency-monitoring

**Issue:** Measuring and alerting on network latency between services
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Services communicate slowly. Unclear if latency is in the application layer or network layer.

## Pattern / Solution
Instrument outbound HTTP client calls as histograms in your application. Use Prometheus histogram_quantile for p99 latency. For infrastructure-level monitoring use node_network_receive_errs_total and node_network_transmit_errs_total. Add network policy latency checks via Blackbox Exporter TCP probes. Use service mesh (Istio/Linkerd) sidecar metrics for zero-instrumentation service-to-service latency.

## Gotchas
Application-level latency includes connection setup, TLS handshake, and transfer. Cross-AZ latency (1-3ms) is significant for high-frequency RPCs. DNS resolution latency is often overlooked. MTU mismatches cause silent fragmentation that appears as intermittent latency.

## Related
dns-resolution-monitoring, tls-certificate-expiry-monitoring, blackbox-monitoring, apm-transaction-tracing
