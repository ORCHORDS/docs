---
title: "Code Signing & Certificate Management"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Code Signing & Certificate Management

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Build & Release Engineer)  
**Reviewers:** Mr.Orchords (CTO), Mr.Orchords (DevOps)  
**ISO Standards:** ISO/IEC 27001:2022 (Annex A: Cryptographic Controls), ISO/IEC 12207:2017 (transition)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Certificate lifecycle, signing infrastructure, and SmartScreen reputation |
| **Diátaxis form** | Reference |
| **Primary audience** | Mr.Orchords, Mr.Orchords, Mr.Orchords |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines Mr.Orchords's code signing and certificate management practices. Per **ISO/IEC 27001:2022 Annex A**, cryptographic controls protect the integrity of information. Code signing proves that Mr.Orchords releases are authentic and untampered.
## Contents

- [Why Code Signing Matters](#why-code-signing-matters)
- [Our Signing Strategy](#our-signing-strategy)
  - [What Gets Signed](#what-gets-signed)
  - [Certificate Standards](#certificate-standards)
- [Signing Infrastructure](#signing-infrastructure)
  - [Azure Artifact Signing (Cloud)](#azure-artifact-signing-cloud)
  - [Manual Signing (Fallback)](#manual-signing-fallback)
- [Certificate Lifecycle](#certificate-lifecycle)
  - [Acquisition](#acquisition)
  - [Storage](#storage)
  - [Renewal](#renewal)
  - [Revocation](#revocation)
- [SmartScreen Reputation](#smartscreen-reputation)
  - [How Reputation Works](#how-reputation-works)
  - [Building Reputation Faster](#building-reputation-faster)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Why Code Signing Matters

| Benefit | How It Helps |
|---|---|
| **Authenticity** | Users verify the software came from Mr.Orchords |
| **Integrity** | Detects tampering or corruption after signing |
| **SmartScreen reputation** | Signed software passes Windows SmartScreen faster |
| **Windows Store requirement** | Microsoft requires code signing for Store submissions |
| **Enterprise distribution** | Signed code is required by corporate IT policies |

---

## Our Signing Strategy

### What Gets Signed

| Artifact | Signed? | Method |
|---|---|---|
| `MrOrchords.exe` | ✅ | Azure Artifact Signing |
| `MrOrchordsEngine.dll` | ✅ | Azure Artifact Signing |
| `MrOrchordsSetup.exe` (installer) | ✅ | Azure Artifact Signing |
| `MrOrchordsUpdate.exe` (updater) | ✅ | Azure Artifact Signing |
| Third-party `.dll`s shipped with installer | ❌ | Third-party vendors sign their own |
| OpenFX plugins | ⚠️ | Third-party developers sign their own |
| `MrOrchordsSetup_signed.exe` | ✅ | Installer signed after compilation |

### Certificate Standards

- **Algorithm:** RSA-4096 with SHA-384
- **Storage:** Azure Key Vault (HSM-backed) or physical USB token (for EV certificates)
- **Chain:** Full certificate chain included in signature
- **Timestamp:** DigiCert timestamp server (required)

---

## Signing Infrastructure

### Azure Artifact Signing (Cloud)

Primary signing method for releases:

```yaml
# Forgejo Actions release workflow (GitHub Actions–compatible syntax)
- name: Sign executables
  uses: azure/code-signing-action@v1
  with:
    azure-keyvault-uri: ${{ secrets.AZURE_KEYVAULT_URI }}
    certificate-name: ${{ secrets.CODE_SIGNING_CERT_NAME }}
    files-to-sign: |
      MrOrchords.exe
      MrOrchordsEngine.dll
      MrOrchordsSetup.exe
```

### Manual Signing (Fallback)

If cloud signing is unavailable, Mr.Orchords can sign manually:

1. Export certificate from Azure Key Vault to a secure USB token
2. Sign locally using `signtool.exe`:
   ```powershell
   signtool sign /fd SHA384 /a /tr http://timestamp.digicert.com /td SHA384 MrOrchords.exe
   ```
3. Verify: `signtool verify /pa MrOrchords.exe`

---

## Certificate Lifecycle

### Acquisition

| Step | Owner | Notes |
|---|---|---|
| Generate CSR | Mr.Orchords | From Azure Key Vault or token |
| Submit to CA | Mr.Orchords | DigiCert or Sectigo |
| Complete identity verification | Mr.Orchords | CA verifies Mr.Orchords legal entity |
| Certificate issued | CA | Sent to Azure Key Vault |
| Test signing | Mr.Orchords | Verify signature before production use |

### Storage

- **Never** store certificate files in Git repositories
- **Never** email certificate files
- Store only in Azure Key Vault with restricted access policies
- Access logged and audited quarterly
- Key rotation policy: new certificate every 2 years

### Renewal

- Renew at least **60 days** before expiry
- Test new certificate on a non-release build first
- Update Forgejo Actions secrets with new certificate name
- Document renewal date in this file

### Revocation

If a certificate is compromised:

1. **Immediately revoke** at the CA
2. **Re-sign all affected releases** with a new certificate
3. **Notify users** if the compromised certificate was used for a release
4. **File incident report** (see [`engineering/BACKUP_DISASTER_RECOVERY.md`](../engineering/BACKUP_DISASTER_RECOVERY.md))

---

## SmartScreen Reputation

### How Reputation Works

- **New certificates start with zero reputation** — SmartScreen shows warnings to users
- Reputation builds as more users install and run the signed software
- **~1,000–5,000 installs** needed before SmartScreen trusts the certificate

### Building Reputation Faster

| Method | Effort | Timeline |
|---|---|---|
| Publish to Microsoft Store | Low | Reputation transfers from Store |
| Sign installers + executables | Low | Required anyway |
| Consistent signing over time | Low | Builds naturally |
| Beta program (signed builds) | Medium | Beta users build reputation |

---

## Verification

Every signed artifact must be verified before release:

```powershell
# Verify the signature
signtool verify /pa MrOrchordsSetup.exe

# Check certificate details
Get-AuthenticodeSignature MrOrchordsSetup.exe | Format-List

# Expected output:
# Status: Valid
# SignerCertificate: CN=Mr.Orchords CodeSign 2026, O=Mr.Orchords, ...
# TimeStamperCertificate: CN=DigiCert Timestamp 2026, ...
```

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `signtool` error 0x8007000D | Invalid certificate file | Re-export from Key Vault |
| SmartScreen still warning | New certificate reputation | Wait; publish via Store; collect installs |
| Certificate expired | Not renewed in time | Re-issue + re-sign all releases |
| Timestamp server unreachable | DigiCert downtime | Use alternate: `http://timestamp.sectigo.com` |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 27001:2022 Annex A and ISO/IEC 12207:2017 |

---

*Grounded in: ISO/IEC 27001:2022 Annex A (Cryptographic Controls), ISO/IEC 12207:2017 §6.4 (Transition)*



---

## References

### Internal Documents

- [$title](./../engineering/BACKUP_DISASTER_RECOVERY.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mr.Orchords | Initial version |
| 1.0.1 | June 2026 | Mr.Orchords | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On certificate expiry
- **Reviewer:** Mr.Orchords (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type