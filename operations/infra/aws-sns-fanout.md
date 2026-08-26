# aws-sns-fanout

**Issue:** SNS fan-out to multiple SQS queues for decoupled multi-consumer architectures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A single event (order placed, user registered) needs to trigger multiple independent downstream services without coupling them together.

## Pattern / Solution
```hcl
resource "aws_sns_topic" "order_events" {
  name = "order-events"
}

# Each service gets its own SQS queue subscribed to the topic
resource "aws_sns_topic_subscription" "inventory" {
  topic_arn = aws_sns_topic.order_events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.inventory.arn

  filter_policy = jsonencode({
    eventType = ["ORDER_PLACED", "ORDER_CANCELLED"]
  })
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.order_events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.email.arn

  filter_policy = jsonencode({
    eventType = ["ORDER_PLACED"]
  })
}
```

SQS queue policy to allow SNS delivery:
```json
{
  "Effect": "Allow",
  "Principal": { "Service": "sns.amazonaws.com" },
  "Action": "sqs:SendMessage",
  "Resource": "<queue-arn>",
  "Condition": { "ArnEquals": { "aws:SourceArn": "<topic-arn>" } }
}
```

Publish with message attributes for filter routing:
```python
sns.publish(
    TopicArn=TOPIC_ARN,
    Message=json.dumps(event),
    MessageAttributes={
        'eventType': {'DataType': 'String', 'StringValue': 'ORDER_PLACED'}
    }
)
```

## Gotchas
- Filter policies match on message attributes, not message body — add attributes at publish time
- SNS delivers to SQS raw by default; enable `RawMessageDelivery` on the subscription to avoid JSON-wrapping
- Cross-account SNS→SQS requires queue resource policy AND SNS access policy on both sides
- SNS does not retry on HTTP/HTTPS endpoint failures the same way as SQS — use SQS as intermediary for durability

## Related
- `aws-sqs-patterns.md`
- `message-queue-patterns.md`
- `event-streaming-kafka-vs-kinesis.md`
