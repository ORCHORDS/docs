# dns-propagation-debugging

**Issue:** Diagnosing why DNS changes are not visible globally after a record update
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After updating an A, CNAME, or MX record, some clients see the old value while others see the new one. CI pipelines, monitoring, or users in specific regions fail because they resolve the stale record.

## Pattern / Solution
Use multiple vantage points to isolate whether the problem is authoritative, recursive, or local.

```bash
# Check what the authoritative nameservers say (bypasses caching)
dig @ns1.example.com example.com A +short
dig @ns2.example.com example.com A +short

# Check a public resolver (may be cached)
dig @8.8.8.8 example.com A +short
dig @1.1.1.1 example.com A +short

# Show TTL remaining on a cached answer
dig example.com A | grep -E "ANSWER|[0-9]+\s+IN"

# Trace the full resolution chain
dig +trace example.com A

# Test from multiple global vantage points
# Use: https://dnschecker.org or https://www.whatsmydns.net
```

Global propagation timeline by TTL:
- TTL 300 (5 min): ~10–20 min to propagate globally
- TTL 3600 (1 hr): up to 2 hours
- TTL 86400 (24 hr): up to 48 hours (some ISPs ignore TTL)

Flush your local OS cache during testing:
```bash
# macOS
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder

# Linux (systemd-resolved)
sudo resolvectl flush-caches

# Windows
ipconfig /flushdns
```

## Gotchas
- Some ISPs and corporate resolvers cap minimum TTL at 300 s regardless of what you set; you cannot force faster propagation.
- NS record changes propagate via the parent zone and take longer than A/CNAME changes — plan for 24–48 hours.
- `dig +short` hides TTL; always use the full output when debugging stale caches.
- Negative caching (NXDOMAIN) also has a TTL defined in the SOA record's minimum field.

## Related
- `dns-ttl-strategy.md`
- `cloudflare-dns-api.md`
