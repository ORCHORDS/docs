# GCP Workload Identity Federation Governance

## Purpose

Workload Identity Federation allows workloads running outside Google Cloud (for example, on-premises, AWS, or Azure) to access Google Cloud resources without service-account keys. Governance ensures that identity pools and providers are explicitly scoped, that attribute mappings are reviewed, and that workload impersonation is audited.

## Current context and source status

Workload Identity Federation is generally available. The current feature set includes identity pools, OIDC and SAML providers, AWS-specific providers, attribute mappings, and attribute conditions. Specific pool and provider limits, supported audiences, and supported identity providers evolve; verify the current limits before designing a federation.

## Governance workflow and controls

### 1. Choose identity provider type

Use OIDC for workloads that already have an OIDC token issuer (Kubernetes service accounts, GitHub Actions, GitLab CI). Use SAML for legacy identity systems. Use the AWS provider for AWS workloads.

### 2. Define identity pool

An identity pool groups external identities. Create separate pools for distinct trust boundaries (for example, one pool per CI provider, one pool per partner organization). Do not mix trust boundaries within a single pool.

### 3. Configure attribute mapping

Map provider claims to Google Cloud attributes. For OIDC, map `assertion.sub` to `google.subject`. Reject mappings that use wildcard claims.

### 4. Configure attribute conditions

Attribute conditions restrict which external identities can impersonate service accounts. Use conditions to enforce:

- specific issuer;
- specific audience;
- specific subject pattern;
- required claims (for example, repository name).

### 5. Restrict service-account impersonation

Grant `roles/iam.workloadIdentityUser` only to specific external identities and only for specific service accounts. Avoid granting the role to broad identity pools.

### 6. Audit

Enable Cloud Audit Logs for Identity and Access Management (IAM). Alert on:

- new identity-pool creation;
- new provider creation;
- workload impersonation from outside expected patterns;
- attribute condition changes.

### 7. Rotate and revoke

Establish a rotation cadence for the trust relationship. Define a revocation procedure in case the external identity provider is compromised. Test the revocation procedure.

## Validation and evidence

- Identity pool inventory with purpose and owner.
- Provider configuration with attribute mapping.
- Attribute conditions.
- Service-account impersonation grants.
- Audit log destination and retention.
- Revocation procedure.

## Failure correction

Common defects include overly permissive attribute conditions, missing audit logging, and revoked identities not removed from impersonation grants. Corrective actions include a quarterly attribute review, automated audit-log verification, and a periodic exercise of the revocation procedure.

## Limitations

- Workload Identity Federation is specific to Google Cloud.
- Not all claim types are supported; verify per provider.
- Attribute mapping is sensitive to upstream claim structure changes.
- Federation introduces additional latency; design accordingly.

## Canonical sources

- Google Cloud Workload Identity Federation documentation, current edition.
- Google Cloud IAM documentation, current edition.
- Google Cloud Architecture Center, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for identity controls, the engineering leaf for workload authentication, and the operations leaf for incident response.
