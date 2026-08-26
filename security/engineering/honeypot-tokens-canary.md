# honeypot-tokens-canary

**Issue:** Real credential theft is often undetected because legitimate and malicious access look identical without canary signals
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
If an attacker steals a real API key and uses it, the access looks like a normal request. Honeypot tokens (canary tokens) are fake credentials that should never be used by legitimate systems. Any use of a canary token is an unambiguous signal of compromise.

## Pattern / Solution
```bash
# Generate a canary token via canarytokens.org (free)
# Types: AWS keys, DNS-based, HTTP-based, Word documents, PDF files

# AWS canary credentials — fake IAM key that alerts on any API call
# 1. Create dedicated IAM user with no permissions
# 2. Generate access key for that user
# 3. Create CloudWatch/CloudTrail alarm on any API call from that key
# 4. Place the key in monitored locations: config files, S3 buckets, code repos

# Example: canary key in .env that should never load
CANARY_AWS_KEY=AKIAXXX...XXXXCANARY
# Any call to AWS with this key = credential dump in progress
```
```python
# Application-level canary: embed fake admin token in accessible location
# If token is ever sent to your API, alert immediately
CANARY_TOKEN = "canary-" + secrets.token_urlsafe(32)

@app.middleware("http")
async def canary_detector(request, call_next):
    auth = request.headers.get("Authorization", "")
    if CANARY_TOKEN in auth:
        alert_security_team("CANARY TOKEN USED — possible credential theft")
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)
```
```
Canary placement strategy:
- Database config files (detect file read)
- S3 bucket with public list disabled (detect bucket enumeration)
- Source code comments (detect repo scraping)
- Password manager entries (detect vault compromise)
- Kubernetes secret (detect cluster access)
```

## Gotchas
- Canary tokens only work if legitimate systems never use them — document them carefully to prevent accidental use.
- Rotate canary tokens periodically — a stolen token that isn't used immediately is still dangerous.
- The alert on canary use must be immediate (PagerDuty, not email) — the window to respond is narrow.
- Don't put canary tokens where they'll be included in test suites or CI — false positives erode trust in the signal.

## Related
- `intrusion-detection-patterns.md`
- `security-logging-what-to-log.md`
- `secrets-detection-pre-commit.md`
