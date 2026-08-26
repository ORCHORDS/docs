# aws-waf-rules

**Issue:** AWS WAF v2 rule setup for rate limiting, bot mitigation, and OWASP protection
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications getting scraped, credential-stuffed, or hit with SQL injection. AWS WAF exists but only the default managed rules are enabled with no rate limiting.

## Pattern / Solution
```hcl
resource "aws_wafv2_web_acl" "main" {
  name  = "prod-waf"
  scope = "CLOUDFRONT"   # or REGIONAL for ALB/API GW

  default_action { allow {} }

  # AWS managed OWASP core rule set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  # Rate limit by IP — 1000 req / 5 min
  rule {
    name     = "RateLimitByIP"
    priority = 2
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 1000
        aggregate_key_type = "IP"
        scope_down_statement {
          byte_match_statement {
            field_to_match { uri_path {} }
            positional_constraint = "STARTS_WITH"
            search_string         = "/api/"
            text_transformation { priority = 0; type = "NONE" }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitByIP"
      sampled_requests_enabled   = true
    }
  }

  # Bot Control managed rule
  rule {
    name     = "AWSManagedRulesBotControlRuleSet"
    priority = 3
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesBotControlRuleSet"
        vendor_name = "AWS"
        managed_rule_group_configs {
          aws_managed_rules_bot_control_rule_set {
            inspection_level = "COMMON"
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "BotControl"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "ProdWAF"
    sampled_requests_enabled   = true
  }
}
```

## Gotchas
- Run WAF in `COUNT` mode first to baseline false positives before switching to `BLOCK`
- Bot Control TARGETED level is 10× more expensive than COMMON — start with COMMON
- WAF sampled requests only keep 100 samples/rule/period — enable full logging to S3 for investigations
- IP set updates are eventually consistent (~10 s propagation to edges)

## Related
- `aws-cloudfront-patterns.md`
- `nginx-rate-limiting.md`
- `network-security-groups.md`
