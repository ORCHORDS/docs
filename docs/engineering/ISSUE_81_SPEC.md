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
