# security-logging-what-to-log

**Issue:** Insufficient security logging leaves organizations unable to detect, investigate, or prove security incidents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Most applications log errors and request/response details but miss security-relevant events. When an incident occurs, teams discover they lack the audit trail needed to determine what was accessed, by whom, and when. OWASP lists insufficient logging as a top-10 risk.

## Pattern / Solution
```
MUST LOG (security events):
- Authentication events: login success/failure, MFA attempt, password reset
- Authorization failures: 403/401 responses, IDOR attempts
- Input validation failures: SQL injection patterns, XSS attempts, schema violations
- Session events: session creation, expiry, forced logout
- Privileged operations: user role changes, admin actions, data exports
- Security configuration changes: CORS changes, permission updates
- Outbound connections to external URLs (for SSRF detection)

Each log event MUST include:
- Timestamp (UTC, millisecond precision)
- User/session identifier (anonymized if PII laws require)
- IP address and User-Agent
- Request ID for correlation
- Resource accessed and action attempted
- Outcome (success/failure)
- Risk level (INFO/WARN/ERROR/CRITICAL)
```
```javascript
// Structured security log event
logger.warn('auth.failed', {
  event: 'login_failure',
  username: hashPii(username),  // hash PII, don't log plaintext
  ip: req.ip,
  userAgent: req.headers['user-agent'],
  requestId: req.id,
  timestamp: new Date().toISOString(),
  attemptCount: failCount,
});
```

## Gotchas
- Never log passwords, API keys, tokens, or PII in plaintext — use hashing or masking.
- Log injection: attackers may include newlines in inputs to forge log entries — sanitize before logging.
- Logs must be shipped to a separate, tamper-evident system (SIEM) — local logs can be deleted by an attacker.
- Balance verbosity with signal-to-noise — too much logging causes alert fatigue.

## Related
- `intrusion-detection-patterns.md`
- `audit-log-security.md`
- `log-injection-prevention.md`
