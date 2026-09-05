# Terraform Module Promotion Playbook

## Purpose

Define the operational procedure for promoting a Terraform module from internal use to verified-or-trusted third-party status under `TERRAFORM_VERSION_GOVERNANCE.md`. The promotion gates ensure that any module ingested by the project has been reviewed for state hygiene, source provenance, and license compliance.

## Audience

Platform engineers, SREs, and security engineers who publish or consume Terraform modules.

## Pre-conditions

- The module has been in internal use for at least 30 days.
- The module has at least 3 internal consumers.
- The module source repository is in the orchords org.

## Procedure

### Stage 1 — Internal

1. The module lives in `github.com/<orchords-org>/terraform-modules/<name>`.
2. The module README declares inputs, outputs, and usage.
3. The module has unit tests (`terraform test`).
4. The module has an example under `examples/<scenario>/`.
5. The module has been applied in production in at least 3 internal consumers without rollback.

### Stage 2 — Verified (verified-mirror)

6. The module is mirrored to the internal private registry (`registry.<orchords-org>.internal/<name>`).
7. The mirror pins the source to the internal repository via `source = "git::https://...#vX.Y.Z"`.
8. The consumer MUST commit-pin the tag (not `latest`).

### Stage 3 — Trusted third-party

9. The module is published to the public Terraform Registry (or OpenTofu Registry) with:
   - `source` field pointing back to the internal repository.
   - `version` pinned.
   - `license` declared (MPL-2.0 for OpenTofu works; Apache-2.0 for HashiCorp works).
10. The module is approved by an owner not on the original author team (four-eyes review).
11. The module has a `SECURITY.md` with a coordinated disclosure policy.

### Stage 4 — Untrusted (NOT recommended)

12. Untrusted modules (anonymous GitHub, gists, third-party without review) are forbidden.
13. If a third-party untrusted module is required as an exception, an explicit risk acceptance is filed and the module is vendored into the internal mirror with a pinned commit SHA before use.

### Promotion gates

| Gate | Internal | Verified | Trusted | Untrusted |
|---|---|---|---|---|
| Source | internal repo | internal mirror | public registry | forbidden |
| Pinning | commit SHA | tag | tag + checksum | vendored |
| Review | 1 author | 1 author + 1 reviewer | 2 reviewers | exception only |
| License declared | yes | yes | yes | n/a |
| Unit tests | yes | yes | yes | n/a |

## Rollback

If a promoted module causes an incident:

1. Mark the latest version as ` yanked` in the registry.
2. Pin every consumer to the prior version.
3. File a postmortem per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `TERRAFORM_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- HashiCorp Module Registry: `https://registry.terraform.io/`
- OpenTofu Registry: `https://registry.opentofu.org/`
