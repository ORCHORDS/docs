# storage-tiering-strategy

**Issue:** Designing a storage tiering strategy to balance performance and cost across hot/warm/cold data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
All data stored in expensive high-performance storage regardless of access frequency. Infrequently accessed data never moves to cheaper tiers.

## Pattern / Solution
Access pattern classification:
```
Hot   (accessed daily):    SSD-backed (gp3, EBS io2, Premium SSD)
Warm  (weekly access):     STANDARD_IA, Coldline, Cool Blob
Cold  (monthly or less):   Glacier IR, Nearline, Archive
Archive (< annually):      Deep Archive, Coldline Archive, Archive tier
```

Data lifecycle decision tree:
```
Last accessed < 30d  → Hot tier
Last accessed 30–90d → Warm tier (check min storage duration penalty)
Last accessed 90–365d → Cold tier
Last accessed > 365d  → Archive or delete
```

Block storage tiering for databases:
```bash
# gp3 vs io2 crossover: ~16,000 IOPS
# Below 16K IOPS: gp3 ($0.08/GB + $0.005/IOPS above 3K)
# Above 16K IOPS: io2 ($0.125/GB + $0.065/IOPS)

# Migrate gp2 → gp3 online (no downtime):
aws ec2 modify-volume --volume-id vol-xxx --volume-type gp3 --iops 3000 --throughput 125
```

Intelligent-Tiering for S3 (automatic):
```hcl
resource "aws_s3_bucket_intelligent_tiering_configuration" "main" {
  bucket = aws_s3_bucket.data.id
  name   = "EntireBucket"

  tiering {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = 180
  }
  tiering {
    access_tier = "ARCHIVE_ACCESS"
    days        = 90
  }
}
```

## Gotchas
- Minimum storage duration charges apply: STANDARD_IA=30d, GLACIER=90d, DEEP_ARCHIVE=180d
- Objects < 128 KB in STANDARD_IA cost more than STANDARD due to overhead charge per object
- Moving data between tiers incurs retrieval + PUT costs — model before automating
- Database block storage (EBS/Persistent Disk) has no lifecycle tiering — archive at application level

## Related
- `aws-s3-lifecycle-policies.md`
- `object-storage-replication.md`
- `cloud-cost-optimization-rightsizing.md`
