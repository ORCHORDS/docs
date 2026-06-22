> Auto-generated from `docs/standards/ISO_19770_SWID_TAGS.md` in the docs repo.

---
title: "ISO/IEC 19770-2:2015 — Software Identification (SWID) Tags"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "releases"
status: "approved"
iso-refs: ["ISO/IEC 19770-2:2015", "NIST IR 8060"]
---

# ISO/IEC 19770-2:2015 — Software Identification (SWID) Tags

## Purpose

This document defines the SWID tag specification for Beetle Studio releases, enabling automated software asset management, license compliance verification, and security vulnerability correlation.

SWID tags are XML-based metadata documents that uniquely identify a software product installation, per ISO/IEC 19770-2:2015.

## Scope

Applies to:
- All Beetle Studio installer packages (Inno Setup, MSIX)
- Patch/update packages
- Plugin/extension packages
- Portable/standalone distributions

---

## SWID Tag Types

| Type | When Created | Purpose |
|------|-------------|---------|
| Corpus tag | At build time | Identifies the software product as available for installation |
| Primary tag | At install time | Identifies installed software instance |
| Patch tag | When patch applied | Identifies a patch to installed software |
| Supplemental tag | Post-install | Adds metadata (e.g., license, organization) |

---

## Tag Structure

### Required Elements

```xml
<?xml version="1.0" encoding="UTF-8"?>
<SoftwareIdentity
    xmlns="http://standards.iso.org/iso/19770/-2/2015/schema.xsd"
    name="Beetle Studio"
    tagId="dev.mooned.beetle-studio-{version}"
    version="{version}"
    versionScheme="semver"
    xml:lang="en">

    <!-- Entity: Tag creator and software creator -->
    <Entity
        name="Mooned Dev"
        regid="dev.mooned"
        role="tagCreator softwareCreator"/>

    <!-- Entity: Distributor (if different) -->
    <Entity
        name="Mooned Dev"
        regid="dev.mooned"
        role="distributor"/>

</SoftwareIdentity>
```

### Full Tag with All Optional Elements

```xml
<?xml version="1.0" encoding="UTF-8"?>
<SoftwareIdentity
    xmlns="http://standards.iso.org/iso/19770/-2/2015/schema.xsd"
    xmlns:swid="http://standards.iso.org/iso/19770/-2/2015/schema.xsd"
    name="Beetle Studio"
    tagId="dev.mooned.beetle-studio-1.0.0"
    version="1.0.0"
    versionScheme="semver"
    tagVersion="1"
    corpus="false"
    patch="false"
    supplemental="false"
    xml:lang="en">

    <!-- Entities involved -->
    <Entity
        name="Mooned Dev"
        regid="dev.mooned"
        role="tagCreator softwareCreator distributor licensor"/>

    <!-- Links to related resources -->
    <Link
        rel="license"
        href="https://dev.mooned.dev/beetle-studio/beetle-studio/src/branch/main/LICENSE"/>
    <Link
        rel="release-notes"
        href="https://dev.mooned.dev/beetle-studio/beetle-studio/releases"/>

    <!-- Meta: additional descriptive data -->
    <Meta
        activationStatus="unlicensed"
        product="Beetle Studio"
        colloquialVersion="1.0"
        edition="Professional"
        revision="GA"
        summary="Professional video editing software for Windows"/>

    <!-- Payload: files installed -->
    <Payload>
        <Directory name="Beetle Studio" root="%PROGRAMFILES%">
            <File name="beetle_studio.exe" size="15728640"
                  SHA-256:hash="a1b2c3d4..."/>
            <File name="beetle_studio.dll" size="8388608"
                  SHA-256:hash="e5f6g7h8..."/>
            <Directory name="plugins">
                <File name="openfx_bridge.dll" size="2097152"/>
            </Directory>
        </Directory>
    </Payload>

    <!-- Evidence: discovered installation artifacts -->
    <Evidence date="2026-06-21T00:00:00Z">
        <Directory name="Beetle Studio" root="%PROGRAMFILES%">
            <File name="beetle_studio.exe"/>
        </Directory>
    </Evidence>

</SoftwareIdentity>
```

---

## Key Attributes

### SoftwareIdentity Attributes

| Attribute | Required | Description | Beetle Studio Value |
|-----------|----------|-------------|-------------------|
| name | Yes | Product name | "Beetle Studio" |
| tagId | Yes | Globally unique tag identifier | "dev.mooned.beetle-studio-{version}" |
| version | Yes | Product version (SemVer) | "1.0.0" |
| versionScheme | No | Version numbering scheme | "semver" |
| tagVersion | No | Tag document revision | Integer, starts at 1 |
| corpus | No | Is this a corpus tag? | "true" for build artifacts |
| patch | No | Is this a patch? | "true" for update packages |
| supplemental | No | Is this supplemental? | "true" for license tags |
| xml:lang | No | Language | "en" |

### Entity Roles

| Role | Meaning |
|------|---------|
| tagCreator | Organization that created this SWID tag |
| softwareCreator | Organization that created the software |
| distributor | Organization distributing the software |
| licensor | Organization licensing the software |

### Version Schemes

| Scheme | Description |
|--------|-------------|
| semver | Semantic Versioning (RECOMMENDED) |
| multipartnumeric | Dot-separated integers |
| multipartnumeric+suffix | Integers with suffix |
| alphanumeric | Free-form string |
| decimal | Single decimal number |
| unknown | Unknown scheme |

---

## Tag Lifecycle

```
BUILD TIME:     Corpus tag created (identifies available software)
                ↓
INSTALL TIME:   Primary tag deployed to %PROGRAMDATA%/regid.dev.mooned/
                ↓
PATCH TIME:     Patch tag references primary tag via <Link rel="patches">
                ↓
UNINSTALL:      Primary tag removed
```

---

## File Location Convention

Per NIST IR 8060 guidelines:

```
%PROGRAMDATA%/regid.dev.mooned/
    regid.dev.mooned_beetle-studio-1.0.0.swidtag
    regid.dev.mooned_beetle-studio-1.0.1-patch.swidtag
```

Filename format: `regid.{regid}_{tagId}.swidtag`

---

## Integration with Beetle Studio Build

The release-build.yml workflow MUST:
1. Generate corpus SWID tag at build time
2. Include primary SWID tag in installer package
3. Installer deploys tag to `%PROGRAMDATA%/regid.dev.mooned/`
4. Uninstaller removes the tag

---

## CoSWID (Concise SWID - RFC 9393)

For embedded/constrained scenarios, IETF RFC 9393 defines a CBOR-encoded equivalent of SWID tags (CoSWID). Beetle Studio MAY generate CoSWID for use in:
- Windows Store submissions (MSIX package metadata)
- Automated vulnerability scanning (CVE correlation)
- Software Bill of Materials (SBOM) integration

---

## References

- [ISO/IEC 19770-2:2015 (ISO official)](https://www.iso.org/standard/65666.html)
- [NIST IR 8060: SWID Tag Guidelines](https://nvlpubs.nist.gov/nistpubs/ir/2016/nist.ir.8060.pdf)
- [NIST SWID Tagging Project](https://csrc.nist.gov/projects/software-identification-swid/guidelines)
- [RFC 9393: Concise SWID Tags (CoSWID)](https://datatracker.ietf.org/doc/html/rfc9393)
- [ISO/IEC 19770 Wikipedia](https://en.wikipedia.org/wiki/ISO/IEC_19770)
- [SWID Tag XSD Schema](http://standards.iso.org/iso/19770/-2/2015-current/schema.xsd)
