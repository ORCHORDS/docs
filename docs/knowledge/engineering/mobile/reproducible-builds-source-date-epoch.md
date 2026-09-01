# Reproducible Builds with SOURCE_DATE_EPOCH

A build is reproducible when the same source input produces bit-for-bit identical output artifacts every time, on every machine. Most builds are not: they stamp wall-clock timestamps into archives, embed random build IDs, order filesystem entries nondeterministically, and capture absolute paths. Reproducible builds close a supply-chain verification gap — if anyone can rebuild your release from source and get the same bytes, then the published binary provably corresponds to the source, and a compromised build machine has nowhere to hide. `SOURCE_DATE_EPOCH` is the community-standard environment variable that makes timestamp-driven nondeterminism deterministic: build tools read it and use its fixed Unix timestamp instead of the current clock. This article covers how SOURCE_DATE_EPOCH works, the tool support landscape, the remaining nondeterminism classes it does not solve, and putting the whole loop together with verification.

## Scope

This article addresses reproducible-build practice centered on `SOURCE_DATE_EPOCH`: the variable's semantics and normalization rules, toolchain support (compilers, archivers, package builders, JS/zip ecosystems), the other determinism requirements (path, ordering, and randomness normalization), and the rebuild-verify loop with tooling. It covers software packaging and release verification. It does not cover hermetic toolchain distribution (Guix/Nix), SLSA provenance frameworks, or reproducible container-image builds specifically except where the same rules apply.

## Workflow or implementation guidance

**What SOURCE_DATE_EPOCH is.** An environment variable holding a Unix epoch timestamp that participating tools use *instead of the current time* for anything they would otherwise stamp: file mtimes inside archives, `__DATE__`/`__TIME__` macro values, gzip/tar headers, embedded build timestamps. Convention rules: the value is a decimal integer; timezone is UTC (a fixed offset avoids locale-dependent rendering of embedded dates); tools that receive non-integer or out-of-range values must fail or fall back deterministically (not silently to the clock) — the normalization rules are part of the spec so every tool interprets the variable identically.

