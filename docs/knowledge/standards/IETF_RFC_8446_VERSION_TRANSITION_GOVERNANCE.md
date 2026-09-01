# IETF RFC 8446 Version Transition Governance

## Purpose

This article describes how an organisation records, governs, and transitions between versions of the IETF specification **RFC 8446**, *The Transport Layer Security (TLS) Protocol Version 1.3*, originally published in August 2018 as a Proposed Standard. RFC 8446 was the operative specification of TLS 1.3 until it was **obsoleted by RFC 9846**, *The Transport Layer Security (TLS) Protocol Version 1.3*, published in July 2026, which preserves the TLS version identifier 0x0304 while clarifying, correcting, and tightening the protocol text.

The article is governance guidance. It is not a substitute for the operative RFC, the TLS working group output, or the platform-version documentation that records the TLS stack in use.

## Scope

RFC 8446 specified version 1.3 of the Transport Layer Security (TLS) protocol. It defined the TLS 1.3 handshake, record layer, cipher suites, key schedule, extensions, and authentication mechanisms, and it obsoleted RFC 5246 (TLS 1.2), RFC 5077 (TLS session tickets), and RFC 6961 (OCSP stapling). It also updated RFC 5705 (keying material exporters) and RFC 6066 (TLS extensions).

RFC 9846 retains the same version identifier (0x0304) and is a minor update that tightens some requirements, corrects errata, and adds explicit guidance on points that proved ambiguous in deployed RFC 8446 implementations. Examples include forbidding reuse of KeyShare values between connections, forbidding negotiation of TLS 1.0 and 1.1 (already deprecated by RFC 8996), removing ambiguity around the transcript hash used with PreSharedKey, requiring clients to ignore NewSessionTicket if resumption is unsupported, upgrading the key-update-before-exceeding-limits requirement to MUST, limiting the number of permitted KeyUpdate messages, and clarifying the close_notify alert and the user_canceled alert.

RFC 8446 has therefore transitioned from a current specification to a historical specification that must be retained for audit, contract, and traceability purposes but is no longer the operative IETF specification of TLS 1.3. RFC 8446 was classified as Proposed Standard, not Internet Standard; the path from Proposed Standard to Internet Standard is not the operative transition here — the operative transition is from RFC 8446 to RFC 9846.

## Version governance workflow

### 1. Pin the operative specification and the date consulted

Every reference to TLS 1.3 in policy, design documents, implementation code, deployment documentation, customer-facing material, or audit reports should record the exact specification consulted (RFC 8446 or RFC 9846), the publication date, and any errata or updates published against that specification. An unversioned reference such as "TLS 1.3" loses meaning across the RFC 8446 to RFC 9846 transition because the textual clarifications and tightened requirements change the operative behaviour at edges that some implementations had interpreted loosely.

### 2. Treat the operative specification as the conformance basis

Where a deployment is claimed to be TLS 1.3 conformant, the operative conformance basis is RFC 9846 (not RFC 8446). A claim that an implementation is "RFC 8446 conformant" is acceptable as a historical reference but should be reissued as a claim of RFC 9846 conformance where the implementation has been updated for the successor specification. Mixed claims such as "TLS 1.3 (RFC 8446 / RFC 9846)" are acceptable only if the deployment has been assessed against both and the disposition of any non-applicable or differently-applied requirements is documented.

### 3. Capture the textual changes between RFC 8446 and RFC 9846

A transition register should record the textual and behavioural changes between RFC 8446 and RFC 9846, including:

- the KeyShare reuse restriction;
- the explicit prohibition of TLS 1.0 and TLS 1.1 negotiation (already deprecated by RFC 8996);
- the PreSharedKey transcript hash clarification;
- the NewSessionTicket behaviour when resumption is unsupported;
- the upgrade of the key-update-before-exceeding-limits requirement to MUST;
- the new limits on KeyUpdate messages;
- the close_notify and user_canceled clarifications;
- the new general_error alert;
- the corrections to extension bounds (CertificateRequest.extensions, ClientHello.extensions, NewSessionTicket.extensions);
- the more generic language for asymmetric key exchange (reflecting KEM-based key exchange);
- the removal of the text requiring RSA PSS (consistent with RFC 9963);
- and the removal of the term "master" in favour of "main" for secrets.

The transition register should record the implementation artefacts that needed to change (configuration files, parser changes, behavioural test cases, regression tests, conformance test results) and the dispositions for unchanged artefacts.

### 4. Pin library and platform versions

TLS 1.3 implementations (for example, OpenSSL, BoringSSL, Go crypto/tls, Rust rustls, NSS, GnuTLS, wolfSSL, mbedTLS, Java SunJSSE, Python ssl, and managed TLS-terminating services) track RFC 8446 and RFC 9846 in their own release cycles. Governance should record the library version, the platform version, and the operative RFC tracked by that version.

A library version that claims TLS 1.3 support may track RFC 8446 but not yet have absorbed the RFC 9846 clarifications. Where the platform is held to a specific TLS 1.3 conformance posture, the governance documentation should record the version-specific conformance claim, the test results, and the date the claim was made.

