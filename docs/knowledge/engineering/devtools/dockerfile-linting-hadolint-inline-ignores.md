# Dockerfile Linting with Hadolint and Inline Ignores

Dockerfiles accumulate defects that don't fail builds: `latest`-pinned bases that change underneath you, `apt-get upgrade` layers that bloat images and break reproducibility, `ADD` where `COPY` is safer, chained `RUN`s that leave secrets in intermediate layers. Hadolint is a static analyzer for Dockerfiles that checks these against a rule set grounded in Docker's own best-practice documentation. Running it in CI catches the mechanical issues; the harder engineering problem is managing its findings — which to fix, which to justify, and how to silence the rest without muting the signal. This article covers setting up Hadolint, reading its rule families, and using inline ignores with discipline.

## Scope

This article addresses Hadolint usage for Dockerfile quality: installation-independent invocation patterns, the major rule families (base-image tags, apt/apk/apk-cache correctness, ADD versus COPY, chain-of-commands patterns, sudo, ports, healthcheck), configuration via `.hadolint.yaml`, CI integration, and inline ignore pragmas with their risks. It does not cover image scanning for CVEs (Trivy/Grype territory), multi-stage build design, or container runtime configuration.

## Workflow or implementation guidance

Hadolint parses a Dockerfile and emits findings tagged by rule code: `DL` codes are Hadolint's own best-practice checks (e.g., DL3007 warns on `FROM ...:latest`; DL3008 warns on unpinned `apt-get install` versions; DL3018 on unpinned `apk add`; DL3003 warns on `WORKDIR` with relative path switching; DL4006 warns on `SHELL` piped commands in `RUN` with unset pipefail), and `SC` codes are ShellCheck findings run against the embedded shell scripts inside `RUN` lines — the part teams forget: most Dockerfile logic is shell, and Hadolint delegates that half to ShellCheck rules.

A working setup:

1. **Baseline locally.** Run `hadolint Dockerfile` (or `hadolint --config .hadolint.yaml Dockerfile`) and triage the output. Don't start by silencing; start by understanding which rules you violate structurally.
2. **Configure once, centrally.** A `.hadolint.yaml` at repo root sets ignored rules, trusted registries (`trustedRegistries` suppresses DL3026 warnings for your registry hosts), and label schema. Commit it next to the Dockerfiles it governs.
3. **Pin your linter version in CI.** Hadolint rules evolve; a floating `hadolint/hadolint:latest` in your pipeline is the same defect class as `FROM:latest` in your Dockerfile. Use a versioned container or a locked binary, and record the digest.
4. **Run in CI as a blocking check** on every Dockerfile change: `hadolint --failure-threshold warning $(git ls-files '**/Dockerfile*')` — with the threshold chosen deliberately: `error`-only gates too little for most teams; `warning` blocks the rule families that correlate with real incidents (unpinned bases, cache-broken package installs).
5. **Fix by category, not finding-by-finding.** The common violations and their fixes:
   - `FROM node:latest` → pin a specific version tag and ideally digest (`FROM node:22.11@sha256:...`); DL3007 disappears and builds become reproducible.
   - `RUN apt-get update && apt-get install -y curl` → add `--no-install-recommends`, use version pins where practical, and keep `rm -rf /var/lib/apt/lists/*` in the same RUN (DL3008/DL3009): the layer must clean up after itself because later layers cannot shrink earlier ones.
   - `ADD . /app` → `COPY . /app` unless you need tar/URL semantics (DL3020).
   - `RUN cd /app && npm install` → `WORKDIR /app` then `RUN npm install` (DL3003).
   - Long `RUN` chains flagged by ShellCheck (SC2086 unquoted variables, SC2016, pipefail DL4006) → set `SHELL ["/bin/bash", "-o", "pipefail", "-c"]` where pipes exist, quote expansions.
