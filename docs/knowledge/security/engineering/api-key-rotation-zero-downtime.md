# api-key-rotation-zero-downtime

**Issue:** Rotating compromised or expiring API keys causes downtime if not done in the correct sequence
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a secret is compromised or reaches its rotation deadline, teams often delete the old key before deploying the new one, causing a gap where services fail authentication. Zero-downtime rotation requires an overlap period where both old and new keys are valid.

## Pattern / Solution
```
Zero-downtime rotation sequence:
1. Generate new key/secret at the provider (while old key still works)
2. Deploy new key to all consumers (update secrets manager, redeploy services)
3. Verify all consumers are using the new key (check metrics/logs for old-key auth)
4. Revoke the old key only after all consumers are confirmed migrated

For API keys with usage tracking:
1. Check provider dashboard: any requests still using old key?
2. Set old key to read-only or restricted permissions before deletion
```
```bash
# AWS Secrets Manager — automatic rotation with Lambda
aws secretsmanager rotate-secret \
  --secret-id prod/database/password \
  --rotation-lambda-arn arn:aws:lambda:us-east-1:123:function:SecretsManagerRotator \
  --rotation-rules AutomaticallyAfterDays=30

# Fetch latest version in app — always fetch at startup, not hardcode
import boto3
client = boto3.client('secretsmanager')
secret = <redacted-secret>'prod/database/password')
```

## Gotchas
- Services that cache credentials at startup need restarting or a dynamic credential refresh mechanism.
- Some APIs (Stripe, Twilio) allow two simultaneous active keys to enable zero-downtime rotation — use this feature.
- Rotation without testing the new key first leads to deploying a broken key and then losing access to the old one.
- Rotate secrets on a schedule, not just on compromise — reduces the window of exposure for any given credential.

## Related
- `secrets-detection-pre-commit.md`
- `secrets-encryption-at-rest.md`
- `secrets-rotation-runbook-2026.md`
