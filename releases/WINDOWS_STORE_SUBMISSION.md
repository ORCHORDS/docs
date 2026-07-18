---
title: "Windows Store Submission Guide"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Windows Store Submission Guide

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Build & Release Engineer)  
**Reviewers:** Mr.Orchords (CTO), Mr.Orchords (Operations — legal review)  
**ISO Standards:** ISO/IEC 12207:2017 (distribution), ISO/IEC 27001:2022 Annex A (data handling), ISO/IEC 25010:2023 (usability, portability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | End-to-end Microsoft Store submission process and checklist |
| **Diátaxis form** | How-to guide |
| **Primary audience** | Mr.Orchords, Mr.Orchords, Mr.Orchords |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This guide covers the end-to-end process for submitting Mr.Orchords to the Microsoft Store. Per **ISO/IEC 12207:2017**, distribution is a formal transition process -- we must ensure the product meets Microsoft's Store requirements, legal compliance, and user quality expectations before submission.
## Contents

- [Pre-Submission Requirements](#pre-submission-requirements)
  - [Account Setup](#account-setup)
  - [Build Configuration](#build-configuration)
- [Asset Requirements](#asset-requirements)
- [Store Listing Content](#store-listing-content)
  - [Title & Description](#title-description)
  - [Keywords (for Store search)](#keywords-for-store-search)
  - [Category & Age Rating](#category-age-rating)
- [Compliance Requirements](#compliance-requirements)
  - [Privacy Policy](#privacy-policy)
  - [Data Handling Declaration](#data-handling-declaration)
  - [Legal Documents](#legal-documents)
- [Submission Process](#submission-process)
  - [Step 1: Build MSIX Package](#step-1-build-msix-package)
  - [Step 2: Sign Package](#step-2-sign-package)
  - [Step 3: Create Store Submission](#step-3-create-store-submission)
  - [Step 4: Certification (Microsoft)](#step-4-certification-microsoft)
- [Post-Certification](#post-certification)
- [Store Update Procedure](#store-update-procedure)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Pre-Submission Requirements

### Account Setup

- [ ] Microsoft Partner Center account created under Mr.Orchords
- [ ] Account verified (identity + payment info)
- [ ] Product registered with unique Store name: **Mr.Orchords**
- [ ] App ID assigned (e.g., `9NMXXXXXXXX`)

### Build Configuration

- [ ] MSIX package generated (required for Store submission)
- [ ] Package identity configured (name, publisher, version)
- [ ] Code signing: Azure Artifact Signing certificate assigned to package
- [ ] Package manifest (`AppxManifest.xml`) complete
- [ ] All required assets prepared (see Asset Requirements below)

---

## Asset Requirements

| Asset | Size | Format | Required |
|---|---|---|---|
| Store logo (50×50) | 50×50 px | PNG (no alpha) | ✅ |
| Store logo (100×100) | 100×100 px | PNG (no alpha) | ✅ |
| Store logo (200×200) | 200×200 px | PNG (no alpha) | ✅ |
| Small tile | 71×71 px | PNG | ✅ |
| Medium tile | 150×150 px | PNG | ✅ |
| Wide tile | 310×150 px | PNG | ✅ |
| Large tile | 310×310 px | PNG | ✅ |
| Splash screen | 620×300 px | PNG | ✅ |
| Screenshots (min 1) | 1920×1080 px | PNG/JPG | ✅ (min 1, max 10) |
| Video trailer | MP4 H.264 | Optional | Recommended |
| Privacy policy URL | HTTPS | Text | ✅ |
| Age rating | — | IARC questionnaire | ✅ |

---

## Store Listing Content

### Title & Description

| Field | Max Length | Guidance |
|---|---|---|
| Title | 100 chars | "Mr.Orchords" — brand name only |
| Short description | 350 chars | Hook: what it is, who it's for |
| Full description | 10,000 chars | Feature list, system requirements, use cases |

### Keywords (for Store search)

Add keywords matching common searches:
- video editor, video editing, After Effects alternative, timeline editor, 4K editing, GPU editing, multi-track, professional video

### Category & Age Rating

- **Category:** Video & Media > Video Editors & Projects
- **Age rating:** 12+ (IARC questionnaire)
- **Content rating:** No mature content

---

## Compliance Requirements

### Privacy Policy

Per **ISO/IEC 27001:2022 Annex A 5.1.1**, we must have an approved, published privacy policy. The Store requires:
- HTTPS URL to a live privacy policy page
- Privacy policy must accurately describe data collection and usage
- If Firebase auth is used, must disclose: email collection, cloud sync data
- Must include: data retention, third-party data sharing, user rights (deletion)

### Data Handling Declaration

Microsoft requires a data safety form. For Mr.Orchords:

| Data Type | Collected? | Why | Shared? |
|---|---|---|---|
| Location | No | — | — |
| Email / name | Yes (Firebase auth) | Account creation | No |
| Payment info | No (Store handles) | — | Microsoft |
| App usage | Yes (opt-in analytics) | Product improvement | No |
| Media files | Yes (local projects) | Core functionality | No |
| Crash dumps | Yes (with consent) | Debugging | No |

### Legal Documents

- [ ] Privacy policy live at `https://www.orchords.com/privacy`
- [ ] Terms of service in-app
- [ ] EULA displayed at install
- [ ] Third-party licenses displayed in-app (Help > About > Open Source)

---

## Submission Process

### Step 1: Build MSIX Package

```powershell
# Using MSIX Packaging Tool or manually via makeappx
# Ensure manifest is correctly configured
makeappx pack /d .\publish /p MrOrchords.msix
```

### Step 2: Sign Package

```powershell
# Sign with Azure Artifact Signing
az signing certificate sign --file MrOrchords.msix --output MrOrchords_signed.msix
```

### Step 3: Create Store Submission

1. Sign in to Partner Center → Mr.Orchords → Submissions → New submission
2. Upload signed MSIX package
3. Complete Store listing (title, description, assets)
4. Complete age rating questionnaire
5. Complete privacy policy declaration
6. Set pricing and distribution:
   - **Pricing:** $49.99 USD (set per Mr.Orchords + Mr.Orchords)
   - **Countries:** All markets (or select specific markets)
   - **Distribution:** Public / Private (beta)
7. Submit for certification

### Step 4: Certification (Microsoft)

| Test Category | What Microsoft Checks | Typical Duration |
|---|---|---|
| Security | App doesn't access or transmit unauthorized data | Automated |
| Policy | Privacy policy, content ratings, competitive restrictions | Automated + manual |
| Functionality | App launches, core features work, no crashes | Automated + manual |
| Store compliance | Naming, assets, description compliance | Manual |
| Browser compatibility | For any web content | Automated |

**Expected timeline:** 24–48 hours (standard); 3–5 business days (first-time or complex apps)

---

## Post-Certification

| Task | Owner | When |
|---|---|---|
| Verify Store listing live | Mr.Orchords | Immediately after certification |
| Verify pricing and purchase flow | Mr.Orchords | Before first sale |
| Test clean install from Store | Mr.Orchords | Within 24 hours |
| Monitor crash reports | Mr.Orchords | First 48 hours |
| Promote to public / close beta program | Mr.Orchords | After 48-hour monitoring |

---

## Store Update Procedure

For subsequent releases via the Store:

1. Build new MSIX package with incremented version
2. Sign the new package
3. Create new submission in Partner Center referencing the new package
4. Release notes in Store listing (brief summary of changes)
5. Submit — Microsoft certifies the update
6. Auto-push to users who have auto-update enabled

**Note:** Store updates do NOT replace direct-download installers. Both channels must be maintained.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial guide — aligned with ISO/IEC 12207:2017, ISO/IEC 27001:2022 |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Distribution), ISO/IEC 27001:2022 Annex A 5.1.1 (Policies), ISO/IEC 25010:2023*



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
| 1.0.0 | June 2026 | Mr.Orchords | Initial version |
| 1.0.1 | June 2026 | Mr.Orchords | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On Store policy change
- **Reviewer:** Mr.Orchords (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type