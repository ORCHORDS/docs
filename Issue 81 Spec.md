> Auto-generated from `Issue 81 Spec.md` in the docs repo.

> Auto-generated from `Issue 81 Spec.md` in the docs repo.

> Auto-generated from `Issue 81 Spec.md` in the docs repo.

> Auto-generated from `Issue 81 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_81_SPEC.md` in the docs repo.

---
title: "DragDropImporter Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# DragDropImporter Feature Spec

**Resolves:** #81

Location: ``src/IO/DragDropImporter.h``

## Goals

- Implement the user-facing behaviour from issue #81.
- Small public surface, framework-agnostic.

## Public API (sketch)

```cpp
class DragDropImporter {
public:
    bool Initialize();
    void Shutdown();
};
```

## Dependencies

- `CommonTypes.h`, `Logging.h`.
