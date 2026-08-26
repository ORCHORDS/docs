# Apple Translation framework download lifecycle

**Issue:** An app assumes on-device translation is immediately available for every language pair and loses user work when model download or availability changes.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS and language availability

Apple's Translation framework provides system translation experiences and language availability. Treat translation as an optional, cancellable operation whose model/download state and output provenance are visible to the user.

**Source:** [Apple Translation documentation](https://developer.apple.com/documentation/translation)

## Controls

- check OS and language-pair availability before offering the action;
- initiate downloads with clear user intent and network/storage messaging;
- preserve source text and label machine-translated output;
- cancel stale requests when source, target, or document changes;
- avoid sending sensitive content elsewhere as an undocumented fallback;
- retain manual editing and retry paths.

## Verification

Test unsupported pair, first-time download, offline, low storage, cancellation, app backgrounding, repeated requests, language change, and framework errors. Ensure late output cannot overwrite newer edits.

## Gotchas

Downloaded availability can change with device state or OS data. Translation is not authoritative for legal/safety text. Language identification and target selection are separate decisions.
