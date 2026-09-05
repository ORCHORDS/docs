# OPA Bundle Rotation Playbook

## Purpose

Define the operational procedure for rotating an OPA bundle (policy + data) without service disruption. The procedure ensures that OPA agents always have a signed, validated bundle.

## Audience

Platform engineers, SREs, and security engineers who run OPA in production.

## Pre-conditions

- OPA 1.0+ is in use (per `OPA_VERSION_GOVERNANCE.md`).
- Bundles are signed via `cosign` or GPG.
- The bundle server (BSR, S3, GCS, or HTTP) is reachable.

## Procedure

### Step 1 — Author the new bundle

1. Edit the Rego policy under `policies/<package>/`.
2. Edit the data under `data/<package>/` (JSON or YAML).
3. Run `opa fmt -w policies/`.
4. Run `opa test policies/`.
5. Run `opa build -b policies/<package>/ -o bundle.tar.gz`.

### Step 2 — Sign the bundle

6. Compute the SHA-256 of `bundle.tar.gz`.
7. Sign with `cosign sign --key cosign.key <sha>` or `gpg --sign`.
8. Embed the signature in the bundle manifest (`.manifest`).

### Step 3 — Publish

9. Upload `bundle.tar.gz` to the bundle server (BSR / S3 / GCS / HTTP).
10. Upload the signature.
11. Update the discovery URL or BSR tag.

### Step 4 — Verify the rotation

12. Force a bundle pull: `curl http://opa-server/v1/bundles/<name>` or trigger via control plane.
13. Confirm the new bundle SHA matches.
14. Confirm OPA logs `bundle loaded` with the new SHA.

### Step 5 — Validate

15. Run a synthetic policy query.
16. Confirm `decision_id` and `result`.
17. Confirm the bundle is now serving traffic.

### Step 6 — Roll back if needed

18. If the new bundle is faulty, revert the upload.
19. Force a bundle pull to the previous version.
20. Confirm OPA logs `bundle loaded` with the previous SHA.

## Rollback

If the new bundle causes incorrect decisions:

1. Revert the upload (or delete the bundle).
2. OPA will continue serving the last good bundle.
3. Investigate the policy regression.
4. Re-publish a corrected bundle.

## References

- `OPA_VERSION_GOVERNANCE.md`
- OPA bundles: `https://www.openpolicyagent.org/docs/latest/management-bundles/`
- Cosign: `https://docs.sigstore.dev/cosign/overview/`
