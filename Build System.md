> Auto-generated from `engineering/BUILD_SYSTEM.md` in the docs repo.

> Auto-generated from `docs/engineering/BUILD_SYSTEM.md` in the docs repo.

---
title: "Build System"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Build System

**Project:** Beetle Studio  
**Owner:** Sarah Miller (Build & Release Engineer)  
**Reviewers:** Kirk Beka (CTO), all engineering leads  
**ISO Standards:** ISO/IEC 12207:2017 (development process), ISO/IEC 25010:2023 (maintainability, portability)  
**Version:** 1.0.0  
**Last Updated:** 2026-06-21

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | CMake build system, targets, artifacts, and reproducibility |
| **Diátaxis form** | Reference |
| **Primary audience** | All engineers, Mike Johnson, DevOps |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes the build system configuration, toolchain requirements, and build processes for Beetle Studio.

## Contents

- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Build Configurations](#build-configurations)
  - [CMake Presets](#cmake-presets)
  - [Build Targets](#build-targets)
- [Local Build (Windows)](#local-build-windows)
  - [Prerequisites](#prerequisites)
  - [Build Commands](#build-commands)
- [CI/CD Build Pipeline](#cicd-build-pipeline)
- [Build Performance Targets](#build-performance-targets)
- [Dependency Management](#dependency-management)
  - [External Dependencies](#external-dependencies)
  - [Vendored Dependencies](#vendored-dependencies)
  - [Compiler Flags](#compiler-flags)
- [Testing the Build](#testing-the-build)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| **Generator** | CMake | 3.28+ |
| **Compiler** | MSVC (Visual Studio 2022) | 17.x |
| **GPU SDKs** | DirectX 12 Agility SDK | Latest |
| **Vulkan SDK** | LunarG Vulkan SDK | Latest |
| **FFmpeg** | Static build (LGPL) | 7.x |
| **UI Framework** | Qt6 (static or shared, per config) | 6.7+ |
| **CI/CD** | Forgejo Actions (GitHub Actions–compatible YAML) | v15.0 |
| **Installer** | Inno Setup | 6.x |

---

## Repository Structure

```
BEETLE_STUDIO/
├── CMakeLists.txt              ← root build configuration
├── cmake/
│   ├── CompilerFlags.cmake     ← compiler-specific flags
│   ├── Dependencies.cmake      ← external dependency resolution
│   ├── InstallRules.cmake      ← installation rules
│   └── Platform.cmake          ← platform-specific configuration
├── src/
│   ├── BeetleStudio/           ← main application
│   ├── Engine/                 ← rendering, codec, effects core
│   ├── UI/                     ← Qt6 UI components
│   ├── Audio/                  ← audio engine
│   └── Plugins/                ← plugin hosting and OpenFX
├── third_party/
│   ├── FFmpeg/                 ← vendored FFmpeg build
│   ├── Qt6/                    ← Qt6 framework
│   └── shaders/                ← HLSL/GLSL shaders
├── scripts/
│   ├── build.ps1               ← local build script (Windows)
│   └── generate_swid_tag.py    ← SWID tag generation
├── docs/                       ← documentation
├── tools/                      ← internal tooling
└── CMakePresets.json           ← CMake presets for common configurations
```

---

## Build Configurations

### CMake Presets

```bash
# Available presets
cmake --list-presets
# Output:
#   configure --list-presets
#   Available presets:
#     "dev"           "Development (debug, all modules)"
#     "release"       "Release (optimized, no debug symbols)"
#     "relwithdebinfo""Release with debug info"
#     "minimal"      "Minimal (core engine only, fast iteration)"
#     "ci"           "CI (for Forgejo Actions pipeline, GitHub Actions–compatible)"
```

### Build Targets

| Target | Description | Output |
|---|---|---|
| `BeetleStudio` | Main application executable | `BeetleStudio.exe` |
| `BeetleEngine` | Core engine library | `BeetleEngine.dll` |
| `BeetleUI` | UI library | `BeetleUI.dll` |
| `BeetleAudio` | Audio engine library | `BeetleAudio.dll` |
| `BeetlePlugins` | Plugin host library | `BeetlePlugins.dll` |
| `ShaderCompiler` | HLSL → DXIL shader compiler tool | `ShaderCompiler.exe` |
| `tests` | All unit and integration tests | `test_runner.exe` |

---

## Local Build (Windows)

### Prerequisites

- Visual Studio 2022 (Desktop development with C++)
- CMake 3.28+
- Qt6 6.7+ (installed via vcpkg or standalone)
- Vulkan SDK (if building Vulkan backend)
- Python 3.10+ (for build scripts)

### Build Commands

```powershell
# Full build (Debug)
cmake --preset dev
cmake --build --preset dev

# Release build
cmake --preset release
cmake --build --preset release

# Rebuild a single target
cmake --build --preset dev --target BeetleStudio --clean-first

# Build installer (after release preset)
cmake --build --preset release --target installer
```

---

## CI/CD Build Pipeline

See [`CI_CD_PIPELINE.md`](./CI_CD_PIPELINE.md) for the full Forgejo Actions workflow (GitHub Actions–compatible). The build system produces these artifacts per CI run:

| Artifact | Retention | Contents |
|---|---|---|
| `BeetleStudio-Setup.exe` | 90 days | Signed installer |
| `BeetleStudio.zip` | 90 days | Portable build (no install) |
| `BeetleStudio.pdb` | Permanent | Debug symbols for crash dumps |
| `build-logs.zip` | 30 days | CMake + compiler output |

---

## Build Performance Targets

| Metric | Target | Notes |
|---|---|---|
| Clean build time (Release, 16-core) | < 20 minutes | Parallel build maxed |
| Incremental build time (single module) | < 30 seconds | After a single-file change |
| Link time (BeetleStudio.exe) | < 5 minutes | Incremental linking enabled |
| CI total time (Release) | < 30 minutes | From commit to artifact |

---

## Dependency Management

### External Dependencies

All external dependencies are resolved at CMake configure time:

```cmake
find_package(Qt6 REQUIRED COMPONENTS Widgets Core Gui)
find_package(Vulkan REQUIRED)
find_package(FFmpeg REQUIRED COMPONENTS avcodec avformat avutil swscale)
```

### Vendored Dependencies

FFmpeg is vendored in `third_party/FFmpeg/` to ensure reproducibility and LGPL compliance:

- Built from source as a static library
- License attribution included in installer
- Never dynamically linked

### Compiler Flags

| Flag | Debug | Release |
|---|---|---|
| `/W4` | ✅ | ✅ |
| `/WX-` | Warnings off | Warnings as errors |
| `/permissive-` | ✅ | ✅ |
| `/O2` | ❌ | ✅ |
| `/Zi` | ✅ | Partial |
| `/MP8` | ✅ | ✅ (8 parallel) |

---

## Testing the Build

After any build system change:

1. Run `cmake --preset dev && cmake --build --preset dev`
2. Run `./build/dev/tests/test_runner.exe`
3. Run `./build/dev/BeetleStudio.exe` and verify it launches
4. Verify all CI pipelines green

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 §6.3 (Development) and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.3 (Development Process), ISO/IEC 25010:2023 (Maintainability, Portability subcharacteristics)*



---

## References

### Internal Documents

- [$title](././CI_CD_PIPELINE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mike Johnson | Initial version |
| 1.0.1 | June 2026 | Mike Johnson | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On build system major change
- **Reviewer:** Mike Johnson (DevOps Lead)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type