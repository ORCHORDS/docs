# AWS KMS Key Management Governance

## Purpose

AWS Key Management Service (KMS) provides managed cryptographic key creation, rotation, and access control. Governance ensures that every workload uses the correct key class, that key policies enforce least privilege, that rotation and audit are configured, and that key material is destroyed only when the retention obligation has expired.

## Current context and source status

AWS KMS is generally available. The current feature set includes customer managed keys (CMK), AWS managed keys, AWS owned keys, asymmetric keys, HMAC keys, multi-Region keys, and external key stores (XKS) backed by HSMs on premises. KMS-specific limits (calls per second, key policies size, aliases per key) are documented in the AWS KMS quotas page; verify the current values before designing a workload that depends on them.

## Governance workflow and controls

### 1. Choose key class

Use customer managed keys (CMK) for workloads that require key rotation control, audit visibility, or the ability to revoke access. Use AWS managed keys only when the AWS service's default behavior is acceptable. Do not use AWS owned keys for sensitive workloads because the key is not visible in the customer's account.

### 2. Define key policies

Each key MUST have an explicit key policy. The key policy MUST grant least-privilege permissions to specific IAM principals. Avoid using wildcard principals (`*`) unless the key is intentionally public. Cross-account access MUST be granted through the key policy plus a grant, not through inline IAM policies on the consumer side.

### 3. Configure rotation

Enable automatic annual rotation for symmetric CMKs. Asymmetric CMKs are not rotated; design your workload to support re-encryption when an asymmetric key is replaced. Track rotation status in the control register.

### 4. Audit every use

Enable AWS CloudTrail data events for KMS (or management events if data events are not enabled). Configure CloudWatch alarms for unusual API patterns, including `DisableKey`, `ScheduleKeyDeletion`, and `PutKeyPolicy`.

### 5. Manage grants

Use grants for short-term delegated access (for example, AWS services acting on behalf of the principal). Track grant usage and revoke unused grants.

### 6. Manage aliases

Use aliases to give keys stable, human-readable names. Maintain a documented alias scheme such as `alias/<purpose>-<environment>-<version>`. Validate that aliases resolve to the intended key before relying on them.

### 7. Plan deletion

Key deletion has a mandatory waiting period (7 to 30 days). Validate dependencies before scheduling deletion. Maintain a record of every deletion event with the business justification.

## Validation and evidence

- Key inventory with key class, purpose, and owner.
- Key policy review artifact.
- Rotation status and rotation history.
- CloudTrail configuration for KMS.
- Grant inventory with revocation status.
- Deletion log with justifications.

## Failure correction

Common defects include wildcard key policies, missing rotation, and orphaned aliases. Corrective actions include a quarterly key policy review, an automated check for missing rotation, and an alias reconciliation process.

## Limitations

- AWS KMS is specific to AWS.
- KMS API call quotas apply; design around them.
- Key deletion is irreversible after the waiting period.
- Multi-Region keys have replication lag; design around it.

## Canonical sources

- AWS KMS Developer Guide, current edition.
- AWS KMS Cryptographic Details whitepaper, current edition.
- AWS KMS API Reference, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for workload encryption patterns, and the operations leaf for key lifecycle.
