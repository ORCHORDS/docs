# mermaid-diagram-as-code

**Issue:** Architecture diagrams not versioned alongside code and go stale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Diagrams in external tools drift from actual code; updating requires switching tools.

## Pattern / Solution
Mermaid defines diagrams in text inside Markdown fences. GitHub renders natively. Types: flowchart, sequenceDiagram, erDiagram, gitGraph, C4Context. VS Code extension for preview. Mermaid CLI for SVG export in CI.

## Gotchas
- Complex diagrams with many nodes become unreadable — split into multiple smaller diagrams
- %% comments in Mermaid; label text with special chars needs quoting

## Related
- excalidraw-architecture-diagrams, plantuml-patterns, obsidian-engineering-notes
