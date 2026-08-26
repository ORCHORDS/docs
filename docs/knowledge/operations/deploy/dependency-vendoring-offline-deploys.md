# dependency-vendoring-offline-deploys

**Issue:** A deploy pipeline that resolves dependencies live from public registries at build time has two failure modes: an outage or policy change at npm/PyPI/crates.io stops all deploys cold, and an upstream package changing or disappearing silently changes what you build. The historical answer was vendoring — checking dependencies into source control — which lockfiles largely replaced by pinning versions plus integrity hashes. But 2025-2026 practice has revived vendoring in narrower forms: offline mirrors for air-gapped builds, private registry proxies for resilience and policy control, and cargo-vendor-style local registries where the build must not touch the network at all. This article covers choosing between lockfiles, mirrors, and full vendoring, and the supply-chain tradeoffs; supply-chain-security-sbom-signing covers the SBOM and signing side.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What lockfiles do and don't guarantee

1. **Lockfiles pin resolution, not availability.** A lockfile records exact versions and integrity hashes so a rebuild resolves the same packages — but the bytes still come from the registry at build time. Registry down means build down.
2. **Integrity hashes are the real win.** The hash check is what makes lockfiles a supply-chain control: a tampered or replaced package fails verification rather than silently shipping.
3. **Lockfile coverage is ecosystem-dependent.** Ecosystems differ in what gets pinned (transitive deps, native artifacts, container base images); know the gaps — base images and system packages usually need separate pinning discipline.
4. **Lockfiles can rot.** Unmergeable lockfile conflicts push people to regenerate them, which re-resolves everything; CI diff checks that flag wholesale re-resolution keep lockfiles honest.

## Offline and air-gapped builds

1. **Materialize dependencies into the repo or a local store.** Air-gapped environments standardize on vendored sources: `cargo vendor` writes full registry sources into the tree, yarn's offline mirror stores package tarballs, and other ecosystems have equivalents; the build then resolves against local files only.
2. **Enforce offline with a flag, not a hope.** Builds should run with network resolution disabled (cargo `--offline`, frozen-lockfile modes) so a missing local copy fails loudly instead of silently fetching.
3. **Version the mirror contents.** The vendored store is part of the build definition; changes to it go through review like any dependency bump, which is precisely its audit value.
4. **Cache layers separately from vendoring.** CI dependency caches speed builds but prove nothing; if the requirement is reproducibility or isolation, the artifact of record is the lockfile plus mirror, not a warm cache.

## Private registry mirrors

1. **Proxy everything through one internal registry.** An internal npm/PyPI/crates mirror (Verdaccio, Artifactory, a proxying GitHub Packages) is the middle path: builds resolve against the mirror, which caches upstream, so registry outages and rate limits stop blocking deploys.
2. **Mirror policy is security policy.** The proxy is where you allowlist packages, block known-malicious names, and scope internal packages; dependency-confusion protection lives here, not in developer habits.
3. **Decide your upstream risk tolerance.** A pure pass-through proxy adds availability but not immutability; pinning the mirror's cached versions (or snapshotting it per release) is what makes builds reproducible through upstream deletions.
4. **Fail loudly when the mirror is bypassed.** Lock build configs to the mirror's URL and alert on direct-registry traffic from CI; a mirror that anything can bypass is decorative.

## Full vendoring: when it pays

1. **Air gaps and hostile networks.** Regulated or disconnected environments have no registry to reach; vendored sources in the repo are the only resolution mechanism.
2. **Registry risk as threat model.** If a compromised or deleted upstream package is an existential risk for your product — because you ship something others build — vendoring converts that risk into a diff you review.
3. **Small, frozen dependency trees.** Vendoring a handful of critical SDKs is cheap; vendoring a modern JS dependency tree bloats the repo and turns every bump into a giant diff — which is exactly why lockfiles displaced it (Andrew Nesbitt's 2026 "Lockfiles Killed Vendoring" history is the reference).
4. **Use per-ecosystem mechanisms.** Do not invent vendoring: cargo vendor, yarn offline mirror, Go's vendor directory, and pip local indexes each define an expected layout; custom tarball directories rot.

## Operating the mirror

1. **Automate refresh.** Dependabot-style tooling should open mirror-update PRs with changelogs; a mirror updated by hand is always stale, and stale mirrors push people to bypass them.
2. **Test the offline path regularly.** Periodically build from the mirror with upstream unreachable (a CI job with no external egress) — the failure you want is loud and immediate, and you want to find gaps before an outage does.
3. **Measure mirror health.** Alert on cache misses that require upstream fetches during release builds; a rising trend means pinning discipline is decaying.
4. **Keep SBOM generation downstream of the mirror.** The SBOM should describe exactly what the mirror served the build (see supply-chain-security-sbom-signing), closing the loop between what you resolved and what you attest.
