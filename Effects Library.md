> Auto-generated from `effects/EFFECTS_LIBRARY.md` in the docs repo.

> Auto-generated from `docs/effects/EFFECTS_LIBRARY.md` in the docs repo.

---
title: "Effects Library"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Effects Library

**Project:** Beetle Studio  
**Owner:** Daniel Kim (Effects & Compositing Engineer)  
**Reviewers:** James Park (Graphics), Lisa Martinez (QA)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO/IEC 25010:2023 (functional suitability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Catalog of all built-in effects, parameters, and GPU cost |
| **Diátaxis form** | Reference |
| **Primary audience** | Daniel Kim, James Park, Lisa Martinez, Tom Anderson |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document catalogs all built-in effects in Beetle Studio — what each does, what parameters it exposes, what GPU resources it consumes, and what the expected output should be. Per **ISO/IEC 12207:2017 §6.1**, software components must be documented so that the team, QA, and technical writers can work from a single authoritative source.

This library is the reference for:
- **QA** — writing regression tests and expected output specifications
- **Tom Anderson** — writing user-facing documentation
- **Plugin developers** — understanding how built-in effects work as a reference for OpenFX plugins
- **Engineering** — understanding effect dependencies and resource costs

## Contents

- [Effects by Category](#effects-by-category)
  - [Color Correction](#color-correction)
  - [Blur](#blur)
  - [Sharpen & Enhance](#sharpen-enhance)
  - [Stylize](#stylize)
  - [Distortion](#distortion)
  - [Compositing](#compositing)
- [Effect Ordering](#effect-ordering)
- [GPU Resource Usage](#gpu-resource-usage)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Effects by Category

### Color Correction

#### Color Wheels

| Property | Value |
|---|---|
| **ID** | `builtin.color-wheels` |
| **Category** | Color Correction |
| **GPU Cost** | Low (single pass) |
| **Parameters** | Master Exposure (±3.0), Master Gamma, Master Saturation, Shadows (RGB), Midtones (RGB), Highlights (RGB), Temperature (K) |
| **Output** | Color-graded frame |
| **Notes** | Replaces manual color balance; designed for quick, intuitive grading |

#### Color Curves

| Property | Value |
|---|---|
| **ID** | `builtin.color-curves` |
| **Category** | Color Correction |
| **GPU Cost** | Low (lookup table generated per frame) |
| **Parameters** | RGB curve (bezier), Red curve, Green curve, Blue curve, Hue vs Saturation, Hue vs Luminance |
| **Output** | Curvature-adjusted frame |

#### LUT Application

| Property | Value |
|---|---|
| **ID** | `builtin.lut` |
| **Category** | Color Correction |
| **GPU Cost** | Medium (3D texture sample) |
| **Parameters** | LUT file (.cube), Intensity (0–100%) |
| **Output** | LUT-transformed frame |
| **Notes** | Supports .cube files from Adobe, DaVinci Resolve, and standard LUT exporters |

---

### Blur

#### Gaussian Blur

| Property | Value |
|---|---|
| **ID** | `builtin.gaussian-blur` |
| **Category** | Blur |
| **GPU Cost** | Medium (two-pass separable) |
| **Parameters** | Radius (0–200 px), Quality (1=fast, 2=normal, 3=high) |
| **Output** | Softened frame |
| **Notes** | Separable — horizontal then vertical pass |

#### Directional Blur

| Property | Value |
|---|---|
| **ID** | `builtin.directional-blur` |
| **Category** | Blur |
| **GPU Cost** | Medium |
| **Parameters** | Angle (0–360°), Amount (0–100%) |
| **Output** | Motion-blurred frame |

---

### Sharpen & Enhance

#### Sharpen

| Property | Value |
|---|---|
| **ID** | `builtin.sharpen` |
| **Category** | Sharpen |
| **GPU Cost** | Low |
| **Parameters** | Amount (0–200%), Radius (0.5–3.0 px), Threshold (0–0.1) |
| **Output** | Sharpened frame |

#### Noise Reduction

| Property | Value |
|---|---|
| **ID** | `builtin.noise-reduction` |
| **Category** | Sharpen |
| **GPU Cost** | High (temporal accumulation) |
| **Parameters** | Luminance Strength (0–100), Spatial Detail (0–100), Temporal Stability (0–100) |
| **Output** | Denoised frame |
| **Notes** | Uses temporal frame accumulation — best on stationary shots |

---

### Stylize

#### Film Grain

| Property | Value |
|---|---|
| **ID** | `builtin.film-grain` |
| **Category** | Stylize |
| **GPU Cost** | Low |
| **Parameters** | Amount (0–100%), Size (Fine/Medium/Coarse), Color (Monochrome/Color) |
| **Output** | Grain-textured frame |

#### Vignette

| Property | Value |
|---|---|
| **ID** | `builtin.vignette` |
| **Category** | Stylize |
| **GPU Cost** | Low |
| **Parameters** | Amount (±100%), Radius (0–2.0), Softness (0–1.0), Shape (Circle/Oval/Square) |
| **Output** | Vignetted frame |

---

### Distortion

#### Lens Distortion

| Property | Value |
|---|---|
| **ID** | `builtin.lens-distortion` |
| **Category** | Distortion |
| **GPU Cost** | Low |
| **Parameters** | Distortion Amount (±1.0), Chromatic Aberration (0–0.5) |
| **Output** | Corrected frame |
| **Notes** | Positive = barrel distortion, negative = pincushion |

#### Warp

| Property | Value |
|---|---|
| **ID** | `builtin.warp` |
| **Category** | Distortion |
| **GPU Cost** | Low |
| **Parameters** | Horizontal Bend (±50%), Vertical Bend (±50%), Perspective Horizontal (±25%), Perspective Vertical (±25%) |
| **Output** | Warped frame |

---

### Compositing

#### Blend Modes

Beetle Studio supports all standard blend modes as a compositing effect:

| Supported | Notes |
|---|---|
| Normal | Default |
| Multiply | Darkens |
| Screen | Lightens |
| Overlay | Contrast |
| Soft Light | Gentle contrast |
| Hard Light | Strong contrast |
| Color Dodge | Lightens based on dark |
| Color Burn | Darkens based on light |
| Difference | Inverts |
| Exclusion | Similar to difference, lower contrast |
| Add | Linear light addition |
| Subtract | Linear light subtraction |

#### Chroma Key

| Property | Value |
|---|---|
| **ID** | `builtin.chroma-key` |
| **Category** | Compositing |
| **GPU Cost** | Medium |
| **Parameters** | Key Color (eyedropper), Tolerance (0–100%), Edge Softness (0–50%), Edge Feather (0–10 px), Spill Suppression (0–100%) |
| **Output** | Matte-composited frame |
| **Notes** | Supports green screen and blue screen |

---

## Effect Ordering

Effects are applied in the order they appear in the Effect Stack (top to bottom = render order):

```
Input Frame
  │
  │ 1. Color Correction effects (LUT, Color Wheels, Curves)
  │
  │ 2. Sharpen / Noise Reduction
  │
  │ 3. Blur effects
  │
  │ 4. Distortion
  │
  │ 5. Stylize (Film Grain, Vignette)
  │
  │ 6. Compositing (Blend Modes, Chroma Key)
  │
  ▼
Output Frame
```

---

## GPU Resource Usage

| Effect | VRAM per frame | GPU Compute Load |
|---|---|---|
| Color Wheels | ~10 MB | Low |
| Color Curves | ~10 MB | Low |
| LUT Apply | ~10 MB + LUT texture | Medium |
| Gaussian Blur | ~20 MB | Medium |
| Noise Reduction | ~40 MB (temporal buffer) | High |
| Chroma Key | ~15 MB | Medium |
| Film Grain | ~10 MB | Low |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial library — aligned with ISO/IEC 12207:2017 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 25010:2023 (Functional Suitability)*



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
| 1.0.0 | June 2026 | Daniel Kim | Initial version |
| 1.0.1 | June 2026 | Daniel Kim | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On each new effect release
- **Reviewer:** Daniel Kim (Effects & Compositing Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type