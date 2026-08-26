# Apple Journaling Suggestions privacy boundary

**Issue:** An app treats personal journaling suggestions as a general activity-history feed or uploads suggestion data before the user deliberately chooses it.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS availability

Journaling Suggestions offers a system-controlled picker for personal moments. Keep selection user-driven and process only the content the person explicitly chooses; do not attempt to enumerate or infer the private suggestion store.

**Source:** [Apple JournalingSuggestions documentation](https://developer.apple.com/documentation/journalingsuggestions)

## Controls

- present suggestions only in a clear journaling/composition context;
- request the narrow content types needed;
- keep unselected suggestion information outside application telemetry;
- obtain separate consent before cloud upload or sharing;
- apply normal deletion, export, retention, and account-isolation controls;
- provide a manual-entry path when unavailable or declined.

## Verification

Test cancel, empty results, partial selection, denied/unavailable state, offline use, multiple accounts, deletion, export, app reinstall, and unsupported OS versions. Confirm analytics cannot reveal suggestion content or nonselection.

## Gotchas

Picker presentation is not consent to publish. Suggested assets may carry sensitive time/location context. Availability and returned content vary; never make core journal access depend on suggestions.
