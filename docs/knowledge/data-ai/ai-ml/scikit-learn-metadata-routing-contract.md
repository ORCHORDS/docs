# Scikit-learn Metadata Routing Contract

**Issue:** Sample weights, groups, or other metadata can be dropped, rejected, or sent to the wrong estimator or scorer when a composite scikit-learn workflow has no explicit routing contract.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Pin the scikit-learn version and enable metadata routing explicitly only in applications qualified for the experimental API.
- Inventory every consumer and router in each Pipeline, cross-validation, search, splitter, and scorer path.
- Set each method request deliberately: request metadata, decline it, reject it when supplied, or map it through a documented alias.
- Use separate aliases when fitting and scoring require different weights.
- Treat routing configuration as part of the serialized training definition and review it with the model code.
- Fail a release when a meta-estimator in the supported path does not implement routing.

## Implementation and tests

1. Build the full production composite with routing enabled.
2. Pass distinct sentinel arrays for fitting weights, scoring weights, and groups.
3. Assert each intended consumer receives only its declared value.
4. Misspell and omit each metadata key and assert the documented error or fallback.
5. Run once with routing disabled to detect accidental reliance on global process state.
6. Repeat tests across the pinned upgrade matrix before changing scikit-learn.

## Gotchas and applicability

The API is experimental, disabled by default, incomplete across meta-estimators, and may change outside the usual deprecation cycle. A request value of false, none, and an unchanged existing request are different policies. Routing proves delivery, not that an estimator interprets weights correctly; retain statistical validation. Recheck the current support table before adopting a new composite.

## Official sources

- https://scikit-learn.org/stable/metadata_routing.html
- https://scikit-learn.org/stable/developers/develop.html#metadata-routing
