# object-storage-replication

**Issue:** Cross-region and cross-account S3 replication for DR and compliance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Data stored in a single region without a DR copy. Compliance requires data residency in specific regions. No automated replication — manual sync scripts fail silently.

## Pattern / Solution
S3 Cross-Region Replication (CRR):
```hcl
resource "aws_s3_bucket_replication_configuration" "main" {
  bucket = aws_s3_bucket.source.id
  role   = aws_iam_role.replication.arn

  rule {
    id     = "replicate-all"
    status = "Enabled"

    filter {}   # replicate everything

    destination {
      bucket        = aws_s3_bucket.replica.arn
      storage_class = "STANDARD_IA"   # cheaper for DR replica

      replication_time {
        status = "Enabled"   # S3 RTC: 99.99% of objects in 15 min
        time { minutes = 15 }
      }
      metrics {
        status = "Enabled"
        event_threshold { minutes = 15 }
      }
    }

    delete_marker_replication { status = "Enabled" }
  }
}
```

Cross-account replication (source bucket policy):
```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::DEST_ACCOUNT:role/replication-role" },
  "Action": ["s3:ReplicateObject", "s3:ReplicateDelete", "s3:ReplicateTags"],
  "Resource": "arn:aws:s3:::destination-bucket/*"
}
```

Verify replication status:
```bash
aws s3api head-object --bucket source-bucket --key myfile.txt \
  --query 'ReplicationStatus'
# Returns: COMPLETE, PENDING, FAILED, REPLICA
```

## Gotchas
- Replication only applies to objects uploaded AFTER the rule is created — use S3 Batch Operations for existing objects
- Source bucket must have versioning enabled; destination bucket must also have versioning
- S3 RTC (Replication Time Control) costs extra ($0.015/GB) but provides SLA-backed 15-min replication
- Delete markers replicate only if explicitly enabled — objects deleted at source won't delete at destination by default

## Related
- `aws-s3-lifecycle-policies.md`
- `storage-tiering-strategy.md`
- `multi-cloud-strategy.md`
