> Auto-generated from `Technical Standards.md` in the docs repo.

> Auto-generated from `engineering/TECHNICAL_STANDARDS.md` in the docs repo.

> Auto-generated from `docs/engineering/TECHNICAL_STANDARDS.md` in the docs repo.

---
title: "Technical Standards"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Technical Standards

**Project:** Beetle Studio  
**Owner:** Kirk Beka (CTO)  
**Reviewers:** Mooned Dev (CEO), all engineering leads  
**ISO Standards:** ISO/IEC 12207:2017 (development process), ISO/IEC 25010:2023 (maintainability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | C++ coding standards, API design rules, and RFC process |
| **Diátaxis form** | Reference |
| **Primary audience** | All engineers, Kirk Beka |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

These standards govern how Beetle Studio code is written, reviewed, and maintained. Per **ISO/IEC 12207:2017 section 6.3**, the development process includes defining coding standards that ensure software quality and maintainability. These standards support **ISO/IEC 25010:2023**'s maintainability characteristic.
## Contents

- [C++ Coding Standards](#c-coding-standards)
  - [Standard](#standard)
  - [Core Principles](#core-principles)
  - [Naming Conventions](#naming-conventions)
  - [Memory Management](#memory-management)
  - [Error Handling](#error-handling)
  - [No-Except Guidelines](#no-except-guidelines)
- [API Design Standards](#api-design-standards)
  - [General Principles](#general-principles)
  - [Breaking Change Policy](#breaking-change-policy)
  - [Deprecation](#deprecation)
- [File Organization](#file-organization)
- [Code Review Standards](#code-review-standards)
  - [Review Checklist](#review-checklist)
  - [Approval Requirements](#approval-requirements)
- [RFC Process (Architectural Decisions)](#rfc-process-architectural-decisions)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## C++ Coding Standards

### Standard

- **C++ version:** C++20 (minimum), targeting C++23 where beneficial
- **Compiler:** MSVC (Visual Studio 2022) primary; GCC/Clang for cross-platform code

### Core Principles

1. **Write for correctness first, performance second** — profile before optimizing
2. **No undefined behavior** — even if MSVC doesn't catch it, it will bite us on other platforms
3. **Explicit over implicit** — avoid hidden side effects, implicit conversions
4. **RAII everywhere** — no raw `new`/`delete`; use smart pointers and containers

### Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Class/Struct | PascalCase | `BeetleTimeline`, `AudioMixer` |
| Function | PascalCase | `LoadProject()`, `RenderFrame()` |
| Member variable | `m_` prefix + PascalCase | `m_projectPath`, `m_frameRate` |
| Static variable | `s_` prefix + PascalCase | `s_instanceCount` |
| Global variable | `g_` prefix + PascalCase | `g_logger` |
| Local variable | camelCase | `frameIndex`, `isReady` |
| Enum value | PascalCase | `TrackType::VideoTrack` |
| Macro / constant | SCREAMING_SNAKE | `MAX_TRACKS`, `DEFAULT_FPS` |
| Header guard | `BEETLE_<MODULE>_<FILENAME>_H` | `BEETLE_TIMELINE_TRACK_H` |

### Memory Management

```cpp
// ✅ Correct — unique_ptr for exclusive ownership
auto effect = std::make_unique<BlurEffect>();

// ✅ Correct — shared_ptr for shared ownership
auto timeline = std::make_shared<Timeline>();

// ❌ Forbidden — raw new/delete
auto buffer = new uint8_t[size];  // Use std::vector or unique_ptr
delete[] buffer;
```

### Error Handling

| Scenario | Approach |
|---|---|
| Expected recoverable errors | `std::optional<T>` or `std::expected<T, E>` |
| Unexpected/programming errors | `assert()` in debug; crash with logged context in release |
| External system errors (file I/O, GPU) | Custom exception with context (`BeetleException`) |
| Never silently swallow errors | Always log or propagate |

### No-Except Guidelines

```cpp
// ✅ noexcept for functions that cannot throw
void Reset() noexcept { /* ... */ }

// ✅ Functions that allocate may throw — don't mark noexcept
std::vector<float> GetWaveformData() { /* may allocate */ }
```

---

## API Design Standards

### General Principles

1. **Prefer composition over inheritance**
2. **Keep APIs narrow and deep** — few methods per class, each doing meaningful work
3. **Avoid virtual function call overhead in hot paths**
4. **Version public APIs explicitly** — changes to public headers require review

### Breaking Change Policy

Any change to a public API that breaks existing callers counts as a **MAJOR version increment** per our [`VERSIONING_POLICY.md`](../releases/VERSIONING_POLICY.md). Examples:

| Change | Breaking? | Action |
|---|---|---|
| Add new method to class | No | MINOR increment |
| Add new parameter to existing method | Yes | MAJOR increment (use overload instead) |
| Change return type of method | Yes | MAJOR increment |
| Rename method | Yes | MAJOR increment (deprecate old name first) |
| Add `const` to parameter | No | Safe change |

### Deprecation

```cpp
// Mark deprecated functions — they'll be removed in a future MAJOR version
[[deprecated("Use InitializeAsync() instead. Removal in v3.0.")]]
bool Initialize();
```

---

## File Organization

| File Type | Suffix | Example |
|---|---|---|
| Class header | `.h` | `Timeline.h` |
| Class implementation | `.cpp` | `Timeline.cpp` |
| Inline implementation | `.inl` | `Timeline.inl` (included in `.h`) |
| Unit tests | `_test.cpp` | `Timeline_test.cpp` |
| Module documentation | `_notes.md` | `RenderNotes.md` |

---

## Code Review Standards

Per **ISO/IEC 12207:2017 §6.3.8**, peer review is a required quality assurance activity.

### Review Checklist

- [ ] Code compiles without warnings
- [ ] Tests added or updated
- [ ] No memory leaks introduced
- [ ] Error handling is appropriate
- [ ] API breaking changes flagged (domain lead review required)
- [ ] Performance impact considered (especially for hot paths)
- [ ] No hardcoded secrets or credentials
- [ ] Documentation updated if public API changed

### Approval Requirements

| Change Type | Required Approvals | Who |
|---|---|---|
| Bug fix / refactor (single module) | 1 | Any engineer on the team |
| New feature | 1 | Domain lead for the feature area |
| Public API change | 2 | Domain lead + Kirk Beka |
| Cross-cutting concern | 2 | Domain leads affected + Kirk Beka |
| Security-sensitive change | 2 | Kirk Beka + Maya Rodriguez |

---

## RFC Process (Architectural Decisions)

For significant architectural changes, an RFC (Request for Comments) is required.
A change is "significant" if it touches **any** of: a public API surface, the
core engine (graphics / codecs / timeline / effects), cross-platform strategy,
security model, build/release pipeline, or license/business rules.

1. **Author** copies [`docs/rfc/RFC-XXX-template.md`](../rfc/RFC-XXX-template.md)
   to `docs/rfc/RFC-XXX-<title>.md` (where `XXX` is the next available RFC
   number from the index) and fills in **all** sections. Skipping the
   *Alternatives Considered* or *Migration Plan* sections is grounds for
   immediate rejection in review.
2. **RFC template** sections: Context, Decision, Consequences, Alternatives
   Considered, Migration Plan, Open Questions, References, Review Notes, Outcome.
3. **Pull request** opens a 1-week open-comment window on the RFC file.
   Discussions happen on the PR (not Slack) so the rationale is preserved.
4. **Decision** by Kirk Beka (with Mooned Dev for engine-level changes).
   Decision criteria are recorded in §9 *Outcome* of the RFC itself.
5. **Outcome** posted as a PR comment and tracked in the issue tracker:
   *Accepted* / *Accepted with changes* / *Rejected* / *Deferred*. Accepted
   RFCs are merged and added to the RFC index.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial standards — aligned with ISO/IEC 12207:2017 §6.3 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.3 (Development Process), ISO/IEC 25010:2023 (Maintainability: Modularity, Reusability, Analysability, Modifiability, Testability)*



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
| 1.0.0 | June 2026 | Kirk Beka | Initial version |
| 1.0.1 | June 2026 | Kirk Beka | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Kirk Beka (CTO)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type