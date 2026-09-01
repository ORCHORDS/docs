# OAuth Marketing Platform Authorization Governance

## Scope

This control governs OAuth-based authorization used to connect marketing platforms, advertising accounts, social channels, CRMs, analytics tools, data clean rooms, consent platforms, and automation services. It applies to applications that request delegated access to create campaigns, read audiences, upload conversions, sync leads, retrieve reports, manage email assets, post content, or administer account settings. The control covers client registration, scope approval, grant selection, redirect URI governance, token handling, refresh management, revocation, monitoring, evidence, and correction. It does not determine whether a marketing activity is lawful, whether a platform’s terms permit a particular campaign, or whether customer data may be shared with a vendor. Those decisions require separate legal, procurement, privacy, and platform policy review.

OAuth 2.0 is defined by the RFC Editor as a framework that lets a third-party application obtain limited access to an HTTP service through an approval interaction or on its own behalf: [RFC 6749, The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/info/rfc6749/). Bearer token usage is separately described as a method for using tokens in HTTP requests, with the important property that a party in possession of a bearer token can use it to access the associated resource: [RFC 6750, Bearer Token Usage](https://www.rfc-editor.org/info/rfc6750/). These primary sources provide protocol grounding. This document does not claim that any specific vendor implements every OAuth option identically.

## Required Fields And Controls

Every OAuth integration must have an integration owner, business purpose, platform account, client identifier, application environment, grant type, redirect URIs, requested scopes, approved scopes, token storage location, rotation or refresh behavior, revocation process, and last review date. Production and non-production clients must be separated unless the platform cannot support separation and the exception is approved. Redirect URIs must be exact, owned by the organization or approved vendor, use HTTPS for production, and avoid wildcards unless a platform-specific constraint is documented and risk-accepted.

Scope requests must follow least privilege. A lead retrieval integration should not request campaign write permissions unless it actually updates campaigns. A reporting integration should not request audience management or account administration. Scopes must be mapped to business actions in plain language, such as `read campaign performance reports`, `upload offline conversion events`, `create lead form webhook subscriptions`, or `manage email templates`. The approval record must distinguish required scopes from optional scopes and document why each required scope is necessary.

Tokens must be treated as sensitive credentials. Access tokens, refresh tokens, authorization codes, client secrets, private keys, and device codes must not be stored in source code, pasted into tickets, logged in application output, embedded in client-side pages, or shared through chat. Token storage must use an approved secrets manager, encrypted database field, or platform-managed credential store. Logs must redact authorization headers and token-like values. Token access must be limited to services and operators with a documented need.

Public clients, confidential clients, service accounts, and server-to-server flows must be identified accurately. Authorization-code flows for user-delegated access should use current platform-recommended protections such as proof-key mechanisms when applicable to the client type and provider. Client credentials or equivalent app-only flows must be limited to use cases where user delegation is not required and the provider supports that model. Deprecated, legacy, or password-based flows require explicit security exception review before use.

## Workflow

OAuth onboarding begins with a request from the marketing or integration owner. The request states the platform, accounts affected, business process, data categories, actions to be performed, required scopes, expected users, environment, and vendor or internal application responsible for the connection. Security reviews redirect URIs, client type, token storage, secret handling, and logging. Marketing operations verifies the business purpose and account ownership. Privacy or legal review is added when personal data, audience data, conversion data, or cross-platform sharing is involved.

Client registration must be performed by an approved administrator. The administrator records the client ID, platform tenant or account, allowed redirect URIs, application name shown to users, owner group, and support contact. Client secrets are delivered only through approved secret-management channels. The integration implementer configures the application without committing secrets to the repository. Before production authorization, the team tests in a sandbox or low-risk account if the provider supports it.

Authorization must be performed by an account holder with appropriate authority. Shared personal accounts should not be used for durable business integrations. When a platform requires a user grant, the owner must identify what happens if that user leaves, loses access, changes role, or revokes consent. Integrations relying on a single employee’s authorization must have a continuity plan, such as service accounts, platform system users, or documented reauthorization procedures where supported.

## Validation Evidence And Tests

Required pre-production evidence includes approved scope mapping, client registration screenshot or export, redirect URI list, token storage design, secret redaction test, error handling behavior, and revocation test plan. The OAuth callback must reject unexpected `state` values when a state parameter is used, reject unregistered redirect targets, handle authorization denial, and avoid exposing authorization codes in logs. Token exchange failures must be observable without revealing token contents.

Functional tests must verify that the integration can perform only the approved actions. For example, a report reader should successfully retrieve allowed reports and fail or lack access for campaign modification. A conversion upload integration should upload only to approved accounts. A lead sync integration should not enumerate unrelated account assets if that scope was not approved. Negative tests are important because a successful integration can still be overprivileged.

Operational monitoring should track token refresh failures, authorization errors, scope changes, client-secret age, unused clients, inactive integrations, sudden increases in API calls, calls to unexpected endpoints, and authorization by unexpected users. Periodic review must compare the active platform app configuration against the approved record. If a provider adds new permissions, changes scope semantics, or migrates API versions, the integration owner must reassess the mapping before relying on the changed access model.

## Failures And Corrections

Common failures include requesting broad scopes for convenience, leaving old redirect URIs active, using one client across production and test, storing refresh tokens in configuration files, failing to rotate exposed client secrets, and relying on a departed employee’s authorization. Another common issue is platform drift: the approved scope list says reporting only, but the platform application now has campaign management because a later feature added it without governance review.

If a token, client secret, or authorization code is exposed, the immediate correction is to revoke or rotate the credential, remove the exposure from active systems where possible, assess logs and repositories for persistence, and verify that the integration resumes with a new credential. The incident record must identify the credential type, platform, affected account, exposure location, time window, actions taken, and residual risk. This document does not decide breach notification or contractual notice obligations.

If an integration is over-scoped, the correction is to reduce scopes in the provider configuration and application code, reauthorize if required, and retest the intended functions. If scope reduction is impossible because the provider bundles permissions, the owner must document the constraint, compensating controls, and review frequency. If an unauthorized user granted access, revoke the grant and reauthorize through an approved account or system user. If a redirect URI is stale or points to an unowned domain, remove it immediately and validate that login and callback flows still operate.

## Requirements Versus Recommendations

Required: document every OAuth integration; approve scopes before production; use exact approved redirect URIs; protect tokens and secrets; separate environments where possible; test denial, callback, token exchange, and revocation behavior; monitor active clients and grants; and correct exposed, stale, or overbroad access with evidence.

Recommended: use centralized OAuth brokers or secret stores; automate app configuration drift checks; use short-lived access tokens with controlled refresh; prefer service identities for durable integrations when providers support them; maintain runbooks for reauthorization; and review scopes whenever marketing workflows or provider APIs change.

## Limitations

OAuth governs delegated authorization mechanics; it does not guarantee that the user granting access has proper business authority, that a provider’s API behavior is stable, or that a marketing use case is compliant. Bearer tokens remain powerful if disclosed. Provider consoles vary in terminology and enforcement, and some platforms bundle permissions coarsely. This control reduces preventable authorization risk through approval, least privilege, evidence, and monitoring, but it must operate alongside vendor management, privacy review, access management, and incident response.

## Canonical sources

- **Primary authority 1 — RFC 6749, The OAuth 2.0 Authorization Framework:** [https://www.rfc-editor.org/info/rfc6749/](https://www.rfc-editor.org/info/rfc6749/)
- **Primary authority 2 — RFC 6750, Bearer Token Usage:** [https://www.rfc-editor.org/info/rfc6750/](https://www.rfc-editor.org/info/rfc6750/)
