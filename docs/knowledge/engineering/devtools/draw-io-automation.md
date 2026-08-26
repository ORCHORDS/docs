# draw-io-automation

**Issue:** draw.io diagrams not integrated into CI or version control effectively
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Architecture diagrams in draw.io updated manually; exported PNGs committed as binary blobs with no diff.

## Pattern / Solution
Save as .drawio.xml (text format) for git-diff visibility. VS Code extension (hediet.vscode-drawio) for in-editor editing. draw-io-export CLI exports PNG/SVG in CI for documentation site. Embed .drawio in Confluence via draw.io plugin.

## Gotchas
- .drawio XML diffs are verbose — use --word-diff for more readable git output
- draw.io desktop is Electron app; VS Code extension avoids separate install

## Related
- excalidraw-architecture-diagrams, mermaid-diagram-as-code, confluence-documentation
