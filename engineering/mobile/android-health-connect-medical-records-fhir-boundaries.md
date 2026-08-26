# Android Health Connect Medical Records FHIR Boundaries

**Issue:** Medical records in Health Connect contain highly sensitive FHIR resources; broad permissions, unsupported resources, or lossy mapping can expose data or create clinically misleading displays.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Request only the Health Connect medical-resource permissions required by a user-visible feature and explain each purpose at consent time. Keep read and write permissions separate. Check platform/feature availability and handle denial, revocation, and partial grants without blocking unrelated app functions.

Health Connect supports defined FHIR versions and maps a supported subset of resources into medical resource types. Validate incoming FHIR version, resource type, identifiers, coding systems, references, timestamps, and provenance before use. Preserve original clinical meaning; do not silently coerce unsupported observations or units.

Encrypt sensitive local caches, minimize retention, prevent medical payloads from entering analytics/crash logs, and require authenticated tenant/patient binding for any server synchronization. Make writes idempotent and maintain deletion/update provenance. Present source, date, and uncertainty; do not turn data transport into medical advice.

## Verification

Use synthetic FHIR fixtures for supported R4/R4B resources, unsupported resource/category, malformed references, duplicate identifiers, updates/deletes, permission revocation, multiple data sources, offline sync, and process restore. Run privacy review, access-log audit, export/deletion tests, and accessibility tests for clinical displays.

## Gotchas

FHIR validity does not guarantee clinical correctness. Health Connect permissions are user grants, not consent for unrelated cloud processing. Regulations vary by jurisdiction and use case; retain legal/privacy review outside the technical permission flow.

## Sources

- [Android Health Connect Medical Records](https://developer.android.com/health-and-fitness/health-connect/medical-records)
- [Medical Records data format](https://developer.android.com/health-and-fitness/health-connect/medical-records/data-format)
- [Health Connect permissions](https://developer.android.com/health-and-fitness/health-connect/get-started)
