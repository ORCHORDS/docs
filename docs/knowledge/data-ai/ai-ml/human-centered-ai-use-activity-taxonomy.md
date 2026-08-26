# Human-centered AI use-activity taxonomy

**Issue:** AI inventories grouped only by model type obscure what people are trying to accomplish, what decisions the system influences, and which outcomes require measurement.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Classify each use case by human goal, task, AI use activities, affected actors, and outcome—not only by model/vendor. NIST's AI Use Taxonomy defines 16 technique- and domain-independent activities intended to support common terminology, cross-domain insight, use-case development, and measurement planning.

## Record

For every workflow capture:

- human goal and accountable decision owner;
- task boundary and ordered AI activities;
- user, subject, operator, reviewer, and downstream recipients;
- model/service and version;
- input/output data classes;
- automation and human-override points;
- intended benefit, foreseeable misuse, and affected outcome;
- activity-specific quality, trustworthiness, usability, and harm measures.

## Controls

1. Observe the real workflow rather than inferring it from architecture.
2. Decompose compound tasks into multiple activities.
3. Define what the human must know, verify, or decide at each handoff.
4. Select evaluation methods per activity and population.
5. Reclassify after UI, model, authority, or workflow changes.
6. Connect high-impact activities to escalation, appeal, and incident processes.

## Verification

Walk representative cases end to end; ask users to restate goals and responsibility; verify instrumentation measures outcomes rather than proxy usage; test automation failure and human override; compare performance across relevant groups and contexts.

## Gotchas

A taxonomy is descriptive, not a risk score or compliance certificate. The same model can serve different activities with different risks. “Human in the loop” is meaningless without authority, information, time, and a tested action.

## Sources

- [NIST: AI Use Taxonomy—A Human-Centered Approach](https://www.nist.gov/publications/ai-use-taxonomy-human-centered-approach)
- [NIST AI Resource Center](https://airc.nist.gov/)
