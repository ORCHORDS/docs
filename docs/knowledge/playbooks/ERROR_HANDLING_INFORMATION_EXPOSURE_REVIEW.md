# Error Handling Information Exposure Review

## Procedure
1. Identify user-facing and API error paths.
2. Test representative invalid, failed, and exceptional conditions.
3. Check for stack traces, secrets, identifiers, internal paths, or excessive detail.
4. Confirm diagnostic detail is restricted to appropriate logs.
5. Remediate exposure and retest.

## Source basis
- NIST SP 800-53 Rev. 5 — SI family.
