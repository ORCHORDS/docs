# AWS Security Hub Findings Triage Governance

## Purpose

AWS Security Hub aggregates security findings from AWS services (GuardDuty, Inspector, Macie, IAM Access Analyzer, Config), third-party products, and partner integrations. It assigns each finding a severity label (Informational, Low, Medium, High, Critical) and a compliance status. Governance ensures that findings are triaged within a defined SLA, routed to the right owner, remediated or accepted with evidence, and that the security posture trend is visible to leadership.

## Current context and source status

AWS Security Hub is generally available. The current release uses the AWS Security Finding Format (ASFF) and integrates with the security standards CIS AWS Foundations Benchmark, AWS Foundational Security Best Practices, and PCI DSS. Compliance standard identifiers and control identifiers evolve between releases. Validate the current standards pack version in your account before treating any control identifier as a current requirement.

## Governance workflow and controls

### 1. Define severity-based SLAs

Establish an explicit SLA for each severity. Example baseline:

| Severity | Initial triage | Remediation target |
|---|---|---|
| Critical | 1 hour | 24 hours |
| High | 4 hours | 7 days |
| Medium | 1 business day | 30 days |
| Low | 5 business days | 90 days |
| Informational | Next review cycle | Not applicable |

SLAs MUST be tailored to the workload sensitivity. Regulated workloads require shorter SLAs.

### 2. Enable required standards

Enable the standards that map to your compliance obligations. The most common baseline is CIS AWS Foundations Benchmark plus AWS Foundational Security Best Practices. Add PCI DSS or other standards only when the account is in scope for that framework.

### 3. Configure integrations

Integrate AWS-native services (GuardDuty, Macie, Inspector, IAM Access Analyzer) and partner products. Configure the finding format to ASFF. Disable integrations that produce duplicate findings without additional context.

### 4. Automate routing

Use EventBridge rules to route findings to owners. Critical and High findings MUST page the on-call security engineer. Medium and Low findings MUST go to the workload owner's queue. Informational findings MUST go to a backlog review.

### 5. Triage workflow

For every finding, classify as:

- true positive requiring remediation;
- true positive requiring risk acceptance with documented justification;
- false positive requiring rule tuning;
- duplicate of an existing ticket.

Never delete a finding without recording the reason.

### 6. Track and report

Track time-to-triage, time-to-remediate, and the open-finding count by severity. Report weekly to engineering and monthly to leadership. Trend the security posture score.

## Validation and evidence

- Enabled standards and current version.
- SLA matrix by severity.
- EventBridge routing rules.
- Finding closure log with reason codes.
- Trend dashboard with security posture score.

## Failure correction

Common defects include stale findings, unowned critical findings, and rule tuning that masks real issues. Corrective actions include a daily SLA-breach report, mandatory ownership on every finding, and a rule-tuning approval process that requires both security and workload-owner sign-off.

## Limitations

- AWS Security Hub is specific to AWS.
- Some findings lack actionable remediation guidance.
- Severity labels reflect AWS's view, not your risk appetite.
- Findings volume can overwhelm small teams; use automation and aggregation.

## Canonical sources

- AWS Security Hub User Guide, current edition.
- AWS Security Finding Format (ASFF) specification, current edition.
- AWS Security Hub API Reference, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for severity taxonomy, the operations leaf for on-call routing, and the engineering leaf for automation patterns.
