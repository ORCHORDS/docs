# AWS VPC Network Architecture Governance

## Purpose

Amazon Virtual Private Cloud (VPC) provides an isolated network within the AWS cloud. Governance ensures that every workload runs in a VPC with documented subnet tiers, route tables, security groups, network ACLs, and connectivity patterns. Without explicit governance, networks accrete ad-hoc peering, inconsistent security groups, and unmanaged internet egress.

## Current context and source status

AWS VPC is generally available. The current feature set includes VPC Lattice, AWS Network Firewall, AWS PrivateLink, Gateway Load Balancer, and VPC Reachability Analyzer. Newer constructs such as VPC Lattice have specific use cases; verify the current AWS guidance before adopting them for production workloads.

## Governance workflow and controls

### 1. Define a tier model

Adopt a three-tier model:

- public tier (entry points such as load balancers and NAT gateways);
- private tier (application services);
- data tier (databases, caches, queues).

Each tier occupies its own subnet with explicit route tables. The data tier MUST NOT have a route to the internet gateway.

### 2. Size subnets deliberately

Size subnets to accommodate current and forecast workload, not just initial deployment. Track IP utilization and create an alert when utilization exceeds 70 percent.

### 3. Govern security groups

Security groups MUST follow least privilege. Default-deny with explicit allow rules. Track security group changes in code (CloudFormation, Terraform). Reconcile security groups against the control register; remove unused security groups.

### 4. Manage network ACLs

Network ACLs provide a stateless layer of defense. Treat them as a secondary control and avoid using them as the primary access control. Keep NACL rules minimal and documented.

### 5. Govern egress

Centralize egress through a NAT gateway or AWS Network Firewall. Block direct internet egress from workloads. Maintain an allowlist of approved destinations for sensitive workloads.

### 6. Connectivity patterns

Use AWS PrivateLink for service-to-service connectivity where supported. Use Transit Gateway for hub-and-spoke multi-VPC architectures. Use VPC peering only for narrowly scoped, stable relationships.

### 7. Flow logs

Enable VPC flow logs to a centralized log destination. Retain logs per the documented retention policy. Use flow logs to detect unexpected traffic patterns.

## Validation and evidence

- VPC topology diagram with tier assignments.
- Subnet sizing and utilization report.
- Security group inventory with owners.
- Network ACL rules review.
- Flow log retention and storage artifact.
- Reachability Analyzer reports for critical paths.

## Failure correction

Common defects include security groups that allow 0.0.0.0/0 ingress on administrative ports, oversized subnets that mask utilization, and missing flow logs. Corrective actions include a periodic security group review with mandatory justification for 0.0.0.0/0 rules, a subnet sizing recalculation, and a deployment-time check that enforces flow log configuration.

## Limitations

- AWS VPC is specific to AWS.
- NACLs do not filter by security group.
- VPC peering does not transitively route.
- AWS PrivateLink has scaling and pricing characteristics that differ from NAT.

## Canonical sources

- AWS VPC User Guide, current edition.
- AWS Network Firewall Developer Guide, current edition.
- AWS PrivateLink documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for network controls, the engineering leaf for connectivity patterns, and the operations leaf for flow log retention.