Where the timestamp comes from: the source's own version-control commit date is the canonical choice (`git log -1 --pretty=%ct`), because it makes the artifact depend only on the source tree, not the build machine's clock or the moment of the build. Some projects clamp to a release date or zero; any deterministic rule works, but "commit timestamp" maximizes meaningfulness (the artifact's embedded date tells you which source era produced it).

**Tool support landscape** (the variable plus adjacent flags):

- **C/C++ toolchains**: GCC and Clang honor `SOURCE_DATE_EPOCH` for `__DATE__`/`__TIME__`. Additional nondeterminism must be switched off explicitly: `-frandom-seed` (fix symbol-name randomization), `-fno-record-gcc-switches` (don't embed flags), stable `-ffile-prefix-map`/`-fdebug-prefix-map` rewriting absolute build paths into stable relative ones (the path nondeterminism class).
- **Archivers and package formats**: GNU tar honors the variable for mtimes; gzip's timestamp comes from it when the input stream carries none; `dpkg-buildpackage`/debhelper export it; RPM spec builds embed it; zip tools vary — several honor it, others need flag discipline (`zip -X` to strip extra fields); the Node.js/npm ecosystem's packaging tools adopted it for tarball mtimes.
- **Language ecosystems**: Rust sets build timestamps from it (cargo embeds it where required); Go builds are deterministic modulo `-trimpath` for paths and build IDs derived from content; JVM builds need jar-normalization (strip or fix entry timestamps — build tools accept the variable); JavaScript bundlers vary and often need their own determinism flags for chunk ordering and sourcemap paths.
- **Containers**: layer timestamps must be pinned (`--source-date-epoch`-aware builders or COPY with fixed mtimes); OS package installs inside images bring their own clocks unless the package manager normalizes.

**The other nondeterminism classes SOURCE_DATE_EPOCH does not touch:**

1. **Paths**: absolute build directories leak into debug info and panic messages; fix with prefix-map flags, `--trimpath`-style options, or building in a canonical directory.
2. **Ordering**: parallel compilation writing archives in completion order; directory iteration order feeding file lists; locale-dependent sorting. Fix with explicit sorted iteration (`LC_ALL=C` for collation determinism) and serial final-packaging steps.
3. **Randomness**: temp-file names embedded in outputs, hash-seeded data structures serialized, ASLR-derived values. Fix with fixed seeds and deterministic serialization.
4. **Toolchain drift**: different compiler versions produce different bytes by design. Reproducibility is per (source, toolchain, environment) tuple — pin the toolchain and record it, or the verification rebuild needs the toolchain spec to reproduce.

**The verification loop** — the payoff that makes this worth doing:

1. Build the release artifact normally (CI machine A), record the exact environment: toolchain versions, `SOURCE_DATE_EPOCH` value, flags.
2. Rebuild in a second environment (different machine or clean container, different filesystem paths, different wall clock) with the same recorded inputs.
3. Compare hashes. Equal: the artifact is reproducible from source under the declared toolchain — publish both hash and build recipe. Unequal: diffoscope the two artifacts to localize the first differing byte and its cause (diffoscope recursively unpacks archives and explains differences — the standard tool for exactly this).
4. Publish the recipe: source commit, toolchain identifiers, environment variables, and the expected hash, so third parties can run step 2 themselves. That third-party run is the trust property: the binary is auditable against source.

A worked example: a CLI tool released as a tarball with a compiled binary. Before: rebuilds differed in embedded `__DATE__`, debug paths, and tar mtimes. Fixes: export `SOURCE_DATE_EPOCH` from the commit date in CI; `-ffile-prefix-map=$PWD=.`; `LC_ALL=C`; tar with the variable honored; fixed `-frandom-seed`. The release pipeline now builds twice (primary + verification container), asserts identical SHA-256, and attaches the recipe to the release notes. A security researcher can now rebuild the v1.4.2 binary from the tag and verify their hash matches the published one — supply-chain claims became checkable.

## Controls

- CI builds export `SOURCE_DATE_EPOCH` derived from the commit timestamp in every build job; jobs fail loudly if the variable is unset (an unset variable is the "silently nondeterministic" state).
- Every release artifact is built twice — once in the release environment, once in a clean verification environment — with hash equality asserted before publishing; the verification build's environment spec is archived with the release.
- Determinism flags (prefix maps, trimpath, random seeds, sorted iteration, locale pinning) live in the shared build definition, not per-job scripts, so all artifact types inherit them.
- diffoscope is a standard CI tool: any hash mismatch fails the release with the diffoscope report attached, turning nondeterminism regressions into reviewable diffs instead of mysteries.
- New dependencies and build steps get a reproducibility check in review: "does this introduce clock, path, ordering, or randomness inputs?" — the four classes as the checklist.

## Validation evidence

- The `SOURCE_DATE_EPOCH` specification (semantics, UTC normalization, integer format, fallback rules) is maintained by the Reproducible Builds project and documented at reproducible-builds.org, which also documents per-tool support (GCC/Clang date macros, tar/gzip/zip behavior, dpkg/RPM integration) and hosts the diffoscope and reprotest tooling.
- The broader rationale and threat model (binary-transparency, compromised-build detection) is documented in the project's docs and its sources-to-binary correspondence literature.
- A reproducible check on any project: build twice on one machine separated by minutes (clocks differ), compare hashes; then build once from a different absolute path and compare again — the two experiments isolate the clock class and the path class respectively, telling you exactly which nondeterminism remains before reaching for diffoscope.

## Failure modes and correction

- **Hash mismatch from paths.** Symptom: rebuilds differ only in embedded absolute paths. Correct with prefix-map/trimpath flags and canonical build directories.
- **Mismatch from parallelism ordering.** Symptom: archive entry order varies run to run. Correct by sorted file lists and serial packaging.
- **Toolchain drift.** Symptom: yesterday's recipe no longer reproduces. Correct by pinning and recording toolchain versions in the recipe; version bumps re-run verification.
- **Unset variable slips in.** Symptom: one CI job silently stamps real time. Correct by fail-if-unset guard in shared build scripts.
- **Non-integer/out-of-range values.** Symptom: tools diverge (one fails, one falls back to clock). Correct by validating the value at job start per the spec's normalization rules.

## Limitations

- Reproducibility is relative to a declared toolchain and environment; without publishing that spec, third-party verification cannot run.
- Some ecosystems (JVM jars, JS bundles) need per-tool determinism work beyond the variable; support is uneven and must be audited per artifact type.
- Cross-compilation and host-linked toolchains pull host variability in unless containerized.
- Bit-for-bit reproducibility says nothing about backdoors in the toolchain itself — it moves trust from build machines to toolchain distribution, which also needs verifiable provenance.

## Canonical sources

- Reproducible Builds project, SOURCE_DATE_EPOCH specification: https://reproducible-builds.org/docs/source-date-epoch/
- Reproducible Builds project, documentation hub (tool support, diffoscope, reprotest, verification): https://reproducible-builds.org/docs/
