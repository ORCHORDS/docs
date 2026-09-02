# GCP VPC Service Controls Governance

## Purpose

VPC Service Controls create a security perimeter around Google Cloud resources, mitigating the risk of data exfiltration. Governance ensures that perimeters cover sensitive services, that access levels are explicit, that ingress and egress policies reflect the workload's trust model, and that perimeter breaches are detected and triaged.

## Current context and source status

VPC Service Controls is generally available. The current feature set includes standard and dry-run perimeters, access levels based on Identity and Access Management (IAM) conditions, ingress and egress rules, and perimeter bridges. Specific service support and identity types evolve; verify the supported services list before standardizing a perimeter.

## Governance workflow and controls

### 1. Identify protected resources

Determine which projects and services hold sensitive data. Apply perimeters to projects that store regulated data, secrets, or production workloads. Avoid applying perimeters to projects that require unrestricted access (for example, public-facing static content) unless paired with explicit ingress and egress rules.

### 2. Choose perimeter mode

Use standard mode for production perimeters. Use dry-run mode to evaluate changes without enforcement. Always validate changes in dry-run before applying them in standard mode.

### 3. Define access levels

Access levels express conditions that determine when a request can cross a perimeter. Define access levels based on:

- user identity;
- device posture (managed device, screen lock);
- IP range (corporate network);
- geographic region;
- time of day.

Combine conditions. Reuse access levels across perimeters where possible.

### 4. Configure ingress rules

Ingress rules define what can cross into the perimeter from outside. Document every ingress rule with the source identity, source scope, target resource, and method. Reject broad rules such as `*` identities.

### 5. Configure egress rules

Egress rules define what can cross out of the perimeter. Use egress rules to allow specific destinations required by the workload. Reject broad egress rules.

### 6. Bridge perimeters where needed

Use perimeter bridges to share resources across two perimeters. Document bridge purpose and review quarterly. Avoid bridging perimeters of different sensitivity tiers.

### 7. Audit and alert

Enable Cloud Audit Logs and send perimeter events to a central log destination. Alert on access-denied events that indicate misconfiguration. Alert on successful perimeter crossings from unexpected identities.

## Validation and evidence

- Perimeter inventory with protected projects and services.
- Access level definitions.
- Ingress and egress rules with rationale.
- Dry-run evaluation reports.
- Audit log configuration and alerting.

## Failure correction

Common defects include ingress rules that are too broad, missing egress rules that block legitimate traffic, and perimeters applied without dry-run testing. Corrective actions include a quarterly rule review with sign-off, a dry-run evaluation before every perimeter change, and an alert-tuning review after each new perimeter.

## Limitations

- VPC Service Controls is specific to Google Cloud.
- Not all Google Cloud services are supported; verify per service.
- Perimeters do not protect against all data-exfiltration paths.
- Bridge configuration can introduce unintended access; review carefully.

## Canonical sources

- Google Cloud VPC Service Controls documentation, current edition.
- Google Cloud Architecture Center, current edition.
- Google Cloud IAM Conditions documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for access controls, the engineering leaf for service-to-service authentication, and the operations leaf for incident triage.
