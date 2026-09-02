# AWS Control Tower Guardrail Governance

## Purpose

AWS Control Tower provides a landing-zone orchestration service that provisions a multi-account AWS environment with baseline identity, logging, networking, and security configurations. Guardrails are preventive or detective controls expressed as AWS Organizations policies, AWS Config rules, or AWS Security Hub controls. Governance ensures that new accounts inherit a known baseline, deviations are detected, and exceptions are recorded.

## Current context and source status

AWS Control Tower is generally available. The current 3.0 release introduced organization-wide controls, the ability to apply controls at the OU level, and inheritance from root to child OUs. Specific guardrail identifiers (for example, AWS-GR_AUDIT_BUCKET_ENCRYPTION) and their configurable parameters change between releases. Validate the current control catalog and the version deployed in your landing zone before treating any rule identifier as a current requirement.

## Governance workflow and controls

### 1. Establish a control baseline

Adopt the mandatory controls as the floor. Add strongly recommended controls where the workload sensitivity justifies them, and add optional controls for regulated workloads only when a documented risk acceptance supports them.

Record in the control register:

- control identifier;
- control type (preventive, detective, proactive);
- severity;
- supported framework mappings;
- deployment OU(s);
- drift response procedure;
- exception owner and expiry.

### 2. Define OU structure

Map each organizational unit to a workload class or environment. Common patterns include a root, infrastructure OU, sandbox OU, workloads OU, suspended OU, and a sensitive-workloads OU. Apply the principle that inheritance flows from root downward and that more restrictive OUs contain more sensitive workloads.

### 3. Enable preventive and detective controls

Preventive controls (Service Control Policies) stop non-conforming actions before they occur. Detective controls (AWS Config rules, Security Hub controls) observe state and produce findings. Use both: preventive controls reduce the volume of findings, and detective controls catch state drift introduced by API operations that preventive controls cannot block.

### 4. Manage account factory

Use Account Factory to provision new accounts with a known baseline. Add customizations through Terraform or AWS CloudFormation StackSets. Every custom account factory product must be reviewed for guardrail compatibility before publication.

### 5. Handle drift

Investigate every drift event. Classify the drift as unauthorized change, authorized change awaiting guardrail update, accepted exception, or false positive. Update the guardrail where the underlying rule needs refinement; do not delete findings without evidence.

### 6. Manage exceptions

Maintain an exception register that records the control, account or OU, business justification, compensating control, owner, expiry date, and review date. Enforce expiry: exceptions without review must be automatically revoked on the expiry date.

## Validation and evidence

- Landing-zone version and deployed control catalog snapshot.
- OU structure diagram and inheritance map.
- Account Factory baseline configuration artifact.
- Drift event log with classification and remediation.
- Exception register with expiries and reviews.
- Security Hub and AWS Config findings summary.

## Failure correction

Common defects include unused strongly recommended controls, drift that accumulates because no owner is assigned, and exceptions that never expire. Corrective actions include a monthly guardrail-effectiveness review, automated exception expiry, and an OU hygiene cadence that retires accounts that no longer need a sensitive tier.

## Limitations

- AWS Control Tower is specific to AWS.
- Preventive controls cannot block every action; use them with detective controls.
- The control catalog evolves; treat identifiers as version-specific.
- Some controls are region-specific; validate per deployment region.

## Canonical sources

- AWS Control Tower User Guide, current edition.
- AWS Control Tower API Reference, current edition.
- AWS Security Reference Architecture (SRA), current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for control taxonomy, the operations leaf for account provisioning, and the business leaf for cost allocation.
