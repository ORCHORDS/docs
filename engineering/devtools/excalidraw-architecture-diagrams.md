# excalidraw-architecture-diagrams

**Issue:** Architecture diagrams in PowerPoint not version-controlled or shareable
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Diagrams in Lucidchart or Visio are locked in proprietary formats and not near the code.

## Pattern / Solution
Excalidraw saves as .excalidraw JSON files — commit alongside code. VS Code extension for in-editor editing. Embed in Notion/Confluence. Hand-drawn aesthetic reduces pressure for perfection. Real-time collaboration via Excalidraw+.

## Gotchas
- .excalidraw files are large JSON — use .gitattributes to mark as binary for diffs
- Export PNG/SVG for embedding in docs; source .excalidraw for iteration

## Related
- mermaid-diagram-as-code, plantuml-patterns, draw-io-automation
