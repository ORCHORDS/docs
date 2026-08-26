# attack-surface-reduction

**Issue:** Unnecessary exposed services, endpoints, and permissions increase the blast radius of any compromise
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every API endpoint, open port, enabled feature flag, and broad IAM permission is a potential entry point. Attackers enumerate exposed surfaces before attacking — reducing the surface reduces exploitable options.

## Pattern / Solution
```bash
# Audit open ports
nmap -sS -O --open target.internal

# List all API routes in an Express app
app._router.stack.filter(r => r.route).map(r => ({
  path: r.route.path,
  methods: Object.keys(r.route.methods)
}))
```
```yaml
# Kubernetes — disable unnecessary capabilities in pods
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```
```terraform
# AWS — restrict S3 bucket to specific VPC endpoint only
resource "aws_s3_bucket_policy" "private" {
  bucket = aws_s3_bucket.data.id
  policy = jsonencode({
    Statement = [{
      Effect = "Deny"
      Principal = "*"
      Action = "s3:*"
      Resource = ["${aws_s3_bucket.data.arn}/*"]
      Condition = {
        StringNotEquals = {
          "aws:sourceVpce" = var.vpc_endpoint_id
        }
      }
    }]
  })
}
```

## Gotchas
- Debug endpoints (`/debug`, `/admin`, `/actuator`) must be disabled or protected in production.
- Unused environment variables containing secrets should be removed, not just ignored.
- Feature flags for unreleased features that are on by default expand the attack surface.
- Third-party integrations (webhooks, OAuth apps) each add attack surface — review and prune quarterly.

## Related
- `threat-modeling-stride.md`
- `zero-trust-network-access.md`
