# random-seed-control-deterministic-tests

**Issue:** The suite uses randomized inputs — property-based generators, `faker` data, hash-map iteration order, shuffled test ordering — and it fails on CI on Tuesday. The rerun passes. Nobody can reproduce the exact sequence of random draws that produced the failure, so the bug report says "flaky" and the test gets quarantined, even though the test found a real defect. The fix is not to remove randomness (randomized inputs find edge cases humans never write) but to make randomness reproducible: inject, log, and re-inject the seed. This article covers seed plumbing across test frameworks, informed by the ICST 2022 empirical study "To Seed or Not to Seed?", reproducible-builds.org's randomness guidance, and current property-based-testing practice.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The core mechanism: seed in, seed out

1. **Every pseudo-random draw in a test process comes from an RNG whose state is fully determined by its seed.** Re-running with the same seed replays the identical sequence — the same generated values, the same shuffle, the same sampled branches. Reproducibility is therefore a plumbing problem: get one seed into every RNG at test start, and get it out of the process on failure.
2. **Derive one root seed per run, and derive per-test seeds from it deterministically.** Either fix the root seed (simple, but every run explores the same space — fine for regression, useless for discovery) or draw it from entropy (exploration), then compute each test's seed as `hash(rootSeed, testId)` so tests stay independent and any single test can be re-run in isolation with its exact seed. Never let tests share one rolling RNG: parallel execution then makes even a fixed root seed irreproducible.
3. **Print the seed in the failure message, not just the logs.** The failure output must contain `seed=127` (or the property-based runner's equivalent, e.g. fast-check's failing path output) inline with the reproduction instructions; a seed buried 4,000 lines up in CI logs does not exist as far as a tired engineer is concerned.
4. **Support re-injection as a first-class knob.** `SEED=127 pnpm test -- -t "cart"` should work, as should the framework's native mechanism (Vitest `--sequence.seed`, pytest `--randomly-seed`, fast-check's `seed`/`path` parameters recorded on failure). If the only way to replay a failure is a debugger session, the feature is unfinished.
5. **Reseed per test, not per module or per session alone.** The ICST study of seed usage in the wild found ad-hoc, module-level seeding is the dominant practice and is exactly what breaks under parallelization and test filtering; per-test derivation survives `-t` filtering, sharding, and reordering.

## Where randomness hides in a test suite

1. **Property-based generators.** fast-check, Hypothesis, jqwik all run with internal RNGs; all record the failing seed/path on failure and accept them back on rerun. Hypothesis additionally keeps a example database so previously-failing shrunk cases replay automatically — do not delete that database in CI cache scrubbing.
2. **Test-data generation (`faker`, `@faker-js/faker`).** Faker has a `seed()` method; a shared factory that seeds from the per-test seed makes every generated record replayable. Without it, a failure involving generated names/emails/UUIDs cannot be reconstructed (see `faker-js-test-data.md` for the data side).
3. **Collection iteration order.** `Object.keys`, `for...in`, HashMap iteration, and Set ordering vary by engine and insertion history; code whose behavior depends on them fails "randomly" with no seed to capture. The defense is sorting before iteration in production code paths where order leaks into output — a seed cannot save you from nondeterminism that is not RNG-based.
4. **Parallel scheduling and shared-mutable state.** Which interleaving a race takes is not RNG-controlled and cannot be seeded — and neither is current time, timezone, DNS order, or remote responses; inject clocks (`jest-timer-fakes.md`, `playwright-clock-controlled-time-tests.md`) and mock transports so the seed is the ONLY source of variability left. If a test only fails under parallelism, chase the shared state (see `shared-test-state-antipatterns.md`) before blaming the generator.

## Discovery mode vs regression mode

1. **Run CI in exploration mode: root seed from entropy, printed on every run.** This turns CI into a continuous fuzzer over input space — every merge attempt samples new cases. The ICST 2022 study's central finding is that seeded-random usage determines how much of this value teams actually capture; unseeded randomness finds bugs that then die as "unreproducible flake."
2. **Run the failing-test rerun in replay mode: inject the printed seed, disable shuffle randomization if it interferes.** One run explores, the next run reproduces. The workflow is only two commands if the knobs exist (document them in the repo README next to the test commands, not in a wiki).
3. **Promote discovered failures into deterministic regression tests.** The property-based runner's shrinking gives you a minimal case; freeze it as an explicit example-based test (fast-check's `.example()` reuse or a plain unit test with the literal values). A bug that only ever reproduces through a live seed will regress silently.
4. **Do not fix the root seed globally in CI to "stop the flakiness."** It converts the suite into a regression-only suite while giving the illusion that randomized testing is still happening; the first time deployment config changes the code path, the fixed seed's coverage silently diverges from reality. If determinism is required (e.g., snapshot comparisons), scope it to the tests that need it and comment why.

## Debugging a seed-reproducible failure

1. **Reproduce locally first, then shrink.** Re-run with the seed on the exact commit CI used; if it does not reproduce locally, suspect environment differences (parallelism, timezone, CPU-architecture float behavior) rather than the seed itself — and write down which, because that difference is itself a finding.
2. **Log the draws, not just the seed, when a failure occurs.** A `onFail` hook that dumps the generated inputs (fast-check `reporter`, or your factory's per-test artifact) turns a seed into a stack of concrete values, which is what you actually want in front of you while debugging.
3. **Bisect over the seed space when the failure is input-dependent and rare.** If reruns with fresh seeds fail at, say, 1 in 200, run a batch of N seeded runs in CI on the suspect commit range; a scripted loop over seeds is a poor man's statistical bisect and much cheaper than arguing about whether the test is flaky.
4. **Separate "test is flaky" from "test found a rare bug" explicitly in triage.** A seed-reproducible failure is BY DEFINITION not flaky — the same inputs deterministically break the code. Only unseeded, unexplainable variance earns the flaky label and the retry policy (see `flaky-test-detection.md`, `test-retry-strategies.md`); the seed printout is the deciding evidence.
5. **Guard the seed plumbing itself with a meta-test.** A test that forces a known seed, runs a generator, asserts the exact output, and asserts that a different seed yields different output protects the reproducibility machinery from silent breakage during dependency upgrades — the one test whose job is to verify all the others can be debugged.

## Related

- `flaky-test-detection.md` — classifying variance; seeds are the dividing line between flake and bug
- `property-based-testing-fast-check.md` — generator design and shrinking this article's plumbing supports
- `faker-js-test-data.md` — seeding generated fixture data
- `test-retry-strategies.md` — what retries may and may not paper over
