# Secure Software Release Verification Playbook

## Trigger

Use before publishing a production software release or distributing a build that is intended to become a trusted release artifact.

## Inputs

- release candidate and source revision;
- approved build workflow and dependency state;
- test and security-check results;
- artifact provenance, signatures, or attestations when used;
- release notes and rollback information.

## Steps

1. **Pin the release identity.** Record the exact source revision, version, build inputs, and intended distribution target.
2. **Use the approved build path.** Build through the controlled process rather than an untracked workstation or ad-hoc environment.
3. **Verify required checks.** Confirm required tests, security checks, dependency checks, and policy gates completed on the release revision.
4. **Review unresolved risk.** Identify known vulnerabilities, accepted exceptions, failed optional checks, or changes requiring explicit approval.
5. **Verify artifact integrity.** Confirm checksums, signatures, provenance, or equivalent integrity evidence match the artifact being released.
6. **Prepare recovery.** Ensure rollback or replacement procedures are usable and that the previous known-good state is identifiable.
7. **Authorize publication.** Record the accountable release decision and publish only the verified artifacts.
8. **Observe after release.** Monitor early production signals and be prepared to halt, rollback, or replace the release if material problems appear.

## Completion criteria

The release is complete when the exact published artifact is traceable to its approved source revision and build process, required checks are recorded, exceptions are authorized, and recovery information is available.

## Sources

- NIST — SP 800-218, Secure Software Development Framework Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- SLSA — Supply-chain Levels for Software Artifacts specification: https://slsa.dev/spec/

## Scope note

This playbook does not claim a particular SLSA level or certification. Controls should be selected according to the software's risk and distribution model.
