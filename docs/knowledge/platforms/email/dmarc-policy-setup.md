# dmarc-policy-setup

**Issue:** Publishing a DMARC record to enforce SPF/DKIM alignment and receive aggregate reports
**Date:** 2026-08-11
**Status:** documented

## Pattern / Solution
Add a TXT record at `_dmarc.yourdomain.com`:

```
v=DMARC1; p=none; rua=mailto:dmarc-reports@yourdomain.com; ruf=mailto:dmarc-forensic@yourdomain.com; fo=1; adkim=r; aspf=r; pct=100
```

Tag reference:
- `p=none|quarantine|reject` — policy applied to failing messages
- `rua=` — aggregate report destination (daily XML)
- `ruf=` — forensic report destination (per-message; privacy-sensitive)
- `fo=1` — generate forensic report on any auth failure (not just DMARC fail)
- `adkim=r` — relaxed DKIM alignment (subdomain matches parent)
- `aspf=r` — relaxed SPF alignment
- `pct=` — percentage of mail the policy applies to (use < 100 during rollout)

Rollout sequence:
1. `p=none; pct=100` — monitor for 2–4 weeks
2. `p=quarantine; pct=10` — gradually increase pct
3. `p=quarantine; pct=100` — full quarantine
4. `p=reject; pct=100` — full enforcement

## Gotchas
- DMARC requires either SPF **or** DKIM to both pass **and** align with the `From:` domain
- Forwarded mail often breaks SPF alignment; ARC is the mitigation
- `ruf=` forensic reports may contain full message content; treat the inbox as sensitive
- Google and Yahoo require `p=quarantine` or `p=reject` for bulk senders as of 2024

## Related
- `spf-record-setup.md`
- `dkim-record-setup.md`
- `dmarc-rua-reporting.md`
- `arc-authenticated-received-chain.md`
