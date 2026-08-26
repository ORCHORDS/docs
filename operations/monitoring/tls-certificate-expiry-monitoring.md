# tls-certificate-expiry-monitoring

**Issue:** Alerting on TLS certificate expiry before certificates expire and break HTTPS connections
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Certificate expires and users get browser security warnings or API clients reject connections. Expiry is predictable.

## Pattern / Solution
Use Blackbox Exporter probe_ssl_earliest_cert_expiry: alert at 30 days and critical at 14 days. Prometheus rule: (probe_ssl_earliest_cert_expiry - time()) / 86400 less than 30. For internal certs use x509-certificate-exporter. For cert-manager managed certs track certmanager_certificate_expiration_timestamp_seconds. Include all SANs in monitoring.

## Gotchas
cert-manager renewal failures can be silent — track certmanager_certificate_ready_status. Let's Encrypt rate limits: 5 duplicate certificates per week. Monitor certificates from both inside and outside the cluster. Intermediate CA expiry can silently break chains without leaf cert expiry.

## Related
dns-resolution-monitoring, blackbox-monitoring, uptime-monitoring-patterns
