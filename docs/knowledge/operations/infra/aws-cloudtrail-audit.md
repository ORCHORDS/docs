# aws-cloudtrail-audit

**Issue:** CloudTrail configuration for complete audit logging and forensic readiness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After a security incident, no logs exist of what API calls were made, who made them, or from where. Single-region trails miss activity in other regions.

## Pattern / Solution
```hcl
resource "aws_cloudtrail" "org" {
  name                          = "org-trail"
  s3_bucket_name                = aws_s3_bucket.audit.id
  is_multi_region_trail         = true
  is_organization_trail         = true   # covers all member accounts
  enable_log_file_validation    = true   # SHA-256 digest for tamper detection
  include_global_service_events = true   # IAM, STS, Route53

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = ["arn:aws:s3"]   # all S3 data events
    }
  }

  insight_selector {
    insight_type = "ApiCallRateInsight"
  }

  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.cloudtrail_cw.arn
}
```

Query CloudTrail with Athena:
```sql
-- Find all console logins in last 24h
SELECT eventtime, useridentity.username, sourceipaddress, awsregion
FROM cloudtrail_logs
WHERE eventsource = 'signin.amazonaws.com'
  AND eventname = 'ConsoleLogin'
  AND eventtime > date_add('day', -1, current_timestamp)
ORDER BY eventtime DESC;

-- Who deleted resources?
SELECT eventtime, useridentity.arn, eventname, requestparameters
FROM cloudtrail_logs
WHERE eventname LIKE '%Delete%'
  AND errorcode IS NULL
  AND eventtime > date_add('day', -7, current_timestamp);
```

## Gotchas
- Management events are free; data events (S3, Lambda) cost $0.10/100K events
- CloudTrail has 15-minute delivery lag to S3 — use CloudWatch Logs for near-real-time alerting
- S3 bucket for audit logs must have MFA delete and strict bucket policy denying `s3:DeleteObject`
- Log file validation digests are per-hour — missing digest means potential tampering

## Related
- `aws-guardduty-setup.md`
- `aws-iam-least-privilege.md`
- `post-mortem-blameless-template.md`
