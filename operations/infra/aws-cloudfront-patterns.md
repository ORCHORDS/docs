# aws-cloudfront-patterns

**Issue:** CloudFront distribution patterns for SPAs, APIs, and asset CDN
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cache misses on every request, stale HTML served after deploy, API responses cached when they should not be, or CORS errors at the CDN edge.

## Pattern / Solution
```hcl
resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  default_root_object = "index.html"
  aliases             = ["app.example.com"]

  # S3 origin for static assets
  origin {
    domain_name            = aws_s3_bucket.static.bucket_regional_domain_name
    origin_id              = "s3-static"
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
  }

  # API origin
  origin {
    domain_name = "api.example.com"
    origin_id   = "api"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
    }
  }

  # Assets: long-lived cache
  ordered_cache_behavior {
    path_pattern     = "/assets/*"
    target_origin_id = "s3-static"
    cache_policy_id  = "658327ea-f89d-4fab-a63d-7e88639e58f6"  # CachingOptimized
    viewer_protocol_policy = "redirect-to-https"
  }

  # API: no cache
  ordered_cache_behavior {
    path_pattern     = "/api/*"
    target_origin_id = "api"
    cache_policy_id  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"  # CachingDisabled
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"  # AllViewerExceptHostHeader
    viewer_protocol_policy = "https-only"
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
  }

  # SPA fallback — serve index.html for 403/404
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
}
```

Cache invalidation after deploy:
```bash
aws cloudfront create-invalidation \
  --distribution-id E1234ABCDEF \
  --paths "/index.html" "/asset-manifest.json"
```

## Gotchas
- Invalidations cost $0.005/path after 1000/month — use versioned filenames for assets instead
- `Cache-Control: no-cache` from origin is respected but `no-store` is not cached (good for APIs)
- Lambda@Edge runs in us-east-1 only; CloudFront Functions run at all edges and are cheaper for simple request manipulation
- Origin Shield adds a cache layer between edge and origin — reduces origin load but adds latency for cache misses

## Related
- `cdn-origin-shield-patterns.md`
- `aws-waf-rules.md`
- `aws-s3-lifecycle-policies.md`
