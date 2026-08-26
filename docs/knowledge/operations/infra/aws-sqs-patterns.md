# aws-sqs-patterns

**Issue:** Common SQS queue patterns for reliable async processing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Messages processed multiple times, lost, or stuck in flight. Fan-out to multiple consumers not working. DLQ not catching failures.

## Pattern / Solution
```hcl
# Standard queue with DLQ
resource "aws_sqs_queue" "main" {
  name                       = "orders-processing"
  visibility_timeout_seconds = 300   # must exceed Lambda/worker timeout
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20    # long polling — reduces empty receives

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "dlq" {
  name                      = "orders-processing-dlq"
  message_retention_seconds = 1209600  # 14 days
}

# FIFO queue for exactly-once / ordered
resource "aws_sqs_queue" "fifo" {
  name                        = "payments.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  deduplication_scope         = "messageGroup"
  fifo_throughput_limit       = "perMessageGroupId"
}
```

Consumer pattern (batch delete on success):
```python
while True:
    msgs = sqs.receive_message(QueueUrl=URL, MaxNumberOfMessages=10, WaitTimeSeconds=20)
    for msg in msgs.get('Messages', []):
        process(msg)
        sqs.delete_message(QueueUrl=URL, ReceiptHandle=msg['ReceiptHandle'])
```

## Gotchas
- Visibility timeout must be longer than your processing time or messages reappear
- FIFO queues max 3000 msg/s with batching per queue (not per message group)
- Long polling (`WaitTimeSeconds=20`) is free and reduces cost vs short polling
- DLQ must be same type (standard/FIFO) as source queue

## Related
- `aws-sns-fanout.md`
- `message-queue-patterns.md`
- `rabbitmq-dead-letter-queues.md`
