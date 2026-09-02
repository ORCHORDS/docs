# Cloudflare Zero Trust Access Governance

## Purpose

Cloudflare Zero Trust Access replaces traditional VPNs with identity-aware, application-level access. Governance ensures that every protected application has explicit access policies, that identity providers are configured with strong authentication, that device posture is enforced where required, and that access logs are reviewed for anomalies.

## Current context and source status

Cloudflare Zero Trust is generally available. The current feature set includes Cloudflare Access (self-hosted and SaaS applications), Cloudflare Tunnel, Cloudflare Gateway (DNS, HTTP, network filtering), and Cloudflare Browser Isolation. Specific feature identifiers (for example, `http_rules`, `device_posture` checks, `identity_provider_id`) evolve; verify the current configuration reference before treating any identifier as a current requirement.

## Governance workflow and controls

### 1. Define identity providers

Configure one or more identity providers (IdP) such as Okta, Microsoft Entra ID, Google Workspace, or social identity providers for low-trust applications. Use SAML or OIDC. Require MFA on the IdP.

### 2. Define access policies

For each protected application, define access policies that combine:

- identity (specific users, groups, email domains);
- device posture (managed device, OS version, client certificate);
- geography;
- network (corporate IP range, country code);
- time of day.

Reject allow-all policies except for low-risk public applications.

### 3. Use service tokens for machine access

For machine-to-machine traffic, issue service tokens with specific scopes. Rotate service tokens on a documented cadence. Revoke tokens on workload decommissioning.

### 4. Configure browser isolation

Use Cloudflare Browser Isolation to render untrusted web content in a remote browser. Enable for high-risk browsing destinations and for downloading untrusted documents.

### 5. Configure gateway policies

Use Cloudflare Gateway to filter DNS, HTTP, and network traffic. Apply category-based and threat-based blocklists. Allowlist specific destinations where required.

### 6. Audit access

Send Access and Gateway logs to a central SIEM or log destination. Review access decisions and configuration changes. Alert on unusual patterns: out-of-hours access, denied access from a legitimate user, configuration changes by unexpected administrators.

### 7. Apply principle of least privilege

Reuse access policies across applications where possible. Document any application-specific policy. Avoid creating one-off policies for individual users.

## Validation and evidence

- Application inventory with access policy per application.
- Identity provider configuration.
- Service token inventory with rotation status.
- Browser Isolation configuration.
- Gateway policy configuration.
- Audit log destination and retention.

## Failure correction

Common defects include allow-all policies, missing MFA on the IdP, and unrevoked service tokens. Corrective actions include a quarterly policy review with mandatory justification for any allow rule, automated MFA enforcement, and a quarterly service token review.

## Limitations

- Cloudflare Zero Trust is Cloudflare-specific.
- Some IdPs require additional configuration; validate per IdP.
- Service tokens are bearer credentials; treat them with the same care as API keys.
- Browser isolation has performance implications for media-rich content.

## Canonical sources

- Cloudflare Zero Trust documentation, current edition.
- Cloudflare Access documentation, current edition.
- Cloudflare Gateway documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for access controls, the engineering leaf for workload authentication, and the operations leaf for incident triage.
