# server-side-request-forgery-ssrf

**Issue:** User-controlled URLs passed to server-side HTTP clients enable SSRF to internal services and cloud metadata APIs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Webhooks, URL preview features, and PDF generators that accept user-supplied URLs can be weaponized to fetch `http://169.254.169.254/` (AWS/GCP metadata), internal Redis, or other services not exposed to the internet.

## Pattern / Solution
```javascript
import dns from 'dns/promises';
import net from 'net';

const BLOCKED_CIDRS = [
  '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
  '169.254.0.0/16', '127.0.0.0/8', '::1/128', 'fc00::/7'
];

async function isSafeUrl(urlString) {
  const url = new URL(urlString);
  if (!['http:', 'https:'].includes(url.protocol)) return false;
  const { address } = await dns.lookup(url.hostname);
  return !isPrivateIP(address); // implement CIDR check
}

// Better: use a dedicated SSRF-prevention library
// npm: ssrf-agent, got with block-private-ips option
```
```python
# Use ssrfcheck or validators.url with private-ip blocking
from ssrfcheck import is_safe_url
if not is_safe_url(user_url):
    raise ValueError('SSRF blocked')
```

## Gotchas
- DNS rebinding: hostname resolves to public IP at validation time, then re-resolves to internal IP at fetch time — pin the resolved IP into the HTTP request.
- Redirects can bypass allowlists — follow redirects with the same IP validation.
- IPv6 addresses, decimal-encoded IPs (`http://2130706433/` = 127.0.0.1), and octal encoding all bypass naive blocklists.
- Cloud metadata endpoints vary by provider: AWS `169.254.169.254`, GCP same, Azure `169.254.169.254/metadata`, DigitalOcean `169.254.169.254`.

## Related
- `path-traversal-prevention.md`
- `xxe-injection-prevention.md`
