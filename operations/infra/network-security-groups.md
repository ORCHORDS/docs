# network-security-groups

**Issue:** Designing network security group (NSG / security group) rules that enforce least-privilege without breaking connectivity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Security groups allow `0.0.0.0/0` on all ports after a troubleshooting session "to fix connectivity" and the rule is never tightened. Alternatively, overly strict rules block health checks or inter-service traffic, causing silent failures.

## Pattern / Solution
Define security groups around roles (web, app, db, bastion) and use group-to-group references instead of CIDR ranges for internal traffic.

**AWS Security Group (Terraform):**
```hcl
# Bastion — only SSH from corporate IP
resource "aws_security_group" "bastion" {
  name   = "bastion"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.corporate_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Web tier — HTTPS from internet
resource "aws_security_group" "web" {
  name   = "web"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# App tier — only from web SG (group reference, not CIDR)
resource "aws_security_group" "app" {
  name   = "app"
  vpc_id = var.vpc_id

  ingress {
    from_port                = 8080
    to_port                  = 8080
    protocol                 = "tcp"
    source_security_group_id = aws_security_group.web.id
  }
  # Allow bastion SSH
  ingress {
    from_port                = 22
    to_port                  = 22
    protocol                 = "tcp"
    source_security_group_id = aws_security_group.bastion.id
  }
}

# DB tier — only from app SG
resource "aws_security_group" "db" {
  name   = "db"
  vpc_id = var.vpc_id

  ingress {
    from_port                = 5432
    to_port                  = 5432
    protocol                 = "tcp"
    source_security_group_id = aws_security_group.app.id
  }
}
```

**Egress rules — restrict outbound on sensitive tiers:**
```hcl
# DB instances should not initiate outbound connections to the internet
resource "aws_security_group_rule" "db_egress_deny_internet" {
  type              = "egress"
  from_port         = 0
    to_port           = 0
  protocol          = "-1"
  cidr_blocks       = [var.vpc_cidr]   # only within VPC
  security_group_id = aws_security_group.db.id
}
```

## Gotchas
- Security groups are stateful — you only need an ingress rule; response traffic is automatically allowed.
- Group-to-group references only work within the same VPC (or peered VPCs with specific conditions); use CIDR for cross-account traffic.
- AWS limits 60 rules per security group and 16 security groups per ENI by default; request a limit increase early for complex environments.
- Changing a security group rule takes effect immediately but existing connections are not terminated — a connection already open before a deny rule is added will continue until it closes naturally.

## Related
- `vpc-subnet-design.md`
- `bastion-host-pattern.md`
- `nginx-rate-limiting.md`
