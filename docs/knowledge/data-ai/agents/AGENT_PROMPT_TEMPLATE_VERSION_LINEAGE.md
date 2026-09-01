# Prompt Template Version Lineage with SLSA-Grade Provenance

## Scope

Prompt templates have become release artifacts with security consequence, yet most organizations manage them with less rigor than a stylesheet. A template that changes a tool-selection heuristic, relaxes an output constraint, or reorders an instruction hierarchy can alter agent behavior as profoundly as a code change, while bypassing code review entirely. When an incident occurs, the first question is what the agent was actually instructed to do at 14:02 on the affected day, and most teams cannot answer it.

This article applies supply-chain provenance discipline, modeled on the SLSA framework's build levels, to prompt template lifecycle. The goal is a verifiable chain from approved template source through transformation to the exact template instance used in a given run. SLSA itself targets build integrity for software artifacts; here its structure is borrowed as a governance pattern, which is a design analogy rather than a claim of SLSA certification.

## Workflow or implementation guidance

1. Store templates as source in a versioned repository, not as editable rows in a production database. One template per file with metadata declaring identifier, version, owner, intended model family, and variable schema. The repository commit is the root of the lineage chain.
2. Define the build as a real transformation step: variable interpolation, conditional section expansion, localization, and composition of shared fragments. This step must run in a controlled build environment that records inputs and outputs, because provenance that only attests to the source commit says nothing about what interpolation actually produced.
3. Emit a provenance record for every built template artifact. At minimum it should bind the output digest, the source commit and template path, the builder identity, the build invocation identifier, and the parameter defaults or variable values that influenced expansion. Without variable bindings, two runs from the same template version can still differ materially.
4. Pin deployments to artifact digests rather than to version strings. A deployment record should reference the immutable digest of the built template, so a rebuild that produces different bytes creates a new artifact rather than silently replacing content under a stable label.
5. Record consumption at execution time. Every run's audit entry should carry the template identifier, artifact digest, and the interpolated variable values, so behavior can be reconstructed without guessing which of several similarly named templates was active.
6. Segregate authority. Authors propose changes through review; only the release pipeline can sign or attest built artifacts; only the deployment controller can promote a digest to production. No single identity should be able to author a template, build it, and promote it without an independent check.
7. Plan for rollback as a first-class operation: promotion of a previously attested digest, recorded as a new deployment event with a reason code, not as a revert of repository history that destroys the record of what was live in between.
8. When templates are assembled from shared fragments or retrieved dynamically, provenance must cover the fragment set. A chain that attests the parent template but permits arbitrary fragment substitution at load time has a gap exactly where an attacker would prefer to act.

## Controls

Require two-person review on template changes that alter tool permissions, output handling, or instruction hierarchy, and treat those categories as security-relevant by default. Machine-enforce the review requirement rather than relying on convention, because convention degrades exactly under deadline pressure.

Make the build environment hermetic enough that outputs are reproducible from the same inputs. Reproducibility is what allows an investigator to rebuild a historical artifact and compare digests; a build that embeds timestamps or environment-specific values into the template text defeats this. Where nondeterminism is unavoidable, it must be recorded in the provenance record rather than discovered later.

Control the attestation signing key in a managed keystore, rotate it on a schedule with documented overlap, and publish the accepted key set per environment. Verify attestation at deployment time and again, cheaply, at load time via digest comparison. Alert on any production run whose template digest has no corresponding attestation, which is the single most useful operational signal in this scheme.

Retain lineage records for an incident-relevant window, with retention aligned to organizational audit obligations. Compress or archive older records, but keep the mapping from any historical run to its template digest resolvable for as long as run records themselves are retained.

## Validation evidence

Lineage evidence should demonstrate the full chain on a real template: a reviewed commit, a build invocation with recorded inputs, an attested artifact digest, a deployment pin, and a production run referencing that digest. Then demonstrate reconstruction: given only the run's audit entry, an investigator retrieves the template bytes, recomputes the digest, and confirms it matches both the deployment record and the attestation.

Tamper evidence is essential. Demonstrate that modifying template source outside the pipeline yields an unverifiable digest at deployment and that the deployment is rejected. Demonstrate that substituting a fragment at load time is detected because the assembled digest no longer matches the attested artifact. Demonstrate that an artifact built by an unaccepted builder identity is refused promotion.

Show rollback integrity: a rollback event that restores a prior digest, is recorded with its own reason, and leaves the intervening period reconstructible. Show key rotation evidence with overlap validation and post-expiry rejection. Finally, show a gap analysis: an inventory of all templates in production with their current digests and attestations, and zero unattested entries.

## Failure modes and correction

The recurring failure is dual-path drift: an emergency fix applied directly to a production template store while the repository lags, leaving the source of record inaccurate. Correct by making the production store read-only to humans, routing emergency changes through an expedited but still attested path, and reconciling drift daily with alerts on any divergence.

A subtler failure is provenance that attests the wrong thing. Records that bind only a version label, or that omit variable values, reconstruct the illusion of lineage without the substance. Correct by binding digests and interpolation inputs, and by testing reconstruction against a run where variables materially changed behavior.

Fragment substitution is the most commonly missed gap. If dynamic composition is genuinely required, attest the assembled result per composition rather than only the static parts, or restrict fragment sources to an attested set with digest pinning. Where attestation gaps are discovered, freeze affected templates, rebuild and re-attest from known source, and investigate any runs that consumed unverifiable artifacts during the gap window.

## Limitations

Provenance establishes what was built and deployed, not whether the template content was wise. It cannot detect a semantically harmful change that was properly reviewed and attested. Reproducibility depends on build hermeticity and is brittle in polyglot toolchains. The scheme adds latency to template iteration, which teams will route around unless the fast path is genuinely usable. Attestation verification also does not protect against a compromised build platform, which is precisely the threat class that motivated higher SLSA levels and that requires hosted-build hardening beyond this article's scope.

## Canonical sources

- **SLSA, Supply-chain Levels for Software Artifacts (framework and build levels):** https://slsa.dev/
- **SLSA, Provenance attestation model v1.0:** https://slsa.dev/spec/v1.0/provenance
- **SLSA, Build track levels v1.0:** https://slsa.dev/spec/v1.0/levels
