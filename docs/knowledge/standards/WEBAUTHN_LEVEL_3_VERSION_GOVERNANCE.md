# WebAuthn Level 3 Version Governance

## Purpose

This article describes a project-neutral governance model for adopting the W3C Web Authentication (WebAuthn) Level 3 Recommendation. It is intended for engineering, security, identity, and product teams that rely on or interoperate with WebAuthn.

The objective is to make the WebAuthn version choice and migration an explicit, evidence-based decision rather than an accidental consequence of browser or platform evolution.

## Current status

WebAuthn Level 3 is published as a W3C Recommendation. The Recommendation date for the current published Level 3 is **25 August 2026**, as recorded by the W3C Web Authentication Working Group.

WebAuthn Level 2 remains a W3C Recommendation. The Working Group intends Level 3 to supersede Level 2 over time as implementations, conformance materials, and dependent specifications catch up. Treat Level 3 as the authoritative current target unless an interop, dependency, or platform constraint forces a temporary reliance on Level 2 behavior.

The W3C Web Authentication Working Group publishes the Recommendation, Editor’s Draft, and issue tracker at the locations listed in the Sources section. Conformance test suites and registry entries evolve alongside the Recommendation.

The contents of the Recommendation may be amended through the W3C process, including Candidate Amendments, Candidate Recommendation drafts, and errata. Working Group decisions can also add, refine, or deprecate features. Internal documentation should record the exact date and version consulted, not a generic reference to "WebAuthn."

## What Level 3 changes for governance

WebAuthn Level 3 is intended to be largely backwards-compatible with Level 2 in deployed behavior, but it formalizes and clarifies several areas that affect implementation and assurance. Treat the following as a high-level feature inventory rather than an exhaustive list:

- refined definitions and terminology for authenticators, attestation, and credentials;
- clearer treatment of cross-origin registration and authentication ceremonies, including the use of related origins;
- expanded coverage of large blob, hybrid transports, and multi-factor credential composition;
- more explicit requirements for client and authenticator capabilities, including the `getClientCapabilities` extension area;
- refined privacy guidance, including guidance on username and identifier handling;
- additional guidance on attestation verification, including Authenticator Attachment evaluation;
- updates to the registration and authentication ceremonies that clarify success and failure semantics;
- refinements to extensions, including PRF, large blob, and credential properties extensions; and
- alignment with current IETF and FIDO Alliance registries that WebAuthn depends on.

Level 3 does not, by itself, mandate a specific migration timeline for already-deployed Level 2 relying parties. Migration pressure will normally come from browsers, platforms, and attestation providers as their support matures.

## Governance workflow

### 1. Decide whether to target Level 3

Choose between Level 3, Level 2, or a hybrid posture based on evidence rather than novelty. Consider:

- browser support for the relevant client capabilities and extensions;
- platform authenticator availability on the supported operating systems;
- attestation provider support, including the attestation formats you require;
- whether related-origin registration or authentication is needed;
- whether large-blob, hybrid, or PRF extension support is required;
- dependency on other specifications that reference a specific level; and
- regulatory, contractual, or audit expectations about the version in use.

A relying party that does not need Level 3 features may remain on Level 2 conformance for some time, provided browsers and platforms continue to support it. A relying party that needs Level 3 capabilities, or that wants predictable behavior across future browsers, should adopt Level 3.

Document the choice, the rationale, and the evidence in a version register.

### 2. Detect capabilities instead of assuming them

WebAuthn capability detection should be performed through documented mechanisms rather than inferred from the user-agent string alone. Where the protocol exposes a capability discovery method, prefer it. For example, the `getClientCapabilities` extension area allows a relying party to ask a client which features it supports, subject to the user’s consent.

Maintain a capability matrix that maps each relying-party requirement to:

- the client or browser versions that support it;
- the platform authenticator versions that support it;
- the attestation path that supports it;
- the extension negotiation that activates it; and
- the user-visible affordance that surfaces the capability.

