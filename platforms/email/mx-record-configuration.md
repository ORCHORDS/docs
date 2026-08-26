# mx-record-configuration

**Issue:** Configuring MX records for receiving email on a domain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
MX records determine which mail servers receive email for a domain; misconfiguration causes missed mail.

## Pattern / Solution
1. MX records specify mail server hostnames with priority values (lower = higher priority):
```
yourdomain.com. 300 IN MX 10 mail1.yourdomain.com.
yourdomain.com. 300 IN MX 20 mail2.yourdomain.com.
```
2. For Google Workspace:
```
MX 1  aspmx.l.google.com.
MX 5  alt1.aspmx.l.google.com.
MX 5  alt2.aspmx.l.google.com.
MX 10 alt3.aspmx.l.google.com.
MX 10 alt4.aspmx.l.google.com.
```
3. For inbound-only via Cloudflare Email Routing: add Cloudflare's provided MX records.
4. Verify with: `dig MX yourdomain.com` or MXToolbox.

## Gotchas
- MX records must point to hostnames (A records), not IP addresses.
- TTL of 300-3600 is typical; lower TTL allows faster failover.
- Multiple MX records with same priority act as round-robin load balancing.
- Removing all MX records disables email reception; servers then try A record (fallthrough behavior).

## Related
- cloudflare-email-routing, email-forwarding-setup, email-catch-all-patterns, inbound-email-processing