6. **Inline ignores — the controlled escape hatch.** `# hadolint ignore=DL3008` on the line above the offending instruction silences that rule for that line; comma-separate for multiples (`# hadolint ignore=DL3008,SC2086`). Discipline rules:
   - An ignore must carry a justification comment adjacent to it (`# unpinned: distro mirror lacks stable versions; tracked in TICKET-412`) — reviewable reasoning, not reflexive silencing.
   - Never ignore whole rule families globally (`.hadolint.yaml` `ignored`) unless the rule is architecturally inapplicable (e.g., DL4001 warns on `sudo` but your base practice mandates it somewhere specific — that's a line ignore, not a global one).
   - Count ignores in CI as a metric (`grep -rc 'hadolint ignore' Dockerfile*`); a rising count is design debt surfacing.
7. **Multi-stage and build args.** Hadolint checks each stage; `ARG` before `FROM` usage (DL3027 warns on using global ARG after FROM in a confusing way) and copy-between-stages patterns produce their own findings — resolve by structuring stages, not by ignoring.

A worked example: a CI gate upgrades from floating to pinned Hadolint and immediately fails on 40 findings across 6 Dockerfiles. Triage: 28 fix mechanically (pin tags, add `--no-install-recommends`, swap ADD→COPY), 6 are ShellCheck quoting fixes in RUN scripts, 4 need investigation (a package genuinely has no pinned version available — line-ignore with ticket reference), 2 are structural (`sudo` in a legacy base — ignored with justification pending rework). After the pass, the gate blocks at `--failure-threshold warning`, and the ignore count is 6 with justifications — a defensible steady state.

## Controls

- Version-pin (and digest-record) the Hadolint binary/container used in CI; treat linter upgrades as changes requiring review of newly activated rules.
- Require justification comments adjacent to every inline ignore; lint the linter with a script that rejects bare `# hadolint ignore=` lines lacking a second comment or ticket reference.
- Track ignore density per Dockerfile in CI output; trend it in the same dashboard as test skips.
- Review `.hadolint.yaml` changes with the same scrutiny as branch-protection changes — global ignores are the highest-leverage silencer in the system.
- Run Hadolint on a schedule (weekly) against unchanged Dockerfiles: rule updates and registry changes (a pinned tag being re-pushed upstream is not covered, but rule evolution is) surface without waiting for a human to touch the file.

## Validation evidence

- Rule codes, their rationale, the configuration file format (`.hadolint.yaml` keys: ignored, trustedRegistries, label-schema, failure-threshold), and inline ignore pragma syntax are documented in the official Hadolint repository README and docs published on GitHub.
- Docker's own best-practice documentation (Docker Docs — Dockerfile best practices) is the normative basis for most DL rules, which makes findings arguable from first principles rather than style opinion.
- A reproducible check: take a Dockerfile with `FROM alpine:latest`, `RUN apt-get update && apt-get install -y curl`, `ADD . /src`; run the pinned Hadolint; observe DL3007, DL3008-family, and DL3020 findings; fix each as above and observe a clean run — a closed loop validating both the gate and the fix patterns.

## Failure modes and correction

- **Floating linter version.** Symptom: CI flips red on untouched files after an upstream release. Correct by pinning the linter and upgrading deliberately with a rule-diff review.
- **Global rule silencing.** Symptom: `.hadolint.yaml` `ignored` list grows until the gate checks nothing. Correct by policy: global ignores need an architectural justification in the PR description and an owner.
- **Bare inline ignores.** Symptom: `# hadolint ignore=DL3008` copy-pasted down files. Correct by the justification-adjacency check.
- **Treating hadolint as CVE scanning.** Symptom: green lint, vulnerable images. Correct by pairing with a vulnerability scanner in the pipeline; they answer different questions.
- **ShellCheck half ignored.** Symptom: teams fix DL codes, leave SC findings. Correct by failure-threshold and CI messaging that treats SC findings as first-class.

## Limitations

- Hadolint is static: it cannot see build-arg values, base image contents, or runtime behavior; a perfectly linted Dockerfile can still be broken.
- Pinning package versions in `apt-get install` (DL3008) is often impractical on Debian-family bases whose repositories don't expose stable per-package versions — many teams deliberately accept the warning or ignore per line; decide consciously.
- The tool parses Dockerfile syntax families and lags new BuildKit syntax features (`--mount`, heredocs) at times; upgrade to regain coverage.
- Registry digest pinning is beyond lint scope; use a renovate/dependabot-style automation to keep digests fresh once pinned.

## Canonical sources

- Hadolint project, README and documentation (rules, configuration, inline ignores): https://github.com/hadolint/hadolint
- Docker, Dockerfile best practices (the normative basis for DL rules): https://docs.docker.com/build/building/best-practices/