The matrix should be reviewed when browsers ship major releases, when attestation providers issue guidance, or when the W3C publishes an amendment.

### 3. Manage fallbacks explicitly

Some users will not have access to Level 3 features even after adoption. Plan for fallback paths rather than treating fallback as a failure of Level 3.

Fallback design should:

- enumerate the conditions that trigger fallback (for example, missing authenticator class, missing extension, missing transport);
- preserve the strongest available authentication rather than collapsing all fallbacks to a single low-assurance option;
- record why fallback occurred without retaining sensitive authenticator output;
- surface a clear user experience that does not mislead users about the protection in place; and
- re-evaluate fallback eligibility when the user upgrades a device or platform.

Fallbacks should not silently degrade identity assurance. Where a fallback materially reduces protection, require a compensating control such as an additional factor, a higher-risk step-up, or a temporary limitation on the action permitted.

### 4. Preserve interoperability

WebAuthn implementations are highly interoperable across browsers and platforms at the Level 2 baseline. Level 3 adoption should preserve that interoperability where possible.

Interoperability checks should include:

- registration and authentication ceremonies across at least one browser from each major engine;
- platform authenticators across the operating systems you support;
- roaming authenticators via the transports you intend to support, including hybrid transport where applicable;
- attestation verification against each attestation provider you use;
- extension behavior across clients; and
- error and edge-case handling that does not depend on browser-specific behavior.

Interoperability regressions should be treated as security-relevant until proven otherwise. They often signal a misinterpretation of an option or extension.

### 5. Manage terminology migration

Level 3 refines terminology and may rename fields, options, or extension behaviors. Documentation, public material, audit evidence, and support content should be updated to reflect the new vocabulary without losing meaning.

When migrating terminology:

- map old terms to new terms explicitly rather than substituting mechanically;
- retain audit evidence under the original terminology it was recorded with;
- update support content to describe behavior, not terminology; and
- avoid claims that WebAuthn "changed" in ways that mislead users about the underlying protections.

Internal glossaries and customer-facing help should reflect the level actually targeted by the deployment.

### 6. Monitor amendments and errata

The W3C Web Authentication Working Group may publish Candidate Amendments, corrigenda, and errata that affect implementation or interpretation. Subscribe to the Working Group publication feed and the issue tracker, and assign an owner to triage changes.

Maintain a record of:

- the Recommendation date and level consulted;
- the URL of the Recommendation and Editor’s Draft;
- any Candidate Amendments under review;
- any errata or corrigenda that have been published; and
- the internal version of documentation that captured the snapshot.

## Operational failure modes

Common failures include:

- assuming Level 3 features are available without checking client and authenticator capabilities;
- using browser or platform version numbers as a proxy for WebAuthn feature support;
- inferring related-origin support from the absence of errors;
- failing to verify attestation against the current provider format;
- relying on Level 2-specific option behavior that Level 3 clarifies;
- applying fallback paths without a compensating control when assurance materially drops;
- recording WebAuthn evidence with terminology that no longer matches the version in use;
- treating editor’s drafts as authoritative; and
- treating the WebAuthn Recommendation as the sole source, while ignoring dependent registry and extension specifications.

## Sources

- [Web Authentication: An API for accessing Public Key Credentials Level 3 (W3C Recommendation, 25 August 2026)](https://www.w3.org/TR/webauthn-3/)
- [Web Authentication: An API for accessing Public Key Credentials Level 2 (W3C Recommendation)](https://www.w3.org/TR/webauthn-2/)
- [W3C Web Authentication Working Group issues](https://github.com/w3c/webauthn/issues)

## Scope note

This article is project-neutral governance guidance, not a substitute for the normative text of the WebAuthn Recommendation. It does not reproduce W3C text and does not establish conformance. Relying parties should consult the current Recommendation, Editor’s Draft, and dependent registries before making version, capability, or attestation decisions.
