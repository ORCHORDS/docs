# blackbox-monitoring

**Issue:** Monitoring services from the outside as a user would, without access to internals
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Internal metrics show everything is fine but users cannot connect. Need external perspective on availability and correctness.

## Pattern / Solution
Deploy Prometheus Blackbox Exporter to probe HTTP(S), TCP, DNS, and ICMP endpoints. Configure modules in blackbox.yml with expected status codes and TLS checks. Scrape via Prometheus and alert on probe_success == 0 or probe_duration_seconds exceeding threshold. Combine with multi-region synthetic checks for geographic coverage.

## Gotchas
Blackbox exporter runs from within your infrastructure — it catches network issues between exporter and target, not between internet and target. TLS certificate checks are useful: alert on certs expiring within 14 days.

## Related
whitebox-monitoring, uptime-monitoring-patterns, tls-certificate-expiry-monitoring, prometheus-setup-basics
