---
title: "Installer Specification"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Installer Specification

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Build & Release Engineer)  
**Reviewers:** Mr.Orchords (CTO), Mr.Orchords (DevOps)  
**ISO Standards:** ISO/IEC 12207:2017 (transition, development), ISO/IEC 25010:2023 (installability, portability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Inno Setup installer, features, and upgrade behavior |
| **Diátaxis form** | Reference |
| **Primary audience** | Mr.Orchords, Mr.Orchords, QA team |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines the Mr.Orchords installer for Windows. Per **ISO/IEC 12207:2017 §6.4**, the transition process includes packaging and distribution. The installer must be reliable, secure, and user-friendly. It must also satisfy **ISO/IEC 25010:2023**'s installability and portability characteristics.
## Contents

- [Technology](#technology)
- [Installer Features](#installer-features)
  - [1. Welcome Screen](#1-welcome-screen)
  - [2. License Agreement](#2-license-agreement)
  - [3. Component Selection](#3-component-selection)
  - [4. Installation Location](#4-installation-location)
  - [5. Additional Tasks](#5-additional-tasks)
  - [6. Installing Screen](#6-installing-screen)
  - [7. Completion Screen](#7-completion-screen)
- [Inno Setup Script Structure](#inno-setup-script-structure)
- [Installation Artifacts](#installation-artifacts)
- [File Associations](#file-associations)
- [Upgrade & Uninstall Behavior](#upgrade-uninstall-behavior)
  - [Upgrade from Previous Version](#upgrade-from-previous-version)
  - [Uninstall](#uninstall)
- [Code Signing](#code-signing)
- [Testing Checklist](#testing-checklist)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Technology

| Component | Technology |
|---|---|
| Installer | Inno Setup 6.x |
| Script | `installer/mr-orchords-setup.iss` |
| Output | `MrOrchordsSetup.exe` (signed) |
| Target OS | Windows 10 (1903+) and Windows 11 |
| Architecture | x64 only |

---

## Installer Features

### 1. Welcome Screen

| Element | Content |
|---|---|
| Title | "Mr.Orchords Setup" |
| Product name | "Mr.Orchords vX.Y.Z" |
| Company | "Mr.Orchords" |
| Icon | Mr.Orchords logo |

### 2. License Agreement

- Full MIT license text (or EULA)
- "I accept" / "I do not accept" radio buttons

### 3. Component Selection

| Component | Default | Size | Notes |
|---|---|---|---|
| **Mr.Orchords Core** | Required | ~150 MB | Main application |
| **Codecs** | Required | ~80 MB | FFmpeg, hardware codecs |
| **Effects & Templates** | Default | ~50 MB | Built-in effects, title templates |
| **VST Support** | Default | ~10 MB | VST plugin hosting |
| **Documentation** | Optional | ~20 MB | User guide, tutorials |
| **Desktop Shortcut** | Optional | — | Shortcut on desktop |
| **Start Menu Shortcut** | Optional | — | Shortcut in Start Menu |

### 4. Installation Location

| Location | Default |
|---|---|
| Program Files | `%PROGRAMFILES%\Mr.Orchords\` |
| AppData | `%APPDATA%\Mr.Orchords\Mr.Orchords\` |
| Temp files | `%TEMP%\Mr.OrchordsSetup\` |

### 5. Additional Tasks

- [ ] Create desktop shortcut
- [ ] Create Start Menu shortcut
- [ ] Launch Mr.Orchords after installation
- [ ] Create file association for `.mrorchords` project files

### 6. Installing Screen

| Feature | Implementation |
|---|---|
| Progress bar | Inno Setup built-in |
| File extraction progress | Inno Setup built-in |
| Custom branding | Mr.Orchords banner image |

### 7. Completion Screen

- "Installation complete" message
- "Launch Mr.Orchords now" checkbox (default: checked)
- "View release notes" link

---

## Inno Setup Script Structure

```pascal
[Setup]
AppName=Mr.Orchords
AppVersion={#Version}
AppPublisher=Mr.Orchords
AppPublisherURL=https://www.orchords.com
DefaultDirName={autopf}\Mr.Orchords
DefaultGroupName=Mr.Orchords
OutputBaseFilename=MrOrchordsSetup-{#Version}
Compression=lzma2/ultra64
SolidCompression=yes

[Files]
Source: "..\build\Release\MrOrchords.exe"; DestDir: "{app}"
Source: "..\build\Release\MrOrchordsEngine.dll"; DestDir: "{app}"
Source: "..\build\Release\*.dll"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Mr.Orchords"; Filename: "{app}\MrOrchords.exe"
Name: "{autodesktop}\Mr.Orchords"; Filename: "{app}\MrOrchords.exe"

[Registry]
Root: HKCR; Subkey: ".mrorchords"; ValueType: string; ValueData: "Mr.Orchords.Project"
Root: HKCR; Subkey: "Mr.Orchords.Project\shell\open\command"; ValueType: string; ValueData: "{app}\MrOrchords.exe ""%1"""
```

---

## Installation Artifacts

| Artifact | Location | Signed? |
|---|---|---|
| `MrOrchordsSetup.exe` | CI artifact | ✅ (required) |
| `MrOrchords.zip` (portable) | CI artifact | ❌ (no installer needed) |
| `MrOrchords.pdb` (symbols) | CI artifact | ❌ (internal use) |
| `MrOrchords.swidtag` | Inside installer | ✅ (part of installer) |

---

## File Associations

| Extension | Associated Action | Description |
|---|---|---|
| `.mrorchords` | Open with Mr.Orchords | Mr.Orchords project file |
| `.mrorchords-template` | Open with Mr.Orchords | Project template file |

---

## Upgrade & Uninstall Behavior

### Upgrade from Previous Version

| Scenario | Behavior |
|---|---|
| Same version | "Already installed" — repair or uninstall options |
| Newer version | Upgrade — preserves settings, projects, plugins |
| Older version | Downgrade blocked — requires uninstall first |
| Install over existing | Clean install — old files removed |

### Uninstall

| Behavior | Detail |
|---|---|
| Remove program files | All files in `%PROGRAMFILES%\Mr.Orchords\` |
| Remove AppData | `%APPDATA%\Mr.Orchords\Mr.Orchords\` (prompt user) |
| Remove registry entries | File associations, uninstall entry |
| Preserve projects | `%USERPROFILE%\Documents\Mr.Orchords\` never removed |
| Leave shortcut | Removed (Start Menu and Desktop) |

---

## Code Signing

The installer **must be signed** before distribution. See [`CODE_SIGNING_CERTIFICATE_MANAGEMENT.md`](./CODE_SIGNING_CERTIFICATE_MANAGEMENT.md) for the signing process.

Unsigned installers trigger Windows SmartScreen warnings. Signed installers pass SmartScreen within ~1,000–5,000 installs.

---

## Testing Checklist

Before every release:

- [ ] Fresh install on Windows 10 (1903+)
- [ ] Fresh install on Windows 11
- [ ] Upgrade from previous version
- [ ] Uninstall → clean reinstall
- [ ] Verify all components installed
- [ ] Verify file associations work
- [ ] Verify SmartScreen doesn't block (or verify signed)
- [ ] Verify app launches after install
- [ ] Verify all shortcuts work
- [ ] Verify no leftover files after uninstall
- [ ] Verify installer size is reasonable (< 500 MB)

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 §6.4 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Transition), ISO/IEC 25010:2023 (Installability, Portability)*



---

## References

### Internal Documents

- [$title](././CODE_SIGNING_CERTIFICATE_MANAGEMENT.md)

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

- **Next review:** On each installer major change
- **Reviewer:** Mr.Orchords (Build & Release Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type