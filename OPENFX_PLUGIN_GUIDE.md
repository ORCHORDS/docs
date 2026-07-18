---
title: "OpenFX Plugin Guide (Third-Party)"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# OpenFX Plugin Guide (Third-Party)

**Project:** Mr.Orchords  

**Owner:** Mr.Orchords (Effects & Compositing Engineer — SDK), Mr.Orchords (Technical Writer — user guide)  
**Reviewers:** Mr.Orchords (CTO)  
**ISO Standards:** ISO/IEC 12207:2017 (development — API documentation), ISO/IEC 25010:2023 (functional suitability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Third-party OpenFX plugin user guide and developer getting-started |
| **Diátaxis form** | Tutorial |
| **Primary audience** | Plugin users, third-party plugin developers, Mr.Orchords, Mr.Orchords |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This guide helps third-party plugin developers build effects compatible with Mr.Orchords, and helps users install and manage third-party effects. Per **ISO/IEC 12207:2017 §6.1**, API documentation must be clear, accurate, and versioned so developers can build compatible plugins.
## Contents

- [For Plugin Users](#for-plugin-users)
  - [Finding Plugins](#finding-plugins)
  - [Installing a Plugin](#installing-a-plugin)
  - [Managing Plugins](#managing-plugins)
- [For Plugin Developers](#for-plugin-developers)
  - [Getting Started](#getting-started)
  - [Your First Plugin](#your-first-plugin)
  - [Parameter Definition](#parameter-definition)
  - [Render Function](#render-function)
  - [Building](#building)
  - [Testing Your Plugin](#testing-your-plugin)
- [Plugin Compatibility](#plugin-compatibility)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## For Plugin Users

### Finding Plugins

The best sources for OpenFX plugins:

| Source | URL | Notes |
|---|---|---|
| **Mus productions** | musashi-cpp.netlify.app | Free; well-maintained |
| **VirtualDip.org** | virtualdip.org | Free; color correction tools |
| **Pixelanan** | pixelanan.blogspot.com | Free; variety of effects |
| **RevisionFX** | revisionfx.com | Commercial; professional suite |
| **FilmConvert** | filmconvert.com | Commercial; film stock emulation |
| **Neat Video** | neatvideo.com | Commercial; best noise reduction |

### Installing a Plugin

1. Download the plugin (usually a `.zip` file)
2. Extract — you should get a folder with a `.ofx` or `.vst3` file
3. Copy the `.ofx` or `.vst3` file to your plugin directory:
   ```
   %PROGRAMFILES%\Mr.Orchords\OpenFX\
   ```
4. Launch Mr.Orchords — the plugin appears in the Effects Panel

### Managing Plugins

**Edit → Preferences → Plugins** shows all installed plugins:
- Enable/disable individual plugins without uninstalling
- See plugin version and vendor information
- Report incompatible plugins

---

## For Plugin Developers

### Getting Started

To build an OpenFX plugin for Mr.Orchords, you'll need:

| Tool | Version | Notes |
|---|---|---|
| C++ compiler | MSVC 2022, GCC 12+ | C++20 minimum |
| CMake | 3.20+ | Build system |
| OpenFX SDK | 1.4 | [Download from openfx.org](https://openfx.org) |
| Mr.Orchords | Latest beta | For testing |

### Your First Plugin

A minimal OpenFX plugin structure:

```
MyFirstEffect/
├── MyFirstEffect.cpp      ← plugin implementation
├── CMakeLists.txt         ← build config
└── icon.png              ← 256×256 plugin icon
```

### Parameter Definition

```cpp
// In describe() — define your effect's parameters
void BlurEffect::describe(OfxImageEffectHandle effect) {
    // Set plugin properties
    mPlugin->setProperty("OfxImageEffectPropSupportedContexts", "Filter");

    // Add a "Radius" parameter
    addDoubleParam("Radius", "Blur Radius", "pixels", 5.0, 0.0, 100.0);
    
    // Add a mix parameter (0 = full effect, 1 = original)
    addDoubleParam("Mix", "Mix", "", 0.0, 0.0, 1.0);
}
```

### Render Function

```cpp
// In render() — process the frame
void BlurEffect::render(
    OfxPropertySetHandle inArgs,
    OfxPropertySetHandle outArgs) {
    
    // Get input image
    void* inPixels = getInputImage("Source", inArgs);
    
    // Get parameter values
    double radius = getDoubleParam("Radius");
    double mix = getDoubleParam("Mix");
    
    // Apply blur algorithm
    applyGaussianBlur(inPixels, radius);
    
    // Blend with original based on mix
    blendWithOriginal(inPixels, mix);
}
```

### Building

```bash
mkdir build && cd build
cmake .. -DOPENFX_SDK=/path/to/ofx-sdk
cmake --build . --config Release
# Output: MyFirstEffect.ofx
```

### Testing Your Plugin

1. Copy `MyFirstEffect.ofx` to `%PROGRAMFILES%\Mr.Orchords\OpenFX\`
2. Launch Mr.Orchords
3. Apply the effect to a clip and verify:
   - [ ] Effect appears in Effects Panel
   - [ ] Parameters render correctly
   - [ ] No memory leaks (check with RenderDoc/PIX)
   - [ ] Thread-safe (Mr.Orchords calls render from multiple threads)

---

## Plugin Compatibility

| Feature | Supported | Notes |
|---|---|---|
| Single-source image processing | ✅ | Primary use case |
| Multi-source inputs (e.g., blend modes) | ✅ | `OfxImageEffectPropSupportsMultipleSources` |
| Custom parameter types | ✅ | String, choice, pushbutton |
| Keyframe animation | ✅ | All numeric parameters |
| 32-bit float processing | ✅ | Enable in project settings |
| GPU acceleration (via OpenCL/CUDA) | ⚠️ | Via host-provided OpenCL context |
| Audio processing | ❌ | Separate audio effect API (future) |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial guide — aligned with ISO/IEC 12207:2017 §6.1 and OpenFX 1.4 spec |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 25010:2023 (Functional Suitability, Maintainability)*



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

- **Next review:** Quarterly
- **Reviewer:** Mr.Orchords (Effects & Compositing Engineer — SDK)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type