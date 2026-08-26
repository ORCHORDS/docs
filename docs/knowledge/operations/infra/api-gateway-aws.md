# api-gateway-aws

**Issue:** AWS API Gateway (HTTP API vs REST API) patterns for serverless backends
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Choosing between HTTP API and REST API, handling CORS, configuring throttling, and integrating with Lambda.

## Pattern / Solution
HTTP API (recommended for most use cases — 70% cheaper than REST):
```hcl
resource "aws_apigatewayv2_api" "main" {
  name          = "prod-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["https://app.example.com"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "prod"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 500
    throttling_rate_limit  = 1000
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationLatency = "$context.integrationLatency"
    })
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}
```

JWT authorizer (no Lambda needed):
```hcl
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  name             = "cognito-authorizer"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.main.id]
    issuer   = "https://cognito-idp.us-east-1.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}
```

## Gotchas
- HTTP API does not support: usage plans, API keys, request/response transformations (use REST API for these)
- Lambda payload format v2.0 restructures the event object — check your handler handles both formats if migrating
- API Gateway timeout maximum is 29 s — long-running operations need async pattern (return 202, poll for status)
- Regional APIs need CloudFront in front for edge caching and WAF integration

## Related
- `aws-lambda-patterns.md`
- `aws-waf-rules.md`
- `nginx-rate-limiting.md`
