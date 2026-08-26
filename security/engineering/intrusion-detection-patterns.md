# intrusion-detection-patterns

**Issue:** Without active detection rules, security logs accumulate without triggering alerts on real attacks in progress
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Organizations collect logs but only review them after a breach is reported externally. Active intrusion detection applies detection rules to log streams in real time to alert on attack patterns while they're happening, not weeks later.

## Pattern / Solution
```
High-value detection rules (implement in SIEM or alerting):

Brute force:
- >10 failed logins for one account in 5 minutes → alert
- >100 failed logins across accounts from one IP in 5 minutes → block + alert

Credential stuffing:
- >50 login attempts from a single IP across many usernames → rate limit + captcha

Privilege escalation:
- User role changed to admin → immediate alert to security team
- Admin action outside business hours → alert

Data exfiltration indicators:
- User downloads >1000 records in <5 minutes → alert
- API response size >10MB to a new IP → alert
- Bulk export endpoint hit by non-admin → alert

Scanning/enumeration:
- >20 sequential 404s from one IP in 1 minute → alert (IDOR attempt)
- >50 403s from one IP in 5 minutes → alert (authorization bypass attempt)

Geographic anomaly:
- Login from new country not seen in last 90 days → step-up MFA or alert
```
```yaml
# Example Cloudflare WAF rule
expression: (http.request.uri.path matches r"^/api/users/[0-9]+" and http.response.code eq 404)
action: log
# Combine with rate rule triggering on >20 matches from one IP in 60 seconds
```

## Gotchas
- Detection rules need tuning — initial rollout will have false positives; refine for 2–4 weeks before enabling blocking.
- Alert fatigue is real — start with high-confidence, low-volume rules; expand gradually.
- Detections are only as good as the logging — gaps in logs create blind spots.
- Test your detections: run a controlled simulated attack and verify the alert fires.

## Related
- `security-logging-what-to-log.md`
- `honeypot-tokens-canary.md`
- `rate-limiting-2026.md`
