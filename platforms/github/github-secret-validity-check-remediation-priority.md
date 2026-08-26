# GitHub secret validity checks for remediation priority

**Issue:** Secret-scanning queues treat revoked credentials and active production credentials alike, while teams may incorrectly close an alert solely because a validity service reports inactive.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Enable GitHub validity checks through centrally managed security configurations where supported. Use `active`, `inactive`, and `unknown` as prioritization signals, never as substitutes for incident analysis.

GitHub may send the detected credential—and for some types contextual host or URL data—to the issuer's API. Complete privacy and vendor-risk review before enabling at scale. Extended metadata checks are public preview and must be treated as changeable.

## Response

- **Active:** rotate or revoke immediately, identify access and owner, examine use, remove from history/artifacts, and verify replacement.
- **Inactive:** confirm why and when it became inactive, assess historic exposure, and remove the value.
- **Unknown/unsupported:** handle as potentially active until the issuer or owner establishes otherwise.
- Record detection source, validity timestamp, rotation evidence, affected systems, and closure verifier without copying the secret.

## Verification

Test with safe provider fixtures; confirm centralized configuration coverage; sample alerts across all three states; measure time from detection to revocation; and verify on-demand checks do not leak values into automation logs.

## Gotchas

Status can become stale. A credential may be active but unauthorized for the endpoint used by a check. Validity does not establish whether it was abused. Not all token types support validity or extended metadata.

## Sources

- [GitHub Docs: Validity checks](https://docs.github.com/en/code-security/concepts/secret-security/validity-checks)
- [GitHub Docs: Secret scanning](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning)
