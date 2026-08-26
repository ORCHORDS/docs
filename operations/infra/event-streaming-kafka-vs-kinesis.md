# event-streaming-kafka-vs-kinesis

**Issue:** Choosing between Kafka, Kinesis, and Pub/Sub for event streaming workloads
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SQS insufficient for event replay/reprocessing. Need to fan out to many consumers with independent offsets. Unclear whether to self-manage Kafka or use managed Kinesis.

## Pattern / Solution
Comparison:
```
┌─────────────────┬───────────────────┬──────────────────┬──────────────────┐
│ Feature         │ Apache Kafka      │ AWS Kinesis      │ GCP Pub/Sub      │
├─────────────────┼───────────────────┼──────────────────┼──────────────────┤
│ Retention       │ Configurable (∞)  │ 7 days (max)     │ 7 days (max)     │
│ Throughput      │ Very high         │ 1 MB/s/shard     │ Scales auto      │
│ Ordering        │ Per partition     │ Per shard        │ Per ordering key │
│ Replay          │ Yes (by offset)   │ Yes (by seqnum)  │ Limited          │
│ Consumer groups │ Yes               │ Enhanced fan-out │ Subscriptions    │
│ Ops burden      │ High (self-host)  │ None             │ None             │
│ Cost            │ EC2 + EBS         │ $0.015/shard/hr  │ Per message      │
└─────────────────┴───────────────────┴──────────────────┴──────────────────┘
```

MSK (Managed Kafka) for large scale:
```hcl
resource "aws_msk_cluster" "main" {
  cluster_name           = "prod-kafka"
  kafka_version          = "3.7.x"
  number_of_broker_nodes = 6   # 2 per AZ × 3 AZs

  broker_node_group_info {
    instance_type   = "kafka.m5.2xlarge"
    storage_info {
      ebs_storage_info { volume_size = 1000 }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = 1
  }

  encryption_info {
    encryption_in_transit { client_broker = "TLS" }
  }
}
```

Kinesis for simpler managed streaming:
```python
import boto3
kinesis = boto3.client('kinesis')

# Put record
kinesis.put_record(
    StreamName='events',
    Data=json.dumps(event).encode(),
    PartitionKey=event['userId']   # routes to same shard = ordered per user
)

# Consumer with checkpointing (KCL handles this automatically)
```

## Gotchas
- Kafka partition count cannot be decreased — plan partition count for peak throughput upfront
- Kinesis Enhanced Fan-Out costs $0.015/shard/hour extra — use shared throughput for low-scale consumers
- MSK Serverless is cheaper for variable workloads but lacks some features (e.g. topic-level retention)
- Kafka offsets are consumer-side state — losing ZooKeeper/KRaft data doesn't lose messages

## Related
- `kafka-consumer-group-lag.md`
- `aws-sqs-patterns.md`
- `gcp-pub-sub-patterns.md`
