# aws-lambda-patterns

**Issue:** Production Lambda patterns for cold start reduction, concurrency, and cost
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Lambda functions have high p99 latency due to cold starts, hit concurrency limits, or cost more than expected due to over-provisioned memory.

## Pattern / Solution
```python
# Handler with connection reuse outside handler scope
import boto3, os

# Initialized once per container — survives warm invocations
db = boto3.client('rds-data', region_name=os.environ['AWS_REGION'])

def handler(event, context):
    # business logic here
    pass
```

```hcl
resource "aws_lambda_function" "api" {
  function_name = "api-handler"
  runtime       = "python3.12"
  handler       = "main.handler"
  memory_size   = 1024   # tune with Lambda Power Tuning tool
  timeout       = 30
  architectures = ["arm64"]  # 20% cheaper than x86

  # Provisioned concurrency eliminates cold starts for latency-sensitive paths
  # (set on alias, not function directly)
}

resource "aws_lambda_provisioned_concurrency_config" "api" {
  function_name                  = aws_lambda_function.api.function_name
  qualifier                      = aws_lambda_alias.live.name
  provisioned_concurrent_executions = 10
}

# Reserved concurrency — cap blast radius
resource "aws_lambda_function_event_invoke_config" "api" {
  function_name          = aws_lambda_function.api.function_name
  maximum_retry_attempts = 0  # for synchronous; avoid duplicate side effects
}
```

Lambda URLs for direct HTTP (no API Gateway overhead):
```hcl
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM"
  cors { allow_origins = ["https://example.com"] }
}
```

## Gotchas
- Cold starts on VPC Lambdas are longer — use VPC only when needed; prefer RDS Proxy or Secrets Manager endpoints
- `reserved_concurrent_executions = 0` disables the function entirely (throttles all requests)
- arm64 requires compatible layers and binaries — test before switching
- Lambda Power Tuning (open-source Step Functions state machine) finds optimal memory for cost×speed tradeoff

## Related
- `aws-sqs-patterns.md`
- `api-gateway-aws.md`
- `aws-iam-least-privilege.md`
