# network-bandwidth-optimization

**Issue:** Reducing cloud network egress costs and improving throughput between services
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unexpected $10K+ monthly network egress bills. Services in different AZs generating cross-AZ transfer charges. Large object transfers without compression.

## Pattern / Solution
Cross-AZ transfer costs:
```
AWS: $0.01/GB cross-AZ (both directions)
→ Two services in different AZs calling each other 100 GB/day = $60/month

Fix: Pin services to same AZ with affinity rules
```

```yaml
# K8s: prefer same AZ as consumer
affinity:
  podAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchLabels:
            app: consumer
        topologyKey: topology.kubernetes.io/zone
```

Compression for internal service calls:
```python
# gRPC: enable compression
channel = grpc.insecure_channel(
    'service:50051',
    options=[('grpc.default_compression_algorithm', grpc.Compression.Gzip)]
)

# HTTP: negotiate compression
headers = {'Accept-Encoding': 'gzip, br'}
```

S3 Transfer Acceleration for uploads from distant regions:
```bash
# Enable on bucket
aws s3api put-bucket-accelerate-configuration \
  --bucket my-bucket \
  --accelerate-configuration Status=Enabled

# Use accelerate endpoint
aws s3 cp file.tar.gz s3://my-bucket/ \
  --endpoint-url https://my-bucket.s3-accelerate.amazonaws.com
```

Data transfer cost hierarchy (cheapest to most expensive):
```
1. Same AZ             → free
2. Same region, diff AZ → $0.01/GB (AWS)
3. To CloudFront       → free from S3; cheap from EC2
4. Inter-region        → $0.02–0.09/GB
5. Internet egress     → $0.09/GB (first 10 TB)
```

## Gotchas
- S3 same-region transfer to EC2 is free only via VPC endpoint (Gateway type, not Interface)
- NAT Gateway incurs $0.045/GB processing charge — route internal traffic directly to S3/DynamoDB via Gateway endpoints
- ALB → Target cross-AZ data is free for ALB-initiated; charged for inter-AZ backend-to-backend

## Related
- `vpc-subnet-design.md`
- `cdn-origin-shield-patterns.md`
- `cloud-cost-optimization-rightsizing.md`
