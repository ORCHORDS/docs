# email-reputation-monitoring

**Issue:** Continuously tracking sending reputation across major ISPs and blacklists
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deliverability degrades gradually without any obvious signal until you are blocked by a major ISP.

## Pattern / Solution
Monitoring stack:

**Google Postmaster Tools** (`postmaster.google.com`)
- Domain reputation: High / Medium / Low / Bad
- IP reputation per sending IP
- Spam rate (% of delivered mail marked spam by Gmail users)
- Authentication pass rates

**Microsoft SNDS** (`sendersupport.olc.protection.outlook.com/snds`)
- Daily trap hits, complaint rate, IP colour coding (green/yellow/red)

**Blacklist monitoring**
```bash
# Check MXToolbox for all major lists
curl "https://mxtoolbox.com/api/v1/lookup/blacklist/203.0.113.10" \
  -H "Authorization: Bearer YOUR_KEY"
```

Major blacklists to monitor:
- Spamhaus (SBL, XBL, PBL)
- SURBL
- Barracuda (BRBL)
- SpamCop

**Automated alerting**
```yaml
# Datadog monitor example
metric: email.complaint_rate
threshold: 0.001  # 0.1%
notify: oncall-email-team
```

## Gotchas
- Google Postmaster data is only available if you send >100 messages/day to Gmail
- Blacklist listings require a delisting request; some are automatic after fixing the issue, others are manual
- Reputation data is usually 24–48 hours delayed

## Related
- `google-postmaster-setup.md`
- `microsoft-snds-setup.md`
- `complaint-rate-monitoring.md`
- `postmaster-tools-setup.md`
