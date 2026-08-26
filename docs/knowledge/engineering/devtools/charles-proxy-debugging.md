# charles-proxy-debugging

**Issue:** HTTP traffic from mobile apps or browsers not visible for debugging
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
API calls from iOS/Android app fail in production; need to inspect actual requests and responses.

## Pattern / Solution
Charles Proxy intercepts HTTP/HTTPS traffic. Configure device to use Charles as proxy (host IP, port 8888). Install Charles root cert on device for HTTPS. Use SSL Proxying for specific domains. Breakpoints modify requests and responses in flight.

## Gotchas
- Certificate pinning in apps blocks Charles interception — requires app modification
- Charles is paid (30-day trial); alternatives: mitmproxy (free, CLI-based), Proxyman (macOS)

## Related
- wireshark-basics, curl-advanced-usage, postman-collections
