# plantuml-patterns

**Issue:** Need precise UML sequence and class diagrams from code, not freehand
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
System interactions require formal sequence diagrams; Mermaid syntax is too limited for complex UML.

## Pattern / Solution
PlantUML generates diagrams from text. Run locally with plantuml diagram.puml. Types: @startuml @enduml with actor, participant, -> for messages. Use !include for shared components. Render in CI with docker: plantuml/plantuml.

## Gotchas
- PlantUML requires Java — use Docker image to avoid local JRE dependency
- Server-based rendering via public PlantUML server — avoid for proprietary architecture diagrams

## Related
- mermaid-diagram-as-code, excalidraw-architecture-diagrams
