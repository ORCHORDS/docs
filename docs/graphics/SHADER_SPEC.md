# Shader Specification

**Project:** Beetle Studio  
**Owner:** James Park (Graphics Engineer)  
**Reviewers:** Mooned Dev (CEO), Daniel Kim (Effects)  
**ISO Standards:** ISO/IEC 12207:2017 (development — design), ISO/IEC 25010:2023 (functional suitability, performance efficiency)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | HLSL shader interface, parameters, and how to add new shaders |
| **Diátaxis form** | Reference |
| **Primary audience** | James Park, Mooned Dev, Daniel Kim |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document specifies the shader system in Beetle Studio — how shaders are organized, what parameters they expose, and how to add a new shader to the rendering pipeline. Per **ISO/IEC 12207:2017 §6.1**, internal interfaces must be precisely specified so that subsystems (effects, rendering, color) can be developed and modified independently without breaking the whole.

Shaders are the execution layer of Beetle Studio's GPU-accelerated effects pipeline.

## Contents

- [Shader Organization](#shader-organization)
- [Shader Types](#shader-types)
  - [1. Compute Shaders](#1-compute-shaders)
  - [2. Vertex + Pixel Shaders](#2-vertex-pixel-shaders)
- [Common Shader Interface](#common-shader-interface)
- [Parameter Contracts](#parameter-contracts)
- [Adding a New Shader](#adding-a-new-shader)
  - [Step 1: Write the shader](#step-1-write-the-shader)
  - [Step 2: Register with the effects system](#step-2-register-with-the-effects-system)
  - [Step 3: Add to the effects panel](#step-3-add-to-the-effects-panel)
  - [Step 4: Test](#step-4-test)
- [Shader Compilation](#shader-compilation)
  - [Compile Command](#compile-command)
- [Performance Guidelines](#performance-guidelines)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Shader Organization

All shaders live in `third_party/shaders/`:

```
third_party/shaders/
├── color/
│   ├── ColorCorrection.hlsl       ← color wheels, exposure, contrast
│   ├── ColorCurves.hlsl          ← RGB curves
│   └── LutApply.hlsl            ← 3D LUT application
├── blur/
│   ├── GaussianBlur.hlsl         ← separable blur
│   └── DirectionalBlur.hlsl      ← motion blur
├── stylize/
│   ├── Sharpen.hlsl              ← unsharp mask
│   └── NoiseReduction.hlsl       ← temporal noise reduction
├── distortion/
│   ├── LensDistortion.hlsl       ← barrel/pincushion distortion
│   └── Warp.hlsl                ← perspective warp
├── composite/
│   ├── BlendMode.hlsl            ← all blend modes
│   └── ChromaKey.hlsl           ← green/blue screen keying
└── output/
    └── OutputTransform.hlsl      ← color space → display output
```

---

## Shader Types

### 1. Compute Shaders

Used for: blur, sharpen, noise reduction, color correction, LUT application.

Input: `StructuredBuffer<HDRPixel>` (RGBA32_float)  
Output: `RWStructuredBuffer<HDRPixel>`  
Thread group: 16×16 threads

### 2. Vertex + Pixel Shaders

Used for: full-screen passes, compositing, UI overlay rendering.

Full-screen quad, pixel shader writes directly to render target.

---

## Common Shader Interface

Every effect shader follows a common interface:

```hlsl
// Shared include: shaders/common.hlsl

struct ShaderParams {
    float intensity;    // 0.0 = original, 1.0 = full effect
    float2 resolution;   // viewport resolution
    float time;         // for animated effects
};

// All shaders implement:
void ApplyEffect(
    in HDRPixel input,
    in ShaderParams params,
    out HDRPixel output
);
```

---

## Parameter Contracts

Each shader exposes parameters that the UI binds to. Parameters must be declared with metadata:

```hlsl
// Parameter declaration in shader
// [[note: "name=Radius|min=0|max=100|default=5|step=1"]]
cbuffer BlurParams {
    [[note("name=Radius|min=0|max=200|default=5|step=1")]]
    float radius;           // Blur radius in pixels
    
    [[note("name=Intensity|min=0|max=1|default=1.0")]]
    float intensity;         // Blend with original
    
    [[note("name=Quality|min=1|max=3|default=2")]]
    int quality;            // 1=fast, 2=normal, 3=high
};
```

The UI reads this metadata to auto-generate parameter controls.

---

## Adding a New Shader

### Step 1: Write the shader

1. Create `third_party/shaders/<category>/MyEffect.hlsl`
2. Implement the shader using the common interface
3. Add parameter metadata for UI binding
4. Add to `CMakeLists.txt` in the shaders folder

### Step 2: Register with the effects system

```cpp
// Register in EffectRegistry
EffectRegistry::registerEffect<MyEffect>(
    "builtin.my-effect",
    "My Effect",
    "My custom GPU effect",
    EffectCategory::Stylize
);
```

### Step 3: Add to the effects panel

```json
// resources/effects/builtin-effects.json
{
  "id": "builtin.my-effect",
  "name": "My Effect",
  "category": "stylize",
  "parameters": [
    { "name": "radius", "type": "float", "default": 5.0 }
  ]
}
```

### Step 4: Test

- [ ] Shader compiles without errors
- [ ] Parameters are reflected in the UI Properties Panel
- [ ] Effect renders correctly at all resolutions
- [ ] Effect renders correctly in the export pipeline (not just preview)
- [ ] No memory leaks under RenderDoc
- [ ] Thread-safe (no race conditions in multi-threaded rendering)

---

## Shader Compilation

| Stage | When | Tool |
|---|---|---|
| Compile HLSL → DXIL | Build time | DXC (`dxcompiler.dll`) |
| Load at runtime | App launch | DirectX 12 shader reflection |
| Hot reload (dev) | File save | Monitor file changes → recompile |

### Compile Command

```powershell
# Compile HLSL to DXIL for DirectX 12
dxc -T cs_6_2 `
    -E ApplyEffect `
    -Fo MyEffect.dxil `
    MyEffect.hlsl `
    -Qstrip_debug `
    -Qstrip_reflect
```

---

## Performance Guidelines

Per **ISO/IEC 25010:2023** (performance efficiency):

| Guideline | Reason |
|---|---|
| Use `groupshared` memory for blur kernels | Reduces global memory reads |
| Prefer separable filters (horizontal + vertical passes) | O(n) vs O(n²) cost |
| Avoid `discard` in pixel shaders | Causes divergent threads |
| Use 16-bit floats (half) where precision allows | Faster on most GPUs |
| Minimize texture samples per pixel | Bound by texture bandwidth |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial spec — aligned with ISO/IEC 12207:2017 §6.1 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 25010:2023 (Functional Suitability, Performance Efficiency)*



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
| 1.0.0 | June 2026 | James Park | Initial version |
| 1.0.1 | June 2026 | James Park | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On shader system change
- **Reviewer:** James Park (Graphics Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type