# tldr-man-pages

**Issue:** man pages are verbose and do not show practical examples
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
man tar shows all flags; finding common usage requires reading through dense documentation.

## Pattern / Solution
tldr tar shows practical examples for most common use cases. Community-maintained cheatsheets in tldr-pages repo. tldr --update refreshes local cache. Clients: tldr (Node), tealdeer (Rust, fast). Offline access after first cache.

## Gotchas
- Not all tools have tldr pages; fall back to man or --help for obscure flags
- Contribute missing pages to the open-source tldr-pages repo

## Related
- bash-aliases-functions, curl-advanced-usage
