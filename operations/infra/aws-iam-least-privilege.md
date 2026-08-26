# aws-iam-least-privilege

**Issue:** Applying least-privilege IAM policies to reduce blast radius of compromised credentials
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Services using wildcard `*` actions or resources, AdministratorAccess attached to workloads, no permission boundaries — any single compromise gives full account access.

## Pattern / Solution
```json
// Service-specific policy: Lambda reads only from one S3 bucket prefix
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadInputBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/inputs/*"
      ]
    },
    {
      "Sid": "WriteOutputBucket",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::my-bucket/outputs/*"
    }
  ]
}
```

Permission boundary — cap what a role can ever do even if policy allows more:
```json
{
  "Effect": "Allow",
  "Action": "*",
  "Resource": "*",
  "Condition": {
    "StringEquals": { "aws:RequestedRegion": ["us-east-1", "eu-west-1"] }
  }
}
```

Finding unused permissions with Access Analyzer:
```bash
aws accessanalyzer list-findings \
  --analyzer-arn arn:aws:access-analyzer:us-east-1:123456789012:analyzer/prod \
  --filter '{"findingType":{"eq":["UnusedPermission"]}}'
```

IAM Access Advisor — see last-used service dates:
```bash
aws iam generate-service-last-accessed-details --arn arn:aws:iam::123456789:role/MyRole
```

## Gotchas
- `iam:PassRole` is powerful — restrict with `Condition: iam:PassedToService`
- SCPs in AWS Organizations are AND-ed with identity policies; allow in both or it's denied
- Trust policies control who can assume the role; resource policies are separate
- Avoid inline policies in CDK/Terraform — harder to audit; use managed policies

## Related
- `aws-guardduty-setup.md`
- `aws-cloudtrail-audit.md`
- `secrets-management-comparison.md`
