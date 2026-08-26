# translation-memory-tmx

**Issue:** Exchanging translation memories between CAT tools using TMX format
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Switching CAT tools or sharing TM between agencies requires an interoperable format. TMX (Translation Memory eXchange) 1.4b is the industry standard.

## Pattern / Solution
TMX structure:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="MyCAT" srclang="en-US" adminlang="en-US"
          datatype="plaintext" segtype="sentence"/>
  <body>
    <tu tuid="welcome.title" creationdate="20260811T000000Z">
      <tuv xml:lang="en-US"><seg>Welcome to our service</seg></tuv>
      <tuv xml:lang="fr-FR"><seg>Bienvenue dans notre service</seg></tuv>
    </tu>
  </body>
</tmx>
```
Key attributes:
- `tuid` -- unique segment identifier for deduplication
- `creationdate` -- ISO 8601 compact form
- `datatype` -- `plaintext` or `html`

## Gotchas
- `srclang` in `<header>` must exactly match the `xml:lang` of source `<tuv>` elements
- Inline tags (`<ph>`, `<bpt>`, `<ept>`) needed for segments with placeholders
- Some tools export TMX with BOM -- strip it before importing into tools that do not expect it

## Related
- `translation-memory-2026.md`
- `xliff-format-handling.md`
