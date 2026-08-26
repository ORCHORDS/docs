# dns-ttl-strategy

**Issue:** Choosing DNS TTL values that balance propagation speed with resolver load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Setting TTL too high causes slow failover during incidents. Setting it too low increases query volume and cost on authoritative nameservers, and may be ignored by some resolvers anyway.

## Pattern / Solution
Use a tiered TTL strategy based on record type and change frequency.

| Record type | Normal TTL | Pre-change TTL | Rationale |
|-------------|-----------|---------------|-----------|
| A / AAAA    | 300 s     | 60 s          | Short enough for fast failover |
| CNAME       | 300 s     | 60 s          | Same as A |
| MX          | 3600 s    | 300 s         | Mail queues tolerate delay |
| TXT (SPF)   | 3600 s    | 3600 s        | Rarely changes |
| NS          | 86400 s   | 3600 s        | Managed by registrar; reduce well before migration |
| SOA         | 3600 s    | —             | Set negative TTL (min field) to 60–300 |

Migration playbook:
```
T-48h  Lower TTL of affected records to 60 s
T-0    Make the DNS change
T+5m   Verify propagation with dig @8.8.8.8
T+1h   Raise TTL back to normal value
```

Cloudflare-proxied records always return a TTL of 300 s regardless of what you configure; set the Cloudflare-side TTL to "Auto" and tune at the origin.

## Gotchas
- Reducing TTL before a migration is the single most impactful step — do it at least 2× the current TTL before the change.
- Some CDNs and load balancers set very low TTLs (30 s) that inflate authoritative query costs; use their health-check features instead of DNS round-robin.
- Negative caching TTL is separate from positive TTL and is set in the SOA `minimum` field.
- DNSSEC signatures have their own validity window (often 7 days); factor this into zone-signing key roll-over timelines.

## Related
- `dns-propagation-debugging.md`
- `cloudflare-dns-api.md`
- `load-balancer-health-checks.md`