### 5. Pin interoperability test results

TLS 1.3 deployment relies on interoperation between clients, servers, and middleboxes. The transition from RFC 8446 to RFC 9846 affects interoperability at the points where RFC 8446 was ambiguous and where RFC 9846 has clarified behaviour. Governance should retain interoperability test results against the operative specification and should not rely on historical interoperability results when the operative specification has changed.

### 6. Sequence customer-facing claims

Customer-facing claims about TLS 1.3 deployment, security posture, or compliance should record the operative specification reference and the date of the claim. A claim of "TLS 1.3 only" or "no TLS 1.0/1.1" should reference both RFC 8996 (Deprecating TLS 1.0 and TLS 1.1) and the operative TLS 1.3 specification.

### 7. Preserve historical evidence under the specification it was created for

Audit reports, design documents, penetration test reports, and configuration baselines that were assessed against RFC 8446 should remain labelled with the specification under which they were created. Reinterpreting legacy findings against RFC 9846 without preserving the original specification breaks traceability.

### 8. Monitor errata, updates, and the TLS working group

The TLS working group publishes errata, additional Considerations, and follow-on specifications that affect TLS 1.3 deployments. Governance should subscribe to the TLS working group mailing list and the IETF datatracker for the operative specification. A change-log artefact should record the date of each change, the operative specification affected, and the affected clause numbers.

## Controls and evidence

Version-transition evidence typically includes:

- a dated specification register recording the operative TLS 1.3 specification consulted (RFC 8446 or RFC 9846) for each artefact;
- a textual transition register capturing the changes between RFC 8446 and RFC 9846, with dispositions for implementation artefacts;
- a library-and-platform register recording the library version, platform version, and the operative specification tracked by each;
- interoperability test results stored with the specification reference under which they were produced;
- configuration baselines stored with the specification reference under which they were created;
- audit reports and penetration-test findings stored with the specification reference under which they were assessed;
- customer-facing claims stored with the specification reference and date of issue; and
- training and competency records showing staff were briefed on the operative specification.

## Validation

Validation that a TLS 1.3 deployment continues to meet the operative specification typically draws on:

- internal review of implementation artefacts against the operative specification;
- external interoperability tests against peer implementations;
- conformance tests where they exist for the operative specification;
- penetration tests that focus on the operative specification's tightened requirements (KeyShare reuse, PreSharedKey transcript hash, NewSessionTicket handling, KeyUpdate limits);
- vendor advisories and patch tracking for the TLS library in scope;
- monitoring of the TLS working group output and IETF datatracker for errata; and
- where applicable, sector-specific regulatory expectations about TLS deployment.

## Failure correction

Common transition failures include:

- citing "TLS 1.3" without specifying the operative RFC (RFC 8446 or RFC 9846) in policy or customer-facing material;
- continuing to label a deployment as "RFC 8446 conformant" after the operative specification has become RFC 9846;
- failing to record the textual changes between RFC 8446 and RFC 9846 in a transition register;
- assuming that library-version changes absorb the RFC 9846 clarifications without re-testing;
- mixing RFC 8446 test results with RFC 9846 test results without recording the specification reference under which each was produced;
- conflating the RFC 8446 to RFC 9846 transition with the Proposed Standard to Internet Standard track progression, which is a different IETF process;
- failing to preserve historical evidence under the specification it was created for;
- making customer-facing claims about TLS 1.3 deployment that do not reference the operative specification; and
- ignoring errata or updates published against the operative specification.

A corrective action should document the specification under which the failure occurred, the operative specification that should have been used, the disposition of historical evidence, and the owner of the re-issued artefact.

## Limitations

TLS 1.3 governance at the protocol level is only one layer of a deployment's security posture. Application-layer authentication, certificate validation, key management, log handling, and supply-chain integrity for the TLS stack are governed by other standards and frameworks (for example, RFC 5280 for certificates, RFC 7469 for certificate transparency, RFC 8555 for ACME, ISO/IEC 19790 for cryptographic modules, and ISO/IEC 27001 for information security). The RFC 8446 to RFC 9846 transition does not address those layers.

The transition from RFC 8446 to RFC 9846 is a minor textual update. The TLS 1.3 version identifier (0x0304) is preserved, the wire format is largely unchanged, and most deployments that correctly implemented RFC 8446 will continue to interoperate against RFC 9846. The transition's compliance risk is concentrated at the points RFC 9846 explicitly clarifies or tightens.

## Canonical sources

- IETF — RFC 8446, *The Transport Layer Security (TLS) Protocol Version 1.3* (August 2018), obsoleted by RFC 9846: https://www.rfc-editor.org/info/rfc8446
- IETF — RFC 9846, *The Transport Layer Security (TLS) Protocol Version 1.3* (July 2026), obsoletes RFC 8446: https://www.rfc-editor.org/info/rfc9846

## Scope note

This article describes version and reference governance for RFC 8446 in the context of the operative specification RFC 9846. It does not reproduce either RFC, declare conformance, or substitute for the operative RFC, the TLS working group output, or the platform-version documentation that records the TLS stack in use.