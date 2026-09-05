# AWS Organizations — Service Control Policy (SCP) Governance

## Purpose

Establish governance on the AWS Organizations Service Control Policy (SCP) primitive as the account-level guardrail mechanism for multi-account AWS environments. This article scopes SCPs only; it does not cover resource-level authorization via AWS IAM, nor AWS Control Tower (a separate governance layer that consumes SCPs) — see the companion articles in this collection.

## Current status

- SCP is a published AWS Organizations capability, documented by AWS as part of the Organizations service. Current capability is governed through the AWS Organizations User Guide; specific JSON schema elements and SCP effect behaviors are referenced in the AWS Organizations API Reference and the IAM policy reference.
- SCPs function alongside (not instead of) AWS IAM. SCPs act as account-level guardrails and cannot grant permissions; IAM remains the effective authorization layer that grants permissions to identities.
- Status as of 2026-09-04: SCP remains the AWS-wide account guardrail mechanism. AWS has layered additional controls (e.g., declarative policies for Amazon S3 / EC2 / IAM, session permissions boundaries) that interact with SCPs and should be considered when modeling the governance chain.

## Sources

- Primary: AWS Organizations User Guide, https://docs.aws.amazon.com/organizations/latest/userguide/ — sections "Service control policies" and "SCP syntax."
- AWS API reference: https://docs.aws.amazon.com/organizations/latest/APIReference/ — for the JSON schema and the policy-types endpoint.
- AWS Organizations IAM policy reference: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html — for the underlying policy grammar shared with IAM.
- Companion articles in this collection: AWS_CONTROL_TOWER_GUARDRAIL_GUARDRAIL_GOVERNANCE.md (governs the Control Tower overlay) and GCP_ORGANIZATION_POLICY_GOVERNANCE.md (governs the GCP equivalent constraint model, conceptually adjacent).

## Scope note

AWS Organizations SCPs are JSON documents evaluated together with IAM identity-based policies. The interaction is:

- For an action to be allowed by AWS, the caller's identity policy must allow the action AND any applicable SCP must allow the action. SCPs cannot grant (only Deny or Allow with explicit enumeration in an Allow statement).
- An account inherits SCPs from its organization root and every OU between the root and the account. Child OUs cannot grant a permission that is denied higher up the tree.
- The SCP default behavior when no explicit SCP is attached at any level is Allow with full identity policy effective. When an explicit SCP is attached at the root, the implicit deny for unattached accounts is enabled.

Governance-relevant SCP design points to record:

1. Privilege escalation prevention. SCPs must include explicit deny statements for actions such as `iam:CreateAccessKey`, `iam:AttachUserPolicy`, `sts:AssumeRole` to accounts outside a designated permissions boundary. SCPs alone do not suffice against all escalation paths; layered controls (IAM permission boundaries, Control Tower controls, session managers) are required.
2. Region denial for regulated data. SCPs can restrict actions to specific AWS Regions; this is the primary mechanism for governance programs that need to confine workloads to specific geographies. The Region list must be reviewed and updated when AWS adds Regions.
3. Service denial scopes. SCPs are evaluated against service + action + resource type. Governance artifacts should record which services are explicitly denied (e.g., services disallowed under a compliance scope).
4. Inheritance visualization. The effective SCP for an account is the joint set of every SCP attached to root + each OU. Any audit should resolve the merged SCP, not the per-node document.
5. SCP vs Control Tower. Control Tower consumes SCPs and deploys them as the "preventive" guardrail set; governance documentation should distinguish bespoke SCPs authored by the platform team from Control Tower-managed SCPs.

Operational governance requires that SCP changes go through a change-control flow. SCPs that deny required actions have produced incident-acknowledgment failures; therefore, the governance process requires a documented rollback SCP held out-of-band during any change window. AWS Organizations does not natively support SCP change history beyond CloudTrail events; the governance program should record what the expected SCP set is for every OU in a signed artifact reviewed against the live state on a periodic cadence.

This article does not cover AWS Identity-Based Policies, Resource-Based Policies, Permission Boundaries, or Session Policies — each is governed separately under IAM.
