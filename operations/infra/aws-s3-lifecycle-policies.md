# aws-s3-lifecycle-policies

**Issue:** Automating S3 storage tier transitions and expiration to control costs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
S3 bills grow unbounded because objects stay in STANDARD storage forever. Old logs, backups, and raw data accumulate without expiry rules.

## Pattern / Solution
```hcl
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "logs-tiering"
    status = "Enabled"
    filter { prefix = "logs/" }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"   # Instant Retrieval — milliseconds
    }
    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }
    expiration {
      days = 2555   # 7 years then delete
    }
  }

  rule {
    id     = "abort-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }

  rule {
    id     = "delete-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}
```

Storage class cost comparison (approximate, us-east-1):
```
STANDARD       $0.023/GB
STANDARD_IA    $0.0125/GB + $0.01/GB retrieval
GLACIER_IR     $0.004/GB  + $0.03/GB retrieval
GLACIER_FR     $0.0036/GB + minutes retrieval
DEEP_ARCHIVE   $0.00099/GB + hours retrieval
```

## Gotchas
- STANDARD_IA has a 128 KB minimum object size charge — don't tier small objects
- Minimum storage duration: STANDARD_IA=30d, GLACIER_IR=90d, DEEP_ARCHIVE=180d — early deletion fees apply
- Intelligent-Tiering avoids manual rules but adds $0.0025/1000 objects monitoring fee
- Lifecycle rules don't apply to objects tagged with `s3:DeleteMarker` — enable expiration for delete markers separately

## Related
- `object-storage-replication.md`
- `storage-tiering-strategy.md`
- `aws-cost-explorer-tagging.md`
