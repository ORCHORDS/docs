> Auto-generated from `Code Signing Certificate Management.md` in the docs repo.

> Auto-generated from `Code Signing Certificate Management.md` in the docs repo.

> Auto-generated from `releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md` in the docs repo.

> Auto-generated from `docs/releases/CODE_SIGNING_CERTIFICATE_MANAGEMENT.md` in the docs repo.

---
title: "Code Signing & Certificate Management"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Code Signing & Certificate Management

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer)  
**Reviewers:** Kirk Beka (CTO), Maya Rodriguez (Backend — for API signing)  
**ISO Standards:** ISO/IEC 27001:2022 Annex A (cryptographic controls), ISO/IEC 19770-2:2015 (software identification), ISO/IEC 12207:2017 (transition security)  
**Version:** 1.0.0  
**Last Updated:** 2026-06-21

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Certificate lifecycle, signing pipeline, and Azure Artifact Signing integration |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Kirk Beka, Maya Rodriguez |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

All executable code shipped by Mooned Dev -- installers, DLLs, executables, and cloud functions -- must be signed. Per **ISO/IEC 27001:2022 Annex A**, cryptographic controls are required for protecting software integrity. Code signing is our primary integrity control. We use **Azure Artifact Signing** for all Windows binaries.
## Contents

- [What Must Be Signed](#what-must-be-signed)
- [Certificate Types & Lifecycle](#certificate-types-lifecycle)
  - [Windows Code Signing Certificate](#windows-code-signing-certificate)
  - [Certificate Renewal Calendar](#certificate-renewal-calendar)
- [Signing Process](#signing-process)
  - [Build Pipeline Integration (Forgejo Actions, GitHub Actions–compatible)](#build-pipeline-integration-github-actions)
  - [Manual Signing (Emergency)](#manual-signing-emergency)
  - [Firebase Cloud Function Signing](#firebase-cloud-function-signing)
- [Verification](#verification)
  - [SmartScreen Check](#smartscreen-check)
- [Certificate Storage & Access](#certificate-storage-access)
  - [Secrets Rotation](#secrets-rotation)
- [Revocation Procedure](#revocation-procedure)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## What Must Be Signed

| Artifact | Required | Notes |
|---|---|---|
| `BeetleStudio.exe` (main executable) | ✅ Mandatory | Core application |
| `BeetleStudio.dll` and all plugin DLLs | ✅ Mandatory | Plugin SDK requires signed host |
| `BeetleStudioSetup.exe` (Inno Setup installer) | ✅ Mandatory | SmartScreen reputation |
| `BeetleStudio.msix` (Store package) | ✅ Mandatory | Store certification |
| FFmpeg-related DLLs (static build) | ✅ Mandatory | Distributing LGPL components |
| Cloud Functions (Firebase) | ✅ Mandatory | API integrity |
| VST3 plugin stubs | ✅ Recommended | Plugin host trust |

---

## Certificate Types & Lifecycle

### Windows Code Signing Certificate

| Property | Value |
|---|---|
| **Provider** | Azure Artifact Signing (certificate managed by Microsoft) |
| **Key vault** | Azure Key Vault (Moonsign-mvs subscription) |
| **Certificate type** | EV (Extended Validation) Code Signing |
| **Algorithm** | SHA-256 with RSA 4096-bit key |
| **Validity period** | 3 years (monitor at 1 year remaining) |
| **Key rotation** | Automatically handled by Azure Artifact Signing |
| **Emergency re-key** | Contact Azure support + Kirk Beka approval |

### Certificate Renewal Calendar

| Certificate | Expiry | Renewal Deadline | Owner |
|---|---|---|---|
| Windows Code Signing | June 2027 | April 2027 | Sarah Miller |

---

## Signing Process

### Build Pipeline Integration (Forgejo Actions, GitHub Actions–compatible)

```yaml
# Simplified Forgejo Actions signing step (GitHub Actions–compatible syntax)
- name: Sign executables
  uses: azure/code-signing-action@v1
  with:
    azure-tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    azure-client-id: ${{ secrets.AZURE_CLIENT_ID }}
    azure-client-secret: ${{ secrets.AZURE_CLIENT_SECRET }}
    certificate-name: ${{ secrets.AZ_CERT_NAME }}
    files: |
      ./publish/*.exe
      ./publish/*.dll
      ./publish/BeetleStudioSetup.exe
```

### Manual Signing (Emergency)

```powershell
# Sign a single file manually
az signing certificate sign `
  --file "BeetleStudioSetup.exe" `
  --output "BeetleStudioSetup_signed.exe" `
  --certificate-name "BeetleStudio-CodeSign-2026"

# Verify signature
signtool verify /pa /v BeetleStudioSetup_signed.exe
```

### Firebase Cloud Function Signing

Firebase Cloud Functions are signed automatically by Google. Ensure the Firebase project is under the Mooned Dev organization account with correct IAM permissions.

---

## Verification

After signing, always verify:

```powershell
# Basic Windows verification
signtool verify /pa /v BeetleStudioSetup.exe

# Full certificate chain verification
signtool verify /pa /v /c BeetleStudioSetup.cert BeetleStudioSetup.exe

# Output should show:
# "Successfully verified: BeetleStudioSetup.exe"
# "Certificate chain valid"
```

### SmartScreen Check

SmartScreen reputation builds over time with consistent signing. To check:

- **New certificate:** Users may see "Windows protected your PC" warning
- **Reputation established:** Warning disappears after ~1,000 downloads/installations
- **Enterprise environments:** IT admins can whitelist via policy

---

## Certificate Storage & Access

Per **ISO/IEC 27001:2022 Annex A**, cryptographic keys must be protected:

| Requirement | Implementation |
|---|---|
| **Key storage** | Azure Key Vault — hardware security module (HSM) backed |
| **Access control** | RBAC — only Sarah Miller and Kirk Beka have signing permissions |
| **CI/CD access** | Forgejo Actions OIDC token (per the `enable-openid-connect` key — see Forgejo docs) — no static secrets stored |
| **Audit log** | Azure Key Vault logs all access (90-day retention) |
| **Emergency access** | Kirk Beka holds backup access; Mooned Dev as ultimate owner |

### Secrets Rotation

| Secret | Rotation Frequency | Method |
|---|---|---|
| Azure Client ID / Secret | 90 days | Manual via Azure portal |
| GitHub OIDC (auto-rotated) | Ongoing | No manual action needed |
| Firebase admin key | 180 days | Via Firebase console |

---

## Revocation Procedure

If a private key is compromised (suspected or confirmed):

1. **Immediate:** Notify Kirk Beka and Mooned Dev
2. **Revoke certificate:** File revocation request with Azure Artifact Signing
3. **Notify Microsoft:** Submit to Microsoft Code Signing revocation list
4. **Rebuild and resign:** Regenerate all affected artifacts from source
5. **Push emergency update:** Expedited Store submission if Store app is affected
6. **Post-incident review:** Document root cause; update this procedure

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 27001:2022 Annex A cryptographic controls |

---

*Grounded in: ISO/IEC 27001:2022 Annex A (Cryptographic Controls), ISO/IEC 19770-2:2015, ISO/IEC 12207:2017 §6.4*



---

## References

### Internal Documents

_No internal documents referenced._

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Sarah Miller | Initial version |
| 1.0.1 | June 2026 | Sarah Miller | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On certificate renewal (annual)
- **Reviewer:** Sarah Miller (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type