# Installer Specification

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer)  
**Reviewers:** Mike Johnson (DevOps), Kirk Beka (CTO)  
**ISO Standards:** ISO/IEC 12207:2017 (installation as part of transition), ISO/IEC 19770-2:2015 (SWID tags), ISO/IEC 25010:2023 (usability, installability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Installer requirements for all distribution channels |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Mike Johnson, Kirk Beka |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document specifies the installer requirements for Beetle Studio. Per **ISO/IEC 12207:2017**, installation (transition into operational use) must be planned, documented, and executed in a controlled manner. The installer is the delivery vehicle for that transition. We use **Inno Setup** for Windows x64 builds.
## Contents

- [Installer Requirements](#installer-requirements)
  - [Functional Requirements](#functional-requirements)
  - [Components Bundled](#components-bundled)
  - [Per-User Installation](#per-user-installation)
  - [Per-Machine Installation (Admin)](#per-machine-installation-admin)
- [Component Selection](#component-selection)
- [Upgrade Behavior](#upgrade-behavior)
- [Uninstaller Behavior](#uninstaller-behavior)
- [Silent Install Configuration](#silent-install-configuration)
  - [Direct Download Installer](#direct-download-installer)
  - [Enterprise Deployment (SCCM/Intune)](#enterprise-deployment-sccmintune)
- [Installer Metadata](#installer-metadata)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Installer Requirements

### Functional Requirements

| Requirement | Detail |
|---|---|
| **Default install path** | `C:\Program Files\Mooned Dev\Beetle Studio` |
| **Custom install path** | User-selectable; must persist across updates |
| **Minimum disk space** | 2 GB (application) + 500 MB (working temp) |
| **Recommended disk space** | 10 GB (for project cache and media scratch) |
| **Admin rights** | Optional — install to user folder without admin |
| **Silent install** | Supported via `/SILENT` or `/VERYSILENT` flags |
| **Unattended install** | Supported via `/SUPPRESSMSGBOXES` combined with silent flags |

### Components Bundled

| Component | Required | Notes |
|---|---|---|
| Beetle Studio executable | ✅ | Code-signed |
| FFmpeg runtime (static build) | ✅ | LGPL licensed |
| Qt6 runtime libraries | ✅ | LGPL licensed |
| GPU shader cache | ✅ | Created at first run |
| Sample project templates | ✅ | Default templates, ~100 MB |
| License and attribution files | ✅ | FFmpeg, Qt6, third-party libs |
| Uninstaller | ✅ | Full cleanup including cache |
| SWID tag file | ✅ | See [`SWID_TAG_SPEC.md`](./SWID_TAG_SPEC.md) |
| Crash handler | ✅ | Sends crash reports with user consent |

### Per-User Installation

Support non-admin install to `%LOCALAPPDATA%\Programs\Beetle Studio`:

| Item | Detail |
|---|---|
| **Install path** | `%LOCALAPPDATA%\Programs\Beetle Studio\<version>` |
| **Uninstaller path** | `%APPDATA%\Mooned Dev\Beetle Studio\uninstall.exe` |
| **Settings** | `%APPDATA%\Mooned Dev\Beetle Studio\config\` |
| **Cache** | `%LOCALAPPDATA%\Mooned Dev\Beetle Studio\cache\` |
| **Logs** | `%LOCALAPPDATA%\Mooned Dev\Beetle Studio\logs\` |

### Per-Machine Installation (Admin)

| Item | Detail |
|---|---|
| **Install path** | `%ProgramFiles%\Mooned Dev\Beetle Studio` |
| **Uninstaller path** | `%ProgramData%\Mooned Dev\Beetle Studio\uninstall.exe` |
| **Settings** | `%ProgramData%\Mooned Dev\Beetle Studio\config\` |
| **Cache** | `%ProgramData%\Mooned Dev\Beetle Studio\cache\` |
| **Logs** | `%ProgramData%\Mooned Dev\Beetle Studio\logs\` |

---

## Component Selection

Users can choose which components to install:

| Component | Default | Size |
|---|---|---|
| Core application | Always | ~300 MB |
| Sample templates | Optional | ~100 MB |
| Additional language packs | Optional | ~50 MB each |
| Shader cache (pre-baked) | Optional | ~200 MB |

---

## Upgrade Behavior

| Scenario | Behavior |
|---|---|
| **Same MAJOR version** (e.g., 2.3.0 → 2.4.0) | In-place upgrade; preserve settings and cache |
| **MAJOR version change** (e.g., 2.x → 3.0) | Offer to migrate settings; fresh cache |
| **Downgrade** | Not supported; warn user and abort |
| **Corrupt installation detected** | Offer repair or clean reinstall |

---

## Uninstaller Behavior

Full cleanup on uninstall:

- [ ] Remove all installed files in install directory
- [ ] Remove settings directory (with user consent)
- [ ] Remove cache directory (with user consent)
- [ ] Remove SWID tag registration
- [ ] Remove Windows Add/Remove Programs entry
- [ ] Remove desktop and Start Menu shortcuts
- [ ] Remove file associations (with user consent)
- [ ] Remove shell preview handler (if installed)

---

## Silent Install Configuration

### Direct Download Installer

```powershell
# Silent install (user sees progress bar)
BeetleStudioSetup.exe /SILENT

# Very silent (no UI at all)
BeetleStudioSetup.exe /VERYSILENT

# Silent with custom path
BeetleStudioSetup.exe /VERYSILENT /DIR="D:\Apps\BeetleStudio"
```

### Enterprise Deployment (SCCM/Intune)

```powershell
# Detect installed version
$installed = Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BeetleStudio"

# Install/upgrade
BeetleStudioSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="C:\Program Files\Mooned Dev\Beetle Studio"
```

---

## Installer Metadata

| Field | Value |
|---|---|
| **Publisher** | Mooned Dev |
| **DisplayName** | Beetle Studio |
| **DisplayVersion** | MAJOR.MINOR.PATCH (e.g., `2.3.1`) |
| **PublisherURL** | https://www.mooned.dev |
| **SupportURL** | https://www.mooned.dev/support |
| **InstallSource** | Set by installer to track source |
| **UninstallString** | `"{uninstall_exe}" /VERYSILENT` |
| **NoModify** | 1 (not modifiable via Add/Remove Programs) |
| **NoRepair** | 0 (repair is supported) |
| **EstimatedSize** | Installer-computed in KB |
| **Language** | 1033 (English); additional per locale |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 transition and ISO/IEC 25010:2023 installability |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Transition Process), ISO/IEC 19770-2:2015, ISO/IEC 25010:2023 (Installability sub-characteristic)*


---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Unknown owner | Initial version |
| 1.0.1 | June 2026 | Unknown owner | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On installer framework change
- **Reviewer:** Sarah Miller (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type