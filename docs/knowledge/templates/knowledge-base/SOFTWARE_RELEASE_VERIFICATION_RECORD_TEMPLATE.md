# Software Release Verification Record Template

Use this record to capture evidence that a software release was verified before distribution. NIST SSDF 1.1 calls for software integrity verification information and protected release/provenance data.

## Release identification
- **Release:** <version-or-build>
- **Commit or source reference:** <source-reference>
- **Build date:** <date-time>
- **Release owner:** <role>

## Integrity verification
- **Artifact list:** <artifacts>
- **Cryptographic hashes recorded:** <yes-no>
- **Signing status:** <signed-not-signed-not-applicable>
- **Verification location:** <public-or-controlled-reference>

## Provenance and dependencies
- **Provenance captured:** <yes-no>
- **SBOM or component inventory:** <reference>
- **Dependency review:** <result>
- **Build environment evidence:** <reference>

## Security and quality gates
| Gate | Result | Evidence |
| --- | --- | --- |
| Tests | <pass-fail> | <reference> |
| Static or security analysis | <pass-fail-not-applicable> | <reference> |
| Artifact integrity | <pass-fail> | <reference> |
| Release approval | <approved-rejected> | <reference> |

## Archive
- **Release artifacts archived:** <yes-no>
- **Integrity data archived:** <yes-no>
- **Provenance data archived:** <yes-no>
- **Retention reference:** <policy-or-record>

## Completion criteria
Release only after the expected artifacts, integrity evidence, provenance data, required gates, and approval are recorded.

## Reference basis
- NIST SP 800-218 — Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/projects/ssdf
