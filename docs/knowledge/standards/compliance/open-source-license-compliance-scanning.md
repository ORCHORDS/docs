# open-source-license-compliance-scanning

**Issue:** Nearly every product is a stack of transitive open-source dependencies, and each carries a license whose conditions attach automatically on distribution: permissive licenses (MIT, BSD, Apache-2.0) mostly require notice preservation and attribution; weak copyleft (LGPL, MPL-2.0) requires source availability for modified covered files; strong copyleft (GPL-2.0/3.0, AGPL-3.0) can require offering the Corresponding Source of the entire combined work to recipients — and AGPL extends that to users of network services. Courts in the US and Germany have consistently enforced the GPL as both contract and copyright license, no court has ever held it unenforceable, and a California decision suggested even downstream recipients may have standing to enforce. The 2023-2025 relicensing wars (Terraform to BUSL, Redis, Elasticsearch, HashiCorp, Valkey forks, Meta's Llama as an OSI-contested license) mean dependency licenses can change out from under you on a minor version bump. Compliance therefore has to be automated in CI, not rediscovered during diligence.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## License taxonomy that drives obligations

1. **Permissive tier (MIT, BSD-2/3, Apache-2.0, ISC).** Obligations are notice/attribution and (for Apache-2.0) carrying NOTICE files and patent terms; the engineering requirement is a generated attribution bundle shipped with the product — get this right and 80 percent of dependencies are cleared.
2. **Weak copyleft tier (LGPL-2.1/3.0, MPL-2.0, EPL-2.0).** File-level or library-level scope: MPL requires source for modified MPL files only, LGPL requires the ability to relink/replace the library; embedding LGPL code statically into a proprietary binary breaks the terms unless you provide object files or link-time separation.
3. **Strong copyleft tier (GPL-2.0, GPL-3.0).** Distribution of a derivative work triggers Corresponding Source obligations for the whole combined work under the GPL's terms; the derivation analysis (linking, static vs dynamic, process boundaries, "what is a derivative work") is a legal call the pipeline should escalate, not decide.
4. **Network copyleft (AGPL-3.0).** The trigger is interacting with the service over a network, not distribution — running modified AGPL services (e.g., MinIO, Mastodon, older Grafana, Valkey-adjacent tooling) obligates you to offer source to those users; many companies simply prohibit AGPL in runtime dependencies by policy.

## Scanning pipeline design

1. **Generate an SBOM with license fields on every build.** SPDX or CycloneDX with per-component license expressions (SPDX license expression syntax, including exceptions like GPL-2.0-with-classpath-exception), produced by the same tooling as the security SBOM so the two inventories cannot drift; see sbom-generation-distribution-cicd for the SBOM plumbing this builds on.
2. **Fail the build on policy violations.** A deny-list (or allow-list) of licenses enforced in CI, with exemptions as code-reviewed, expiring overrides stored in the repo — the exemption record is your evidence of deliberate risk acceptance rather than accidental inclusion.
3. **Detect license changes on version bumps.** Diff the license field of each dependency against the previous lockfile; when a dependency relocates from Apache-2.0 to BUSL/SSPL/ELv2 (as Terraform and Redis did), the pipeline must block the bump until humans decide — pin and mirror the last-open version in the interim.
4. **Scan more than the package manager manifest.** Vendored source, git submodules, container base images, npm postinstall artifacts, and AI-model weights each carry licenses invisible to lockfile scanners; the container base image scan (Debian/Fedora package licenses) is the most commonly missed surface.
5. **Verify declared licenses against reality.** A package.json saying MIT while files carry GPL headers is a known supply-chain trick; deep-scan tools (ScanCode-style) that read file headers catch declaration mismatches the manifest trusts.

## Distribution-time obligations

1. **Ship the attribution bundle.** Collect all permissive-license notices, copyright lines, and license texts into a generated THIRD-PARTY-NOTICES artifact per distributable (per container image, per CLI binary, per download bundle); regenerating it must be part of the release pipeline, and stale attribution is the most common audit finding.
2. **Offer Corresponding Source for the LGPL/GPL components you modify.** For the (rare, deliberate) cases where copyleft components ship, automate source offer: a signed source tarball URL valid for the statutory offer period (GPL-3.0 requires at least three years), referenced from the product documentation.
3. **Container distribution is still distribution.** Publishing a Docker image to a public registry is conveying; the licenses inside the layers (including base image packages) must appear in the attribution bundle and any copyleft obligations attach.
4. **SaaS changes the trigger set, not the whole analysis.** Pure SaaS distribution of GPL code triggers nothing in GPL-2.0/3.0 — but AGPL triggers fully, and any downloadable agents, CLIs, or SDKs you publish are conventional distributions; segment your product surfaces by distribution mode in the policy engine.

## Governance guardrails

1. **Maintain a decision log for edge cases.** Linking models, "is my plugin a derivative work," and dual-license components (e.g., MySQL client libraries under GPL/commercial) need recorded legal decisions with rationale; when auditors or acquirers ask, the log is the deliverable.
2. **Cover AI-era inputs.** Model weights and training corpora increasingly carry licenses (RAIL, Llama community license, OpenRAIL) with use-based restrictions that are not OSI open source; route model dependencies through the same gate with their own taxonomy, and note the EU AI Act/GPAI documentation duties interact with your provenance records.
3. **Contribution hygiene runs the rules in reverse.** Employee contributions to external GPL projects can leak proprietary code or create IP taint; a lightweight contribution approval step (CLA/DCO sign-off, no company code) closes the loop that scanning only watches inbound.
