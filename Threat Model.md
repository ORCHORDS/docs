> Auto-generated from `Threat Model.md` in the docs repo.

> Auto-generated from `docs/security/THREAT_MODEL.md` in the docs repo.

---
title: "Threat Model"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "maya.rodriguez (Backend Lead) — security lead; kirk.beka (CTO) — approver"
status: "draft"
iso-refs: ["ISO/IEC 27001:2022 A.5.7", "ISO/IEC 27002:2022 A.5.7", "OWASP ASVS 4.0.3"]
---

# Threat Model

**Project:** Beetle Studio
**Owner:** Maya Rodriguez (Backend Lead) — security lead; Kirk Beka (CTO) — approver
**Reviewers:** Mike Johnson (DevOps Lead), Sarah Miller (Build & Release Engineer)
**ISO Standards:** ISO/IEC 27001:2022 A.5.7 (Threat intelligence), ISO/IEC 27002:2022 A.5.7, OWASP ASVS 4.0.3
**Version:** 1.0.0
**Last Updated:** 2026-06-21

> **Status note (2026-06-21):** this document is a **draft** — the threat model is being built up incrementally. STRIDE categories are mapped to assets below, but specific threat actors and full attack trees are not yet enumerated. Updates are expected as the application matures. The framework follows [STRIDE](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats) and the [OWASP ASVS 4.0.3](https://owasp.org/www-project-application-security-verification-standard/) verification model.

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Beetle Studio desktop application (Windows 10/11 x64), its installer, and its on-device data flows |
| **Out of scope** | The marketing website (cutshit.net); the cloud backend (see `docs/backend/API_CONTRACT.md` and a separate cloud threat model) |
| **Diátaxis form** | Reference |
| **Primary audience** | Maya Rodriguez, Kirk Beka, all engineers |
| **Secondary audience** | External security auditors; future maintainers |

---

## Purpose

Establish a shared mental model of who might attack Beetle Studio, what they might want, and which components of the application are most exposed. The output of this document drives security priorities in the backlog and the security gates in the release pipeline.

The threat model is intentionally lightweight: it maps each asset to STRIDE categories, lists the dominant threat actors, and points to the controls already in place. A full attack-tree analysis is out of scope for the first iteration and should be produced for the highest-risk assets before the v2.0 release.

## Methodology

We use the **STRIDE** model:

| Letter | Threat | Property violated |
|---|---|---|
| **S** | Spoofing | Authenticity |
| **T** | Tampering | Integrity |
| **R** | Repudiation | Non-repudiation |
| **I** | Information disclosure | Confidentiality |
| **D** | Denial of service | Availability |
| **E** | Elevation of privilege | Authorization |

For each asset, we mark which STRIDE categories apply. We then list the dominant threat actors and the existing controls. The gaps become backlog items.

## Asset Inventory

| ID | Asset | Description | Owner |
|---|---|---|---|
| A-1 | User project files (.bproj) | Beetle Studio project files on disk; contain media paths, edit history, keyframes | Sarah Miller (file format), Maya Rodriguez (encryption) |
| A-2 | Rendered preview cache | Cached preview frames on disk during a project | Daniel Kim (preview pipeline) |
| A-3 | Exported video files | Final renders written to user-chosen paths | Sarah Miller |
| A-4 | Code-signing certificate (PFX) | Used to sign `BeetleStudio.exe` and the installer | Sarah Miller |
| A-5 | User license key | Stored locally; ties install to entitlement | Maya Rodriguez |
| A-6 | Crash logs / telemetry | Optional opt-in; uploaded to backend | Mike Johnson |
| A-7 | Auto-update channel | Signed update packages fetched at startup | Mike Johnson |
| A-8 | OpenFX plugin DLLs | User-installed third-party plugins | Daniel Kim |
| A-9 | VST audio plugin DLLs | User-installed third-party audio plugins | Ryan Foster |
| A-10 | License-check endpoint response | Cloud response consumed at startup | Maya Rodriguez |
| A-11 | Crash-report endpoint | Cloud endpoint receiving crash telemetry | Mike Johnson |
| A-12 | Installer (`BeetleStudio-Setup-vX.Y.Z.exe`) | Inno Setup installer; runs as Administrator | Sarah Miller |

## Threat Actors

| ID | Actor | Motivation | Capability | Likely targets |
|---|---|---|---|---|
| TA-1 | Casual reverser | Curiosity, "I want the Pro features for free" | Static analysis, public unpackers, basic patching | A-5 (license), A-4 (signing), A-3 (DRM-free output) |
| TA-2 | Malware author | Distribution of malware via repackaged apps | Sophisticated packers, code-signing theft, supply-chain attacks | A-12 (installer), A-7 (update), A-8/A-9 (plugin DLLs) |
| TA-3 | Plugin developer (malicious) | Steal user data, persist on system, abuse elevated plugin load | Can author a plugin; relies on user installing it | A-1 (project files), A-6 (crash logs that may contain paths), filesystem, network |
| TA-4 | Insider threat (employee) | IP theft, sabotage | Source-tree access, signing cert access | A-4, A-1, A-7 |
| TA-5 | Nation-state | Targeted user surveillance (a journalist using Beetle Studio) | 0-day exploits, supply-chain compromise, MITM of update channel | A-7, A-1, A-3 |
| TA-6 | Script kiddie (DDoS) | Fun / lulz | L7 DDoS tools | A-10, A-11 (the cloud endpoints) |

## STRIDE Mapping (per asset)

| Asset | S | T | R | I | D | E | Notes |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| A-1 project files | – | ✓ | – | ✓ | – | – | An attacker with disk access can read or tamper with project files. Mitigation: optional encryption (planned). |
| A-2 preview cache | – | ✓ | – | ✓ | – | – | Cache is a perf optimization, not a security boundary. |
| A-3 exported video | – | ✓ | – | – | – | – | Watermarking (planned) is the only post-export tamper signal. |
| A-4 code-signing cert | ✓ | ✓ | – | – | – | ✓ | A stolen PFX is catastrophic. See [CODE_SIGNING_CERTIFICATE_MANAGEMENT.md](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md). |
| A-5 license key | ✓ | ✓ | – | ✓ | – | ✓ | License-check response is consumed; local key check must be tamper-resistant. |
| A-6 crash logs | – | – | – | ✓ | – | – | Path-leak risk; opt-in only. |
| A-7 auto-update | ✓ | ✓ | ✓ | – | ✓ | ✓ | The auto-update channel is the highest-impact supply-chain attack surface. Must be signed and pinned. |
| A-8 / A-9 plugins (OpenFX / VST) | ✓ | ✓ | – | ✓ | ✓ | ✓ | A malicious plugin runs in-process. See [OPENFX_PLUGIN_GUIDE.md](../OPENFX_PLUGIN_GUIDE.md) and [VST_SDK_INTEGRATION.md](../audio/VST_SDK_INTEGRATION.md) for sandboxing plans. |
| A-10 license-check | ✓ | – | – | – | ✓ | – | MITM and DDoS. |
| A-11 crash-report | ✓ | – | – | – | ✓ | – | Same as A-10. |
| A-12 installer | ✓ | ✓ | – | – | – | ✓ | Repackaging + code-signing theft. |

## Existing Controls (selected)

| Control | Where | What it covers |
|---|---|---|
| Code signing (Authenticode) | A-12, A-7 | Authenticity of installer and update packages |
| HTTPS for all cloud calls | A-10, A-11 | MITM protection |
| Gitleaks secret scan | Source | A-4, A-5 secrets not in repo |
| Semgrep SAST | Source | Common CWEs (C/C++ rules) |
| Branch protection | main, develop | A-4 (signing cert) is not in repo; branch protection covers source |
| Forgejo Actions self-hosted runner | Build | A-12, A-7 build integrity (assumes runner is trusted) |
| User opt-in for telemetry | A-6 | Privacy by choice |
| Plugin digital signature verification (planned) | A-8, A-9 | Authenticity of plugin DLLs (not yet implemented) |
| Process-level sandbox for plugins (planned) | A-8, A-9 | Limit damage of malicious plugin (not yet implemented) |

## Gaps (input to backlog)

| ID | Gap | Priority | Suggested owner |
|---|---|---|---|
| G-1 | Plugin DLLs run in-process with no signature check or sandbox | High | Daniel Kim (OpenFX), Ryan Foster (VST) |
| G-2 | Auto-update packages are not yet pinned to a specific build of Beetle Studio | High | Mike Johnson |
| G-3 | No SBOM / SCA in CI | Medium | Mike Johnson, Maya Rodriguez |
| G-4 | Project files are not encrypted at rest | Medium | Maya Rodriguez, Sarah Miller |
| G-5 | Crash logs may include absolute paths from the user's filesystem | Low | Mike Johnson (scrubber) |
| G-6 | No fuzzing of project-file parser | Medium | Lisa Martinez (QA), Daniel Kim |
| G-7 | License-check response not pinned / not signed | Medium | Maya Rodriguez |
| G-8 | No anti-debug / anti-tamper on the binary | Low (acknowledged trade-off) | Kirk Beka |

## Review Cadence

This document is reviewed **quarterly** by Maya Rodriguez + Kirk Beka, and re-issued when:

- A new asset is added (new cloud endpoint, new file format, new plugin type)
- A new STRIDE category becomes relevant
- A security incident occurs
- A major release ships

## References

### Internal Documents

- [Security Policy](../SECURITY_POLICY.md)
- [Security Waivers](../security/WAIVERS.md)
- [Vulnerability Disclosure (planned)](../security/VULNERABILITY_DISCLOSURE.md)
- [Incident Response (planned)](../operations/INCIDENT_RESPONSE.md)
- [OpenFX Plugin Guide](../OPENFX_PLUGIN_GUIDE.md)
- [VST SDK Integration](../audio/VST_SDK_INTEGRATION.md)
- [Code Signing Certificate Management](../releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)
- [Backend API Contract](../backend/API_CONTRACT.md)
- [Dependency Management (planned)](../engineering/DEPENDENCY_MANAGEMENT.md)

### External

- STRIDE — https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats
- OWASP ASVS 4.0.3 — https://owasp.org/www-project-application-security-verification-standard/
- OWASP Threat Modeling Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html
- NIST SP 800-154 (Guide to Data-Centric System Threat Modeling) — https://csrc.nist.gov/publications/detail/sp/800-154/draft
- ISO/IEC 27001:2022 A.5.7 — Threat intelligence
- ISO/IEC 27002:2022 A.5.7

---

*Grounded in: ISO/IEC 27001:2022 A.5.7 (Threat intelligence), ISO/IEC 27002:2022 A.5.7, OWASP ASVS 4.0.3. Asset list derived from the module map at `docs/architecture/MODULE_MAP.md`.*
