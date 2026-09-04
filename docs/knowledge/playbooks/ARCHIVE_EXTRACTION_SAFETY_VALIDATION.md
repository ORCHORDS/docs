# Archive Extraction Safety Validation

## Trigger
Run before enabling archive uploads, after archive/extraction-library changes, after resource-limit changes, and during periodic upload-security review.

## Inputs
- Supported archive/file formats.
- Maximum upload, expanded-size, and archive-entry limits.
- Extraction library/service and temporary-storage design.
- Symlink policy.
- Nested-archive behavior.

## Procedure
1. Record the documented maximum uploaded size, maximum uncompressed size, and maximum archive-entry count for the feature.
2. Verify the application can determine or enforce expanded-size and entry-count limits before material extraction occurs.
3. Submit a compressed archive whose stored size is within the upload limit but whose expanded size exceeds the allowed maximum; confirm rejection before full extraction.
4. Submit an archive whose entry count exceeds the configured maximum; confirm rejection before the archive is materially unpacked.
5. Exercise nested archives according to the supported processing model and confirm nested expansion cannot bypass the intended resource envelope.
6. Submit an archive containing symlinks and confirm rejection unless symlink support is explicitly required.
7. If symlinks are required, test a target outside the permitted extraction boundary and confirm the allowlist/confinement control blocks it.
8. Confirm rejected archives do not leave partially trusted extracted files available to downstream processing.
9. Verify temporary extraction data is cleaned up according to the application’s storage lifecycle.
10. Record gaps, remediate, and rerun the failed archive cases.

## Escalation
Escalate archive handling that expands before limits are enforced, permits uncontrolled symlinks, leaves partial trusted-looking output after rejection, or allows nested archives to bypass documented limits.

## Evidence
- Documented upload/archive limits.
- Expanded-size rejection test.
- Entry-count rejection test.
- Nested-archive result.
- Symlink test.
- Partial-extraction/cleanup verification.
- Findings and retest evidence.

## Completion criteria
Archive processing enforces expanded-size and entry-count limits before extraction, constrains symlink behavior, and leaves no trusted partial output after rejection.

## Source basis
- OWASP ASVS 5.0.0 requirements V5.1.1, V5.2.3, and V5.2.5: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
