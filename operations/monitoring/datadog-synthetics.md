# datadog-synthetics

**Issue:** Setting up Datadog Synthetic Monitoring for uptime and browser tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Services appear healthy internally but external users experience failures; internal metrics miss geographic or CDN issues.

## Pattern / Solution
Terraform for API synthetic test:
```hcl
resource "datadog_synthetics_test" "api_check" {
  name    = "API Health Check"
  type    = "api"
  subtype = "http"
  status  = "live"

  request_definition {
    method = "GET"
    url    = "https://api.example.com/health"
  }

  assertion {
    type     = "statusCode"
    operator = "is"
    target   = "200"
  }

  assertion {
    type     = "responseTime"
    operator = "lessThan"
    target   = "500"
  }

  locations = ["aws:us-east-1", "aws:eu-west-1", "aws:ap-southeast-1"]

  options_list {
    tick_every = 60
    retry {
      count    = 1
      interval = 300
    }
  }
}
```

## Gotchas
- Synthetic tests count against APM ingestion quotas if trace injection is enabled
- Browser tests require a Datadog Recorder Chrome extension for recording
- Private locations needed for internal endpoints not exposed to internet

## Related
- `uptime-monitoring-patterns.md`
- `synthetic-monitoring-setup.md`
- `blackbox-monitoring.md`
