---
title: "Timeline Data Model"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Timeline Data Model

**Project:** Beetle Studio  
**Owner:** Emma Thompson (Timeline Systems Engineer)  
**Reviewers:** Alex Chen (UI), Kirk Beka (CTO)  
**ISO Standards:** ISO/IEC 12207:2017 (development), ISO/IEC 25010:2023 (functional suitability, usability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Clip and track data structures, undo system, and serialization |
| **Diátaxis form** | Reference |
| **Primary audience** | Emma Thompson, Alex Chen, Kirk Beka |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document describes the internal data model of the Beetle Studio timeline. Per **ISO/IEC 12207:2017 section 6.1.3**, the data model must be defined with sufficient precision for implementation and cross-team coordination. Per **ISO/IEC 25010:2023**, a clean data model supports usability -- complex editing must feel effortless.
## Contents

- [Core Data Types](#core-data-types)
  - [Project](#project)
  - [Track](#track)
  - [Clip](#clip)
  - [AppliedEffect](#appliedeffect)
- [Undo/Redo System](#undoredo-system)
  - [Command Interface](#command-interface)
  - [Core Commands](#core-commands)
  - [Undo Stack](#undo-stack)
- [Key Timeline Operations](#key-timeline-operations)
  - [Splitting](#splitting)
  - [Trimming](#trimming)
  - [Nested Clips](#nested-clips)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Core Data Types

### Project

```cpp
struct Project {
    std::string name;
    uint32_t frameRate;            // e.g., 30, 60, 24, 25, 29.97
    uint32_t width;                // Output width in pixels
    uint32_t height;               // Output height in pixels
    PixelFormat pixelFormat;       // RGBA, YUV422, etc.
    ColorSpace colorSpace;         // Rec.709, DCI-P3, etc.
    uint64_t durationFrames;       // Total project length in frames
    
    std::vector<Track> tracks;
    std::vector<Marker> markers;
    Selection selection;
};
```

### Track

```cpp
struct Track {
    std::string id;                // UUID
    TrackType type;                // Video, Audio, Subtitle
    std::string name;              // User-visible name
    int zIndex;                    // Layer order (higher = on top)
    bool isMuted;
    bool isSolo;
    bool isLocked;
    
    std::vector<Clip> clips;
};
```

### Clip

```cpp
struct Clip {
    std::string id;                // UUID
    ClipType type;                 // Video, Audio, Image, Nested
    
    // Source media
    std::optional<MediaSource> source;
    
    // Timeline position
    uint64_t timelineStart;        // Where clip starts on timeline (frames)
    uint64_t sourceStart;          // In-point in source media (frames)
    uint64_t duration;             // Clip duration on timeline (frames)
    
    // Speed / time remapping
    double speedRatio;             // 1.0 = normal, 0.5 = half speed, 2.0 = double speed
    
    // Effects
    std::vector<AppliedEffect> effects;
    
    // Compositing
    BlendMode blendMode;
    std::optional<Mask> trackMatte;
    
    // State
    bool isSelected;
    bool isLocked;
    std::string labelColor;
};
```

### AppliedEffect

```cpp
struct AppliedEffect {
    std::string pluginId;          // "builtin.blur" or UUID for plugin
    bool isEnabled;
    std::unordered_map<std::string, ParameterValue> parameters;
};
```

---

## Undo/Redo System

The timeline uses a **Command Pattern** for undo/redo. Per **ISO/IEC 25010:2023**, reliability includes recoverability — users must be able to reverse mistakes.

### Command Interface

```cpp
class ITimelineCommand {
public:
    virtual void execute() = 0;
    virtual void undo() = 0;
    virtual void redo() = 0;
    virtual std::string description() const = 0;
};
```

### Core Commands

| Command | Triggered By | Undo Effect |
|---|---|---|
| `AddClipCommand` | Drag clip to timeline | Remove clip |
| `DeleteClipCommand` | Delete key / cut | Restore clip |
| `MoveClipCommand` | Drag clip on timeline | Restore previous position |
| `TrimClipCommand` | Drag clip edge | Restore trim point |
| `SplitClipCommand` | S key / razor tool | Merge clips back |
| `ApplyEffectCommand` | Drag effect to clip | Remove effect |
| `ChangeSpeedCommand` | Speed dialog | Restore previous speed |
| `AddTrackCommand` | Add track button | Remove track |
| `ReorderTrackCommand` | Drag track up/down | Restore track order |

### Undo Stack

- **Max depth:** 100 operations (configurable in settings)
- **Memory limit:** 500 MB (oldest commands dropped when limit exceeded)
- **Grouping:** Rapid sequential edits (e.g., dragging) are grouped into one undo step

---

## Key Timeline Operations

### Splitting

1. User positions playhead and presses `S` (or uses razor)
2. `SplitClipCommand` created:
   - Clip A: same source range, timeline up to playhead
   - Clip B: same source range, timeline from playhead
3. Both clips reference same `MediaSource`
4. Undo merges them back into one clip

### Trimming

- **Trim in-point:** Adjust `sourceStart` forward (ripple subsequent clips)
- **Trim out-point:** Adjust `duration` (no ripple)
- **Ripple trim:** All subsequent clips shift by trim delta

### Nested Clips

- A clip can contain an entire timeline (nested project)
- Nested timeline is a full `Project` object
- Unlimited nesting depth
- Used for pre-composing workflows

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial data model — aligned with ISO/IEC 12207:2017 §6.1.3 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1.3 (Design), ISO/IEC 25010:2023 (Functional Suitability, Usability)*



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
| 1.0.0 | June 2026 | Emma Thompson | Initial version |
| 1.0.1 | June 2026 | Emma Thompson | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On timeline model change
- **Reviewer:** Emma Thompson (Timeline Systems Engineer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type