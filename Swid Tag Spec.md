> Auto-generated from `releases/SWID_TAG_SPEC.md` in the docs repo.

> Auto-generated from `docs/releases/SWID_TAG_SPEC.md` in the docs repo.

---
title: "SWID Tag Specification"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# SWID Tag Specification

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer)  
**Reviewers:** Kirk Beka (CTO), Maya Rodriguez (Backend)  
**ISO Standards:** ISO/IEC 19770-2:2015 (Software Identification Tag)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | ISO/IEC 19770-2 SWID tag implementation for Beetle Studio |
| **Diátaxis form** | Reference |
| **Primary audience** | Sarah Miller, Kirk Beka, Maya Rodriguez, enterprise IT customers |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

Per **ISO/IEC 19770-2:2015**, software products should carry a Software Identification (SWID) tag to enable enterprise IT asset management tools (SCCM, Intune, LANDESK, ServiceNow) to correctly identify, track, and manage Beetle Studio on managed devices.
## Contents

- [SWID Tag Format](#swid-tag-format)
  - [Example Tag (installed Beetle Studio v2.3.0)](#example-tag-installed-beetle-studio-v230)
  - [File Naming](#file-naming)
- [Tag Fields Reference](#tag-fields-reference)
  - [Required Fields (ISO/IEC 19770-2:2015 §6.2)](#required-fields-isoiec-19770-22015-62)
  - [Optional but Recommended Fields](#optional-but-recommended-fields)
- [Windows Registration](#windows-registration)
  - [Registry Path](#registry-path)
  - [Enterprise Discovery](#enterprise-discovery)
- [Version-Specific Tags](#version-specific-tags)
- [Installer Integration](#installer-integration)
  - [Inno Setup Integration](#inno-setup-integration)
  - [Auto-Generation in CI](#auto-generation-in-ci)
- [Compliance Checklist](#compliance-checklist)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## SWID Tag Format

We use the **Corpus SWID tag** format (for installed software), per ISO/IEC 19770-2:2015 §5.3.

### Example Tag (installed Beetle Studio v2.3.0)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<SoftwareIdentificationTag
  xmlns="http://standards.iso.org/iso/19770/-2/2015/schema"
  schemaVersion="2.0">

  <ProductID>beetle-studio-2.3.0</ProductID>
  <ProductName>Beetle Studio</ProductName>
  <ProductVersion>
    <VersionScheme>alphanumeric</VersionScheme>
    <Version>2.3.0</Version>
  </ProductVersion>
  <SoftwareCreator>
    <Name>Mooned Dev</Name>
    <Regid>regid.mooned.dev</Regid>
  </SoftwareCreator>
  <LicensePrivacyURL>https://www.mooned.dev/privacy</LicensePrivacyURL>
  <Summary>Professional video editing software</Summary>
  <Description>Beetle Studio is a professional-grade video editor with GPU-accelerated rendering, multi-track timeline, and FFmpeg-based codec support.</Description>

</SoftwareIdentificationTag>
```

### File Naming

| Tag Type | Filename | Location |
|---|---|---|
| **Corpus tag** (installer) | `BeetleStudio_2.3.0.swidtag` | Bundled in installer payload |
| **Installed tag** (post-install) | `BeetleStudio_2.3.0.swidtag` | `%ProgramData%\Mooned Dev\Beetle Studio\` |

---

## Tag Fields Reference

### Required Fields (ISO/IEC 19770-2:2015 §6.2)

| Field | Value for Beetle Studio | Notes |
|---|---|---|
| `schemaVersion` | `2.0` | ISO/IEC 19770-2:2015 schema |
| `ProductID` | `beetle-studio-{MAJOR}.{MINOR}.{PATCH}` | Unique per version |
| `ProductName` | `Beetle Studio` | Display name |
| `Version` | `{MAJOR}.{MINOR}.{PATCH}` | Must match SemVer exactly |
| `VersionScheme` | `alphanumeric` | Matches SemVer format |
| `Name` (SoftwareCreator) | `Mooned Dev` | Legal entity name |
| `Regid` (SoftwareCreator) | `regid.mooned.dev` | Reverse domain identifier |

### Optional but Recommended Fields

| Field | Value | Notes |
|---|---|---|
| `LicensePrivacyURL` | `https://www.mooned.dev/privacy` | Links to privacy policy |
| `Summary` | Short product description | One line |
| `Description` | Full description | One paragraph |
| `ProductSuite` | Not used | Reserved for product families |
| `TagCreator` | Same as SoftwareCreator | Self-signed tag |

---

## Windows Registration

During installation, the SWID tag must be registered with Windows via the `swiupdate` service or directly to the registry:

### Registry Path

```
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{ProductID}
```

Or using the SWID directory (preferred):

```
%ProgramData%\Mooned Dev\Beetle Studio\*.swidtag
```

### Enterprise Discovery

Enterprise IT tools discover SWID tags in this order:
1. `%ProgramData%\swidtag\<regid>\*.swidtag`
2. `%ProgramFiles%\Mooned Dev\Beetle Studio\*.swidtag`
3. Windows Registry Uninstall key

---

## Version-Specific Tags

Each Beetle Studio version gets a new SWID tag. Old tags must NOT be deleted on upgrade — each installed version should be individually trackable:

| Installed Version | SWID Tag Filename | Tag Version Field |
|---|---|---|
| 2.2.0 | `BeetleStudio_2.2.0.swidtag` | `2.2.0` |
| 2.3.0 | `BeetleStudio_2.3.0.swidtag` | `2.3.0` |
| 2.3.2 | `BeetleStudio_2.3.2.swidtag` | `2.3.2` |

When upgrading, install the new tag alongside the old one. When uninstalling, remove the uninstalled version's tag only (not all version tags).

---

## Installer Integration

### Inno Setup Integration

The SWID tag file is bundled in the installer payload:

```iss
[Files]
Source: "BeetleStudio_{#Version}.swidtag"; DestDir: "{app}"; Flags: ignoreversion
Source: "BeetleStudio_{#Version}.swidtag"; DestDir: "{commonappdata}\Mooned Dev\Beetle Studio"; Flags: ignoreversion
```

### Auto-Generation in CI

Sarah Miller's CI pipeline generates the SWID tag file dynamically using the version number from the git tag:

```python
# scripts/generate_swid_tag.py (called in CI before installer build)
import xml.etree.ElementTree as ET

def generate_swid_tag(version: str) -> str:
    tag = ET.Element("SoftwareIdentificationTag", xmlns="http://standards.iso.org/iso/19770/-2/2015/schema")
    tag.set("schemaVersion", "2.0")
    # ... populate fields
    return ET.tostring(tag, encoding="unicode")
```

---

## Compliance Checklist

- [ ] SWID tag generated for every release (including hotfixes)
- [ ] `ProductID` uniquely identifies each version
- [ ] `Version` field matches SemVer exactly
- [ ] `Regid` uses `regid.mooned.dev` format
- [ ] Tag bundled in installer payload
- [ ] Tag registered to `%ProgramData%\swidtag\regid.mooned.dev\`
- [ ] Tag discoverable by SCCM/Intune (validate with IT test environment)
- [ ] Store submission includes SWID data in package manifest

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — fully aligned with ISO/IEC 19770-2:2015 |

---

*Grounded in: ISO/IEC 19770-2:2015 — Information technology — IT asset management — Part 2: Software identification tag*



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

- **Next review:** On ISO/IEC 19770 revision
- **Reviewer:** Sarah Miller (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type