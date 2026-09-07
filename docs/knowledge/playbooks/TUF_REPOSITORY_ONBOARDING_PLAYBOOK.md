# TUF Repository Onboarding Playbook

## Purpose

Onboard a new private artifact repository (container images, language packages, or CI tool installers) onto the ORCHORDS TUF metadata service so that consumers can verify signatures and metadata for every artifact pulled from the new repository.

## Audience

Platform security engineers, build/release engineers, repository maintainers bringing a new artifact feed online.

## Pre-conditions

- TUF metadata service running and healthy (see `TUF_VERSION_GOVERNANCE.md` reference card).
- `repository-tool` CLI installed and authenticated to the metadata service.
- A list of target files (artifacts) with their SHA-256 digests.
- Hardware-backed root signing keys (YubiHSM2 or AWS CloudHSM) accessible to at least 3 of 5 root holders.

## Procedure

1. **Initialize repository metadata**: `repository-tool init --role root --threshold 3 --num-keys 5`. This generates the offline `root.json` to be signed by the 5 root holders.
2. **Distribute root signing**: each of the 5 root holders signs `root.json` independently with their HSM. Combine the signatures via `repository-tool combine-roles --role root`.
3. **Stage targets**: copy the new artifact set into the staging bucket. Run `repository-tool add-target --path images/* --expires 90d` to enumerate them.
4. **Sign targets and snapshot**: the targets signer produces `targets.json`; the snapshot signer produces `snapshot.json`.
5. **Set timestamp**: the online timestamp signer publishes `timestamp.json` with a 24-hour expiry.
6. **Publish**: copy the metadata directory (`root.json`, `targets.json`, `snapshot.json`, `timestamp.json`) to the metadata endpoint served over TLS.
7. **Client onboarding**: distribute the pinned `root.json` to consumers via the existing out-of-band bootstrap bundle. Document the repository name and key ID in `docs/security/tuf-clients.md`.
8. **Verify**: run `tuf client --repo https://artifacts.example.com/repo-x --root root.json list` from a clean client and confirm the expected targets are visible.

## Rollback

- Stop publishing updates to the metadata endpoint.
- Re-publish the previous `root.json` if a root key compromise is discovered.
- Notify consumers to revert to the previous bootstrap bundle via the standard security mailing list.

## References

- TUF specification — https://theupdateframework.io/
- Internal reference card: `TUF_VERSION_GOVERNANCE.md`.
- Internal NIST SP 800-218A GenAI profile (Batch 50 reference).
