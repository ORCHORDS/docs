# http3-quic-benefits

**Issue:** TCP head-of-line blocking and slow connection setup hurt performance on lossy networks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
HTTP/3 runs over QUIC (UDP-based), eliminating TCP head-of-line blocking. Connection setup takes 0-RTT for returning users. Critical for mobile users on lossy networks.

## Pattern / Solution
1. Enable QUIC on Cloudflare, nginx (with nginx-quic patch), or Caddy.\n2. Serve Alt-Svc: h3=:443 header so browsers upgrade to HTTP/3.\n3. Verify with Chrome chrome://net-internals/#quic or WebPageTest.\n4. Ensure UDP port 443 is open through your firewall and load balancer.\n5. Cloudflare automatically enables HTTP/3; opt-in per zone in Speed settings.

## Gotchas
- Some corporate firewalls block UDP; browsers fall back to HTTP/2 automatically.\n- QUIC benefits are most visible on high-latency or lossy connections -- lab tests may not show improvement.\n- 0-RTT resumption has replay attack implications; avoid for non-idempotent requests.

## Related
http2-multiplexing, cloudflare-workers-performance, ttfb-optimization
