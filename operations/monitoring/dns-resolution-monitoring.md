# dns-resolution-monitoring

**Issue:** Monitoring DNS resolution health and latency to catch misconfiguration and failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Services occasionally fail to connect to dependencies. Root cause is DNS resolution failures or slow responses.

## Pattern / Solution
Use Blackbox Exporter DNS module to probe critical DNS names from within cluster and from external vantage points. Alert on probe_dns_lookup_time_seconds exceeding 0.5 or probe_success equal to 0. Track coredns_dns_requests_total and non-NOERROR response rates for cluster DNS health. Monitor NXDOMAIN rates — spikes indicate misconfigurations.

## Gotchas
CoreDNS caches responses — a bad TTL can cause stale DNS for minutes. ndots:5 in default Kubernetes DNS config causes unnecessary FQDN searches — tune or use explicit FQDNs. DNS resolution failure often manifests as connection timeout, not a clear DNS error.

## Related
network-latency-monitoring, blackbox-monitoring, tls-certificate-expiry-monitoring
