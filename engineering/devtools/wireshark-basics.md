# wireshark-basics

**Issue:** Network-level debugging needed beyond HTTP — TCP, DNS, TLS handshake issues
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
App connects but responses are wrong at protocol level; Charles only shows HTTP layer.

## Pattern / Solution
Wireshark captures all packets on network interface. Display filter: http, dns, tcp.port==5432. Follow TCP Stream to reconstruct conversation. TLS decryption requires SSLKEYLOGFILE environment variable. Use tshark for CLI capture.

## Gotchas
- SSLKEYLOGFILE must be set before launching the app, not after
- Capture on loopback (lo0) for local service-to-service traffic

## Related
- charles-proxy-debugging, curl-advanced-usage
