# aws-guardduty-setup

**Issue:** Enabling and tuning GuardDuty for threat detection across AWS accounts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
No visibility into compromised IAM credentials, crypto-mining EC2 instances, or S3 data exfiltration attempts. GuardDuty exists but is only enabled in one region or not at all.

## Pattern / Solution
Enable via AWS Organizations delegated administrator (preferred):
```bash
# Designate security account as GuardDuty admin
aws organizations enable-aws-service-access --service-principal guardduty.amazonaws.com
aws guardduty enable-organization-admin-account --admin-account-id 111122223333

# In security account: auto-enable for all member accounts
aws guardduty update-organization-configuration \
  --detector-id <detector-id> \
  --auto-enable-organization-members ALL \
  --features '[{"Name":"S3_DATA_EVENTS","AutoEnable":"ALL"},
               {"Name":"EKS_AUDIT_LOGS","AutoEnable":"ALL"},
               {"Name":"RDS_LOGIN_EVENTS","AutoEnable":"ALL"},
               {"Name":"RUNTIME_MONITORING","AutoEnable":"ALL"}]'
```

EventBridge rule to route HIGH/CRITICAL findings to PagerDuty:
```json
{
  "source": ["aws.guardduty"],
  "detail-type": ["GuardDuty Finding"],
  "detail": {
    "severity": [{ "numeric": [">=", 7] }]
  }
}
```

Suppress known-good findings:
```bash
aws guardduty create-filter \
  --detector-id <id> \
  --name "suppress-nat-instance" \
  --action ARCHIVE \
  --finding-criteria '{
    "Criterion": {
      "resource.instanceDetails.instanceId": {"Eq": ["i-natgateway-id"]},
      "type": {"Eq": ["Recon:EC2/PortProbeUnprotectedPort"]}
    }
  }'
```

## Gotchas
- GuardDuty must be enabled in every region — threats in disabled regions are invisible
- S3 Protection and EKS protection are separate features; check they're enabled
- Malware Protection for EC2 requires an IAM service role — missing it silently skips scans
- Finding severity 7–8.9 = HIGH, 9–10 = CRITICAL; tune EventBridge threshold accordingly
- Cost scales with volume of logs analysed — S3 Data Events can be expensive in high-write buckets

## Related
- `aws-cloudtrail-audit.md`
- `aws-iam-least-privilege.md`
- `alerting-fatigue-reduction.md`
