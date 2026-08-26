# works-on-my-machine-systematic-root-causes

**Issue:** "Works on my machine" is treated as a punchline or a developer quirk, but it is a reproducibility defect with a short, well-understood list of systematic causes: environments that differ in tool versions, system libraries, dependency resolution, ambient state, and undocumented setup steps. The 2025-era reproducibility writing (DevBox/Nix-style declarative environments, the PEP 665 lock-file saga in Python, container-practice threads) converges on the same diagnosis: loose version ranges and transitive dependency drift mean two machines legitimately resolve different builds from the same manifest; differing OS libraries and base-image drift mean the same code behaves differently; and undocumented setup steps mean the working machine's magic never transfers. Worse, containers were sold as the fix and instead relocated the problem — "works in my container" fails the same way when base images float and nothing is pinned. The compounding organizational cause: when the reproducible path is slow or painful, developers bypass it, so the drift is manufactured continuously by the tooling itself.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The root causes, ranked by frequency

1. **Loose version ranges resolve differently over time.** A manifest that says `^2.x` or `>=1.0` produces a different dependency tree today than it did last month — a fresh install on machine B is not the same software as machine A's install from three weeks ago. This is the number-one cause, and it is invisible because both machines are "correct."
2. **Transitive dependencies drift underneath you.** Even with your direct deps pinned, their dependencies may float; the lock file (not the manifest) is the only artifact that pins the full tree. Ecosystems without a standard lock format spent years relitigating this — Python's PEP 665 saga exists precisely because manifest-only reproducibility failed in practice.
3. **System libraries and OS differences change behavior.** glibc versions, OpenSSL builds, icon sets, filesystem case-sensitivity, and line-ending handling differ across dev machines and CI runners; native extensions link against whatever the host provides. The code is identical; the platform it binds to is not.
4. **Base-image and toolchain drift.** `FROM node:latest`, an unpinned Dockerfile base, or a toolchain (compiler, SDK manager, dev runtime) that auto-updates means the build artifact itself varies by machine and by day. "Works in my container" is "works on my machine" with extra packaging.
5. **Ambient state and undocumented setup steps.** The working machine carries env vars in a shell profile, a hosts-file entry, a local database in a weird state, a manually installed tool, or a config file someone edited in 2023 — none of it in version control, all of it load-bearing. The setup that was never written down cannot be repeated, only reincarnated by luck.
6. **The reproducible path is slow, so it gets bypassed.** When the sanctioned build takes 25 minutes or the pinned environment is painful to update, developers take the local shortcut — and each bypass widens the gap between what's committed and what works. Tooling friction is not a neutral inconvenience; it is an active generator of drift.

## Containers shifted the problem, didn't solve it

1. **Unpinned bases reintroduce the machine.** A Dockerfile that floats its base image means two developers (or two CI runs) build from different filesystems; the container is portable exactly as far as its bottom layer is pinned — digest-pinned, ideally, not tag-pinned.
2. **Bind mounts and "dev in container, run on host" hybrids leak the host back in.** When source is mounted in and tools run partly outside, host differences (file watching, line endings, permissions, resource limits) re-enter through the mount. The container boundary must actually contain the build for it to mean anything.
3. **Multi-stage builds can quietly differ per stage.** A builder stage that floats while the runtime stage is pinned still ships different compiled output; pinning the layers that *produce* artifacts matters as much as pinning the ones that run them.
4. **The same image on different kernel/VM features behaves differently.** ARM vs x86 emulation, missing kernel features (inotify limits, seccomp profiles, cgroup versions) produce "identical image, different behavior" — the residual gap containers cannot close, which only declarative environments and honest CI parity can.

## The reproducibility stack that actually works

1. **Lock files, committed and enforced.** A lock file (package-lock, yarn.lock, poetry.lock, Cargo.lock, go.sum) committed to the repo and required in CI (install with `--frozen`/`--locked`) is the minimum viable defense — the full transitive tree, resolved once, identical everywhere.
2. **Pin the base image by digest, not tag.** Tags are mutable pointers; digests are content. Every FROM line in every Dockerfile should be digest-pinned or generated from a single controlled source that is bumped deliberately, with the bump visible in review.
3. **Declarative, shareable dev environments.** Dev containers, Nix flakes, or DevBox-style pinned tool definitions move "what's installed on the machine" into version control — the setup steps stop being tribal memory and become a file that CI and every new hire execute identically.
4. **One artifact, promoted everywhere.** The binary/image that CI tests is the binary/image that staging and prod run — never re-resolved, never rebuilt from source per environment. Reproducibility of the build plus immutability of the artifact closes the loop.
5. **CI parity checks.** A periodic job that builds the same commit twice (or on two runners) and compares hashes turns silent non-reproducibility into a red build. Reproducible builds are a property you can continuously test, not a hope.

## Treating it as a system problem, not a person problem

1. **Every "works on my machine" ticket is a bug against reproducibility.** File it: what differed, which layer (manifest, lock, base, host state), and fix that layer. Teams that treat each instance as trivia accumulate a permanent tax of debugging roulette; teams that fix layers watch the class of bug go extinct.
2. **Make the reproducible path the fast path.** Aggressive layer caching, remote build caches (Turborepo/sccache/cachenix-style), and prebuilt dev environments remove the incentive to bypass. The battle is won when the sanctioned way is also the quickest way.
3. **Onboard via the declarative environment only.** If a new machine can be productive by running one bootstrap command, undocumented setup cannot accumulate; if it can't, the gaps revealed on day one are the exact drift that would have been next month's mystery bug.
4. **Blame the environment, verify with evidence.** The debugging move that works: reproduce the failure in a clean environment (fresh checkout, fresh container, frozen install). If it fails there too, it's a real bug; if it passes, diff the environments — the difference is the bug, and the diff is the fix.
