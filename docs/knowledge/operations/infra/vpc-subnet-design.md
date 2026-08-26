# vpc-subnet-design

**Issue:** Designing VPC subnet layout for isolation, scalability, and future growth
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Subnets are too small to accommodate auto-scaling groups. Public and private resources share the same subnet, violating isolation. No room for new availability zones. CIDR ranges conflict with on-prem or peered networks.

## Pattern / Solution
Use a hierarchical CIDR design with dedicated subnets per tier per AZ.

**Three-tier layout across 3 AZs (10.0.0.0/16):**

| Tier | AZ-a | AZ-b | AZ-c | Size |
|------|------|------|------|------|
| Public (ALB, NAT GW) | 10.0.0.0/24 | 10.0.1.0/24 | 10.0.2.0/24 | 256 IPs |
| Private App | 10.0.16.0/20 | 10.0.32.0/20 | 10.0.48.0/20 | 4096 IPs |
| Private DB | 10.0.64.0/22 | 10.0.68.0/22 | 10.0.72.0/22 | 1024 IPs |
| Reserved | 10.0.128.0/17 | — | — | future |

**Terraform pattern:**
```hcl
locals {
  azs = ["us-east-1a", "us-east-1b", "us-east-1c"]

  public_cidrs  = ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"]
  private_cidrs = ["10.0.16.0/20", "10.0.32.0/20", "10.0.48.0/20"]
  db_cidrs      = ["10.0.64.0/22", "10.0.68.0/22", "10.0.72.0/22"]
}

resource "aws_subnet" "public" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.public_cidrs[count.index]
  availability_zone = local.azs[count.index]
  map_public_ip_on_launch = true
}

resource "aws_subnet" "private" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = local.azs[count.index]
}

resource "aws_subnet" "db" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.db_cidrs[count.index]
  availability_zone = local.azs[count.index]
}

# NAT Gateway per AZ for HA (or single for cost savings)
resource "aws_nat_gateway" "main" {
  count         = length(local.azs)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
}
```

**Route tables:**
- Public subnets → Internet Gateway
- Private app subnets → NAT Gateway in same AZ
- DB subnets → no default route to internet (egress blocked)

## Gotchas
- AWS reserves 5 IPs per subnet (first 4 and last 1) — a `/28` gives only 11 usable IPs, which is not enough for auto-scaling.
- CIDR cannot be changed after subnet creation; over-provision private ranges — you cannot grow them later without adding new subnets.
- VPC peering and Transit Gateway require non-overlapping CIDRs across all connected networks; document and allocate a unique range per environment from the start.
- Placing NAT Gateways in only one AZ for cost savings means private subnets in other AZs lose internet if that AZ fails.

## Related
- `network-security-groups.md`
- `bastion-host-pattern.md`
- `iac-best-practices.md`
