# GitHub Actions immutable OIDC subject claims

**Issue:** Cloud trust policies based only on repository owner and name can be confused by namespace reuse, and an unsynchronized subject-template change can break every deployment.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Bind GitHub Actions federated identities to immutable owner and repository IDs where GitHub supports immutable OIDC subjects. GitHub documents that repositories created after 2026-07-15 use the immutable default format, while older repositories retain the previous format unless opted in. GitHub Enterprise Server is excluded from this rollout.

## Migration

1. Inventory cloud trust policies and capture currently observed issuer, audience, and subject.
2. Resolve immutable owner/repository IDs through trusted GitHub metadata.
3. Add a narrowly scoped cloud-provider trust condition for the new subject before changing GitHub.
4. Keep branch, environment, workflow, or custom-property context as needed; repository identity alone is usually too broad.
5. Opt in at organization or repository level through supported settings/API.
6. Run a non-production token exchange and inspect claims without logging the token.
7. Remove the legacy condition only after all required workflows succeed.
8. Monitor renames, transfers, repository restoration, and policy drift.

## Verification

Decode only short-lived test tokens locally, validate `iss`, `aud`, `sub`, time bounds, owner ID, repository ID, and contextual claims, then destroy them. Prove an unauthorized branch and a different repository ID are denied.

## Gotchas

Customizing included claims replaces the entire default subject template. GitHub warns the cloud condition must exist first. Never paste tokens into issues or logs. Name-based and ID-based formats may coexist during migration.

## Sources

- [GitHub OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub REST API for Actions OIDC](https://docs.github.com/en/rest/actions/oidc)
