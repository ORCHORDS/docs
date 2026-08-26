# infrastructure-cost-tagging

**Issue:** Tagging cloud resources consistently so costs can be attributed to teams, services, and environments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloud bills grow but no one knows which team or service is responsible. Without consistent resource tagging, cost optimization is guesswork and cross-team chargebacks are impossible to compute accurately.

## Pattern / Solution
**Mandatory tag schema**
| Tag key | Values | Description |
|---|---|---|
| `env` | `prod`, `staging`, `dev` | Environment |
| `service` | `api`, `worker`, `web` | Service name |
| `team` | `platform`, `payments`, `growth` | Owning team |
| `cost-center` | `eng-001`, `mkt-002` | Finance cost center |
| `managed-by` | `terraform`, `manual` | Provisioning method |

**Terraform: apply tags to all resources via provider default_tags**
```hcl
# providers.tf
provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      env        = var.environment
      service    = var.service_name
      team       = var.team
      managed-by = "terraform"
    }
  }
}
```

**Enforce tagging via AWS Config rule**
```hcl
resource "aws_config_config_rule" "required_tags" {
  name = "required-tags"
  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }
  input_parameters = jsonencode({
    tag1Key = "env"
    tag2Key = "service"
    tag3Key = "team"
  })
}
```

**Cost allocation in AWS Cost Explorer**
```bash
# Activate tags for cost allocation (one-time setup per tag key)
aws ce update-cost-allocation-tags-status \
  --cost-allocation-tags-status \
    TagKey=service,Status=Active \
    TagKey=team,Status=Active \
    TagKey=env,Status=Active
```

**Monthly cost report by service (AWS CLI)**
```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-09-01 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=service
```

## Gotchas
- AWS tag activation takes up to 24 hours to appear in Cost Explorer
- Resources created before the tagging policy will not have tags — use Tag Editor in the console or `aws resourcegroupstaggingapi tag-resources` for bulk backfill
- EC2 spot instances and Lambda layers do not support all tag keys — check resource type support
- Kubernetes pods do not map directly to AWS costs; use Kubecost or OpenCost for K8s cost allocation

## Related
- `terraform-state-management.md`
- `terraform-drift-detection.md`
- `finops-cost-optimization.md`
