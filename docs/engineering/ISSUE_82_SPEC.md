# UndoRedoManager Feature Spec

**Resolves:** #82

Location: ``src/Core/UndoRedoManager.h``

## Goals

- Implement the user-facing behaviour from issue #82.
- Small public surface, framework-agnostic.

## Public API (sketch)

```cpp
class UndoRedoManager {
public:
    bool Initialize();
    void Shutdown();
};
```

## Dependencies

- `CommonTypes.h`, `Logging.h`.
