---
title: "OpenFX Plugin SDK"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# OpenFX Plugin SDK

**Project:** Beetle Studio  
**Owner:** Daniel Kim (Effects & Compositing Engineer)  
**Reviewers:** Kirk Beka (CTO), Alex Chen (UI)  
**ISO Standards:** ISO/IEC 12207:2017 (development, API design), ISO/IEC 25010:2023 (maintainability, functional suitability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | OpenFX plugin API, parameter format, and SDK developer guide |
| **Diátaxis form** | Reference |
| **Primary audience** | Daniel Kim, third-party plugin developers, Alex Chen |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes the OpenFX plugin system in Beetle Studio. Per **ISO/IEC 12207:2017 section 6.1**, software design must define interfaces that allow extensibility. The OpenFX SDK enables third-party developers to build visual effects compatible with Beetle Studio. Per **ISO/IEC 25010:2023**, this extensibility supports functional suitability and maintainability.
## Contents

- [OpenFX Version](#openfx-version)
- [Plugin Architecture](#plugin-architecture)
- [Plugin API Reference](#plugin-api-reference)
  - [Required Functions](#required-functions)
  - [Parameter Types](#parameter-types)
  - [Image Input/Output](#image-inputoutput)
- [Building a Plugin](#building-a-plugin)
  - [Project Setup](#project-setup)
  - [Plugin Bundle Structure](#plugin-bundle-structure)
- [Parameter Descriptor Example](#parameter-descriptor-example)
- [Testing Plugins](#testing-plugins)
- [Publishing Plugins](#publishing-plugins)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## OpenFX Version

Beetle Studio implements **OpenFX 1.4** (the most widely supported version).

Reference: [OpenFX 1.4 Specification](https://openfx.org/doc/1.4/)

---

## Plugin Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Beetle Studio (Plugin Host)                 │
│                                                          │
│  ┌──────────────────┐                                   │
│  │  Plugin Host API  │                                   │
│  │  (OfxHost)        │                                   │
│  └────────┬─────────┘                                   │
│           │                                              │
│           ▼                                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │              OpenFX Plugin (.ofx)                 │   │
│  │                                                  │   │
│  │  OfxPlugin → describe() → effect descriptor      │   │
│  │              → create() → effect instance         │   │
│  │              → render() → processed frame          │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## Plugin API Reference

### Required Functions

Every OpenFX plugin must implement:

```cpp
// Entry point — called once when plugin is loaded
OfxPlugin* OfxGetPlugin(uint32_t apiVersion, uint32_t pluginVersion);

// Mandatory callbacks
static OfxStatus OfxPlugin::describe(OfxImageEffectHandle effect);
static OfxStatus OfxPlugin::describeInContext(
    OfxImageEffectHandle effect,
    OfxPropSetHandle context);
static OfxStatus OfxPlugin::create(OfxImageEffectHandle effect);
static OfxStatus OfxPlugin::destroy(OfxImageEffectHandle instance);
static OfxStatus OfxPlugin::render(
    OfxImageEffectHandle instance,
    OfxPropertySetHandle inArgs,
    OfxPropertySetHandle outArgs);
```

### Parameter Types

| Parameter | OfxType | Notes |
|---|---|---|
| Integer | `kOfxParamTypeInteger` | Clamped to min/max |
| Float | `kOfxParamTypeDouble` | Supports keyframe animation |
| Color | `kOfxParamTypeRGB` | 3-component (R, G, B) |
| Color | `kOfxParamTypeRGBA` | 4-component (R, G, B, A) |
| Choice | `kOfxParamTypeChoice` | Dropdown list |
| Boolean | `kOfxParamTypeBoolean` | Checkbox |
| String | `kOfxParamTypeString` | Text input |
| PushButton | `kOfxParamTypePushbutton` | Action trigger |

### Image Input/Output

| Property | Value | Notes |
|---|---|---|
| Pixel depths | 8-bit, 16-bit float, 32-bit float | User-selectable in settings |
| Color spaces | Linear, sRGB | OpenFX default is linear |
| Alpha support | Premultiplied, Straight | Configurable |

---

## Building a Plugin

### Project Setup

```cmake
# CMakeLists.txt for an OpenFX plugin
add_library(my_effect SHARED my_effect.cpp)
target_include_directories(my_effect PRIVATE ${OPENFX_INCLUDE})
target_link_libraries(my_effect PRIVATE ${OPENFX_LIBRARIES})
set_target_properties(my_effect PROPERTIES
    PREFIX ""          # No prefix — .ofx extension required
    SUFFIX ".ofx")
```

### Plugin Bundle Structure

```
MyEffect.ofx/
├── Contents/
│   ├── Resources/
│   │   ├── Default.ofx.png   # 256x256 plugin icon
│   │   └── ParamGroups.txt  # UI grouping
│   └── Linux-x86-64/
│       └── MyEffect.ofx     # Linux build
│   └── Mac/
│       └── MyEffect.ofx     # macOS build
│   └── Windows-x86-64/
│       └── MyEffect.ofx     # Windows build (code-signed)
└── Manifest.xml
```

---

## Parameter Descriptor Example

```cpp
OfxStatus describe(OfxImageEffectHandle effect) {
    // Create the effect descriptor
    mEffect = effect;
    
    // Define a "Mix" parameter (0.0 = full effect, 1.0 = original)
    OfxParamHandle mixParam;
    mEffect->defineParam(kOfxPluginMixParamName, kOfxParamTypeDouble, "");
    mEffect->paramSetProp(mixParam, kOfxParamPropDefault, 0.0);
    mEffect->paramSetProp(mixParam, kOfxParamPropMin, 0.0);
    mEffect->paramSetProp(mixParam, kOfxParamPropMax, 1.0);
    
    // Define a blur radius (in pixels)
    OfxParamHandle radiusParam;
    mEffect->defineParam("Radius", kOfxParamTypeDouble, "pixels");
    mEffect->paramSetProp(radiusParam, kOfxParamPropDefault, 5.0);
    mEffect->paramSetProp(radiusParam, kOfxParamPropMin, 0.0);
    mEffect->paramSetProp(radiusParam, kOfxParamPropMax, 200.0);
    
    return kOfxStatOK;
}
```

---

## Testing Plugins

| Test | Scope | Tool |
|---|---|---|
| API compliance | Plugin loads and responds to all OfxHost calls | Beetle Studio plugin test harness |
| Parameter animation | Keyframes persist and interpolate correctly | Visual inspection + regression test |
| Render performance | No memory leaks, acceptable frame time | PIX / RenderDoc |
| Cross-platform | Same effect works on all supported platforms | CI plugin test matrix |

---

## Publishing Plugins

Plugin SDK docs and publishing guidelines: see [`OPENFX_PLUGIN_GUIDE.md`](../OPENFX_PLUGIN_GUIDE.md)

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial SDK documentation — aligned with ISO/IEC 12207:2017 and OpenFX 1.4 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 25010:2023 (Functional Suitability, Maintainability)*



---

## References

### Internal Documents

- [$title](./../OPENFX_PLUGIN_GUIDE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Daniel Kim | Initial version |
| 1.0.1 | June 2026 | Daniel Kim | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On OpenFX major version
- **Reviewer:** Daniel Kim (Effects & Compositing Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type