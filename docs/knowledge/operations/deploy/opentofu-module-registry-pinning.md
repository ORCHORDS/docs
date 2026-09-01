# OpenTofu Module Registry Pinning

**Issue:** OpenTofu modules are consumed from public or private registries, and operators who rely on loose semver ranges or unconstrained latest tags receive upstream changes without their knowledge, breaking the reproducibility guarantee that IaC is supposed to provide. Module registry pinning is the practice of binding a configuration to a specific module version using digest-based references, and the operational details of how to enforce that binding in CI and at apply time are where most implementations fall short.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The OpenTofu Module Reference

OpenTofu, like Terraform, supports module references in the form `source = "registry.example.com/org/module/aws"`. The reference can include a version constraint (`version = "~> 1.2"`) or a specific version (`version = "1.2.3"`). In addition, OpenTofu accepts a `source` parameter that resolves to the registry's API and downloads the module archive by tag. The registry returns metadata including the module's input variables, output values, and provider requirements.

Pinning by version alone is insufficient because tags are mutable in most registries. A malicious or accidental tag rewrite can serve a different module under the same version. The fix is to verify the module's content-addressable digest after download. OpenTofu supports `lock.hcl` (or `terraform.lock.hcl` for compatibility) that records the source URL, the version, and the digest hash of every module and provider the configuration depends on. A subsequent apply that encounters a different digest will refuse to proceed.

## The Lock File Lifecycle

OpenTofu generates the lock file on the first `init` and updates it on subsequent `init -upgrade`. The lock file should be committed to version control; it is the artifact that enforces pinning across environments. A developer who runs `tofu init -upgrade` and commits the updated lock file is effectively promoting a new module version to all environments, which should require the same review as any other configuration change.

Operational discipline around the lock file includes: never edit it manually, never allow `init -upgrade` in CI without an explicit task label, and treat any PR that includes a lock-file change as a meaningful change that deserves review. The lock file diff itself is the most informative artifact; reviewers can compare hashes and determine whether the new module version is the cause of the lock-file change. CI should display the lock-file diff prominently in the PR summary.

## Registry Trust Boundary

Module registries fall into two trust classes: the public registry, where anyone can publish a module that anyone else can consume, and a private registry that the team controls. The public registry model assumes the module author is trusted and the registry operators are honest, but neither assumption has held historically. Pinning the digest provides a partial defense: even if a module is republished, the digest will differ and the lock file will refuse to apply. The defense is complete only when combined with explicit provenance verification.

OpenTofu supports the `--verify-module-versions-from-registry` flag and `--registry-protocol` settings that integrate with registries implementing the module registry protocol's signing extensions. Configure the registry to sign every published module artifact, then verify the signature in CI before applying. The lock file records the signature alongside the digest so the audit trail includes both integrity and authenticity.

## Cross-Provider And Cross-Module Consistency

Module pinning has a hidden dimension: a module that depends on a particular provider version can pull in a provider that conflicts with another module's provider requirement. OpenTofu's lock file includes provider hashes for this reason; if two modules require incompatible provider versions, `init` will fail with a clear message about the conflict. Resolve conflicts by aligning module versions to a compatible set, and document the compatibility matrix in the platform repository.

When multiple modules share a provider, the lock file records a single provider hash shared across all references. This means that upgrading one module's provider requirement upgrades the shared provider for every other module that consumes it. The change has system-wide blast radius and should be reviewed with the same care as a base-image upgrade. A provider upgrade that breaks a downstream module should be caught at the lock-file review step, not at apply time.

## Failure Modes

The most common failure is `init -upgrade` running in CI for every commit, which auto-bumps modules to their latest versions and defeats the purpose of pinning. Configure CI to run `init` without `-upgrade`, and require an explicit PR label or workflow trigger to perform upgrades. The label should require a human approval before the upgrade runs, and the resulting PR should include the diff of provider and module hashes for review.

A second failure is the lock file being absent or ignored in legacy projects that predate OpenTofu. Pin the existing modules by introducing the lock file in a separate PR that records current hashes, then commit it. Subsequent upgrades go through the standard review process. Without the initial pin, the project remains exposed to drift from upstream modules between commits.

A third failure is a private registry that does not enforce immutable tags. Configure the registry to refuse tag reuse, and configure the publishing pipeline to fail when the same tag is pushed twice. Operators who rely on tag immutability will lose it when the registry drifts; the digest pinning still protects the apply, but the lock file will diverge from the registry's notion of "latest", confusing developers who use the registry's UI to explore versions.

## Canonical sources

1. https://opentofu.org/docs/intro/whats-new/#opentofu-modules
2. https://opentofu.org/docs/cli/commands/init/