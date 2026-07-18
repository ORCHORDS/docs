---
title: "SWID Tag Specification"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# SWID Tag Specification

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Build & Release Engineer)  
**Reviewers:** Mr.Orchords (CTO), Mr.Orchords (DevOps)  
**ISO Standards:** ISO/IEC 19770-2:2015 (software identification tags), ISO/IEC 12207:2017 (transition)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | ISO/IEC 19770-2 SWID tag structure and generation |
| **Diátaxis form** | Reference |
| **Primary audience** | Mr.Orchords, Mr.Orchords, enterprise IT administrators |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines the Software Identification (SWID) tag for Mr.Orchords. Per **ISO/IEC 19770-2:2015**, SWID tags provide authoritative identification of software products for IT asset management (ITAM) systems. Enterprise customers use SWID tags to track software inventory, license compliance, and patch management.
## Contents

- [What Is a SWID Tag?](#what-is-a-swid-tag)
- [SWID Tag Structure](#swid-tag-structure)
  - [Required Elements](#required-elements)
  - [Optional Elements](#optional-elements)
- [SWID Tag Schema](#swid-tag-schema)
  - [Tag ID](#tag-id)
  - [Entity](#entity)
  - [Link](#link)
  - [Meta](#meta)
  - [Payload](#payload)
  - [Evidence](#evidence)
- [Example Tag: Installed Mr.Orchords v2.3.0](#example-tag-installed-mrorchords-v230)
- [Validation Rules](#validation-rules)
  - [Schema Validation](#schema-validation)
  - [Required Value Rules](#required-value-rules)
- [Generation](#generation)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## What Is a SWID Tag?

A SWID tag is an XML file that identifies a software product. When Mr.Orchords is installed, the SWID tag:
- Identifies the product (name, version, edition)
- Identifies the publisher (Mr.Orchords)
- Links to the installation media (installer file hash)
- Records the installation directory

Enterprise IT tools (Microsoft Intune, SCCM, BigFix, etc.) scan installed SWID tags to build software inventories.

---

## SWID Tag Structure

### Required Elements

| Element | Purpose | Example |
|---|---|---|
| `<SoftwareIdentity>` | Root element | — |
| `@name` | Product name | `Mr.Orchords` |
| `@tagId` | Unique tag identifier | `Mr.Orchords-v2.3.0` |
| `@version` | Product version | `2.3.0` |
| `@versionScheme` | Version scheme | `semver` |
| `<Entity>` | Publisher information | Mr.Orchords (see below) |

### Optional Elements

| Element | Purpose |
|---|---|
| `<Link>` | Related resources (installer URL, docs) |
| `<Meta>` | Additional product metadata |
| `<Payload>` | Files installed by this product |
| `<Evidence>` | How the software was detected |

---

## SWID Tag Schema

### Tag ID

Format: `{regid}_{product}_{version}`

| Field | Rule | Example |
|---|---|---|
| `regid` | Reverse DNS of publisher | `com.orchords` |
| `product` | Product short name | `mr-orchords` |
| `version` | Full version string | `2.3.0` |

**Full example:** `com.orchords_mr-orchords_2.3.0`

### Entity

Identifies the software publisher:

```xml
<Entity
  name="Mr.Orchords"
  regid="regid.orchords.com"
  role="softwareCreator" />
```

### Link

Links to related resources:

```xml
<Link
  rel="installationmedia"
  href="https://www.orchords.com/download/MrOrchords-2.3.0-Setup.exe"
  type="application/octet-stream" />
<Link
  rel="homepage"
  href="https://www.orchords.com" />
```

### Meta

Additional metadata for ITAM tools:

```xml
<Meta
  product="Mr.Orchords"
  colloquialVersion="2026"
  edition="Professional"
  revision="2.3.0" />
```

### Payload

Files installed by this product:

```xml
<Payload>
  <File name="MrOrchords.exe" size="125829120" />
  <File name="MrOrchordsEngine.dll" size="52428800" />
</Payload>
```

### Evidence

How the software was detected (for ITAM scanning):

```xml
<Evidence>
  <File name="MrOrchords.exe" path="C:\Program Files\Mr.Orchords\MrOrchords.exe" />
</Evidence>
```

---

## Example Tag: Installed Mr.Orchords v2.3.0

```xml
<?xml version="1.0" encoding="UTF-8"?>
<SoftwareIdentity
  xmlns="http://standards.iso.org/iso/19770/-2/2015/schema.xsd"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://standards.iso.org/iso/19770/-2/2015/schema.xsd swid.xsd"
  xml:lang="en-US"
  name="Mr.Orchords"
  tagId="com.orchords_mr-orchords_2.3.0"
  version="2.3.0"
  versionScheme="semver">

  <!-- Publisher -->
  <Entity
    name="Mr.Orchords"
    regid="regid.orchords.com"
    role="softwareCreator" />

  <!-- Links -->
  <Link
    rel="installationmedia"
    href="https://www.orchords.com/download/MrOrchords-2.3.0-Setup.exe" />
  <Link
    rel="homepage"
    href="https://www.orchords.com" />

  <!-- Product metadata -->
  <Meta
    product="Mr.Orchords"
    colloquialVersion="2026"
    edition="Professional"
    revision="2.3.0" />

  <!-- Installed files -->
  <Payload>
    <File name="MrOrchords.exe" size="125829120" />
    <File name="MrOrchordsEngine.dll" size="52428800" />
    <File name="MrOrchordsSetup.exe" size="150994944" />
  </Payload>

  <!-- Detection evidence -->
  <Evidence>
    <File name="MrOrchords.exe" path="C:\Program Files\Mr.Orchords\MrOrchords.exe" />
  </Evidence>

</SoftwareIdentity>
```

---

## Validation Rules

### Schema Validation

The tag must validate against the ISO/IEC 19770-2:2015 schema:
- `swid.xsd` — available from ISO
- Validated at build time by the installer build script

### Required Value Rules

| Rule | Requirement |
|---|---|
| `tagId` | Must match `com.orchords_mr-orchords_{version}` |
| `version` | Must match the installer version |
| `Entity@regid` | Must be `regid.orchords.com` |
| `Meta@product` | Must be `Mr.Orchords` |

---

## Generation

The SWID tag is generated during the build:

```python
# scripts/generate_swid_tag.py
# Called by CMake during release build

def generate_swid_tag(version: str, output_path: str):
    tag = f'''<?xml version="1.0" encoding="UTF-8"?>
<SoftwareIdentity
  xmlns="http://standards.iso.org/iso/19770/-2/2015/schema.xsd"
  xml:lang="en-US"
  name="Mr.Orchords"
  tagId="com.orchords_mr-orchords_{version}"
  version="{version}"
  versionScheme="semver">
  <Entity name="Mr.Orchords" regid="regid.orchords.com" role="softwareCreator" />
  <Meta product="Mr.Orchords" colloquialVersion="2026" edition="Professional" revision="{version}" />
</SoftwareIdentity>'''
    
    with open(output_path, 'w') as f:
        f.write(tag)
```

The generated `.swidtag` file is:
1. Embedded in the installer
2. Installed to `%PROGRAMDATA%\Mr.Orchords\Mr.Orchords.swidtag`
3. Registered with Windows (optional, for WMI query)

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 19770-2:2015 and ISO/IEC 12207:2017 |

---

*Grounded in: ISO/IEC 19770-2:2015 (Software Identification Tags), ISO/IEC 12207:2017 §6.4 (Transition)*



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

- **Next review:** On ISO standard update
- **Reviewer:** Mr.Orchords (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type