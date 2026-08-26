# build-reproducibility-verification

**Issue:** When something breaks in production, the first forensic question is whether the running artifact was really built from the reviewed source. Most pipelines cannot answer that: rebuilding the "same" commit twice produces different bytes because timestamps, build paths, locale settings, unpinned dependencies, and parallel iteration order leak nondeterminism into the output. That breaks the promote-don't-rebuild deployment model, makes incident forensics guesswork, and allows tampered or locally built binaries to masquerade as CI output. Build reproducibility verification closes the gap by proving that rebuilding the same inputs yields a byte-identical artifact, and by attaching signed provenance so any consumer can verify who built what from which source. The SLSA framework treats bit-for-bit reproducibility as a foundation: provenance confirms the build's lineage, while a verified rebuild independently confirms the artifact could only have come from those inputs.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Sources of nondeterminism

1. **Embedded timestamps.** Compilers, archives, and package managers stamp the current wall-clock time into binaries and metadata. Standardize on SOURCE_DATE_EPOCH, pinning every timestamp in the build to the commit date, so the clock at build time stops influencing the output bytes.

2. **Build paths and host identity.** Absolute paths, temp directories, and hostnames get baked into debug symbols and logs. Run builds in a fixed virtual path (for example, always /workspace) on ephemeral, identically configured runners so machine-specific details never reach the artifact.

3. **Unpinned dependencies.** Floating tags like latest or a loose major-version range resolve to different upstream releases on different days. Enforce lockfiles for every ecosystem, verify digests, and treat a lockfile change as a first-class reviewed diff rather than a build-time accident.

4. **Nondeterministic compilation inputs.** Thread scheduling changes dictionary and archive ordering in some toolchains, and randomized symbol seeds (ASLR keys, hash seeds) end up in output. Use toolchain flags that force deterministic ordering and disable randomization, then prove it with a rebuild rather than assuming.

5. **Toolchain drift.** Different runner images carry different compiler and linker versions, producing different codegen from identical source. Pin the toolchain by digest (container image or hermetic toolchain download) so the builder itself is part of the locked input set.

## Verification techniques

1. **Rebuild-and-compare in CI.** Periodically (and for release builds) check out the exact recorded inputs, rebuild from scratch in a clean environment, and compare digests against the shipped artifact. A matching digest is the strongest evidence the artifact corresponds to its source; a mismatch is a finding, not a curiosity.

2. **reprotest for systematic coverage.** Drive the build under varied conditions — different timestamps, locales, CPU counts, filesystem orderings — to discover hidden nondeterminism before it ships. Anything reprotest flags becomes either a fixed input or a documented, excluded variation.

3. **diffoscope for triage.** When rebuilds differ, byte-level diffs of binaries are unreadable; diffoscope unpacks archives and binaries down to the first meaningful difference, turning hours of hexadecimal squinting into a targeted fix of the one varying field.

4. **Semantic equivalence as a fallback.** Some artifacts (signed jars, reproducible-only-in-principle native builds) cannot reach byte equality. Document an accepted equivalence class — same source, same toolchain digest, same dependency digests, differences confined to a known allowlist — and verify against that allowlist explicitly instead of giving up on verification entirely.

## Provenance integration

1. **Generate SLSA provenance at build time.** Use the build platform's attestation support (GitHub artifact attestations, SLSA GitHub generators, or an in-toto attestation from the CI system) so every artifact ships with a signed statement of source repository, builder identity, and build parameters. The spec expects resolvedDependencies so verification, debugging, and rebuilds all start from the recorded truth.

2. **Verify provenance at deploy and admission time.** Deploy pipelines and cluster admission policies should reject artifacts whose provenance is missing, unsigned, built by an unexpected builder, or pointing at an unexpected source. This is what turns provenance from paperwork into a tamper gate: a locally built binary cannot present a valid CI attestation.

3. **Independent rebuilders for the highest bar.** SLSA Level 4 contemplates a second party rebuilding from source and confirming the published artifact. Few teams need this internally, but critical shared libraries and supply-chain-sensitive components justify a separate account or org performing the rebuild so a single compromised builder cannot forge both the artifact and its verification.

## Pipeline design rules

1. **Build once, promote the digest.** The reproducibility guarantee is wasted if staging and production rebuild independently. Produce one attested artifact, promote the identical digest through environments, and let each environment's gate verify the same provenance rather than re-deriving a possibly different binary.

2. **Deterministic containers.** Apply the same discipline to OCI images: pinned base image digests, fixed build timestamps, sorted file ordering in layers, and no network fetches beyond the locked dependency set. Then a tag move or base-image patch is detectable as a legitimate digest change, not noise.

3. **Verify before sign, sign before publish.** Order the pipeline so the rebuild comparison and provenance verification complete before the artifact is signed and pushed to the registry, ensuring only verified bytes ever become deployable.

4. **Treat a reproducibility break as an incident.** A sudden mismatch between rebuild and shipped artifact means either the build gained hidden nondeterminism or something replaced the artifact. Both demand investigation before the next deploy, not a shrug and a re-tag.
