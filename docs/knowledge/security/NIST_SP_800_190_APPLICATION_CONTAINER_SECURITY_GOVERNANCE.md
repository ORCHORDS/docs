# NIST SP 800-190 Application Container Security Governance

## Purpose

NIST SP 800-190, *Application Container Security Guide*, is the United States National Institute of Standards and Technology (NIST) Special Publication that consolidates security recommendations for container technologies, including container images, image registries, orchestrators, hosts, and the container runtime. It was finalized in September 2017 and remains the canonical U.S. government reference for container-security engineering in production systems.

This article describes a governance pattern for applying the SP 800-190 control families across the container life cycle. It does not assert compliance with any specific compliance regime or replace the publication itself.

## Scope

SP 800-190 addresses the full container stack:

- container images, including their contents, configuration, and supply chain;
- registries that store, distribute, and version images;
- orchestrators such as Kubernetes and its peers, which schedule workloads and enforce policy;
- hosts running container runtimes; and
- the runtime itself, which includes the operating-system-level isolation that containers rely upon.

It does not by itself cover serverless platforms, micro-VMs, or unikernels, although many of its principles transfer. It also does not supersede SP 800-144 (public cloud computing) or platform-specific guidance; apply it alongside those publications as appropriate.

## Workflow

A reusable SP 800-190 program runs continuously across the image and runtime life cycle.

1. **Define the threat model.** Document what is in scope, who can submit images, what runtime isolation is in use, and what trust boundaries exist between cluster components.
2. **Establish image-procurement rules.** Allow only images from approved registries, with defined provenance. Distinguish first-party images from third-party and base images.
3. **Harden the build pipeline.** Use reproducible builds where practical, generate signed artifacts, and record metadata for traceability.
4. **Standardize configuration.** Apply a baseline configuration to images, runtimes, and orchestrators. Treat per-deployment overrides as exceptions.
5. **Scan and test continuously.** Combine vulnerability scanning, configuration scanning, and runtime testing. Treat scan errors and missing scans as unassessed states.
6. **Segment and isolate.** Use orchestrator features (namespaces, network policies, pod security standards) to enforce isolation between workloads and between tenants.
7. **Monitor and respond.** Aggregate orchestrator, runtime, and host logs. Detect anomalies and react.
8. **Reassess on change.** Re-evaluate when images, orchestrators, control planes, or the cluster's network exposure change.

## Controls and evidence

SP 800-190 organizes its recommendations into layers. A program should map its controls to each layer and retain evidence accordingly.

| Layer | Example controls | Example evidence |
|---|---|---|
| Image | Minimal base, signed builds, no embedded secrets, vulnerability scan before promotion | Build records, signing logs, scan reports, SBOMs |
| Registry | Access control, signing verification, retention, integrity protection | Registry ACLs, signature-verification logs, retention policy |
| Orchestrator | RBAC, network policies, admission control, secret management | RBAC review, policy manifests, admission controller logs |
| Host | Hardened operating system, restricted runtime, minimal attack surface | Host configuration scans, runtime audit logs |
| Runtime | Isolation boundaries, seccomp/AppArmor profiles, resource limits | Profile manifests, runtime audit, resource-limit verification |

A container-security program should retain at minimum:

- the registry and image provenance policy, with the responsible role;
- the build pipeline configuration and provenance records for each deployed image;
- the most recent vulnerability and configuration scan outputs;
- the orchestrator RBAC and network-policy manifests in force;
- any exception, with reason, approver, compensating control, and expiry; and
- incident records involving a container image, registry, orchestrator, host, or runtime.

## Validation

Validation confirms the container program is operating as documented. Useful activities include:

- selecting a sample of running workloads and confirming that the deployed image digest matches the recorded digest in the registry;
- attempting to run an unsigned or unscanned image and confirming it is blocked;
- reviewing orchestrator RBAC and network policies for over-permissive rules;
- running a Kubernetes or CIS benchmark scanner and addressing high-severity findings;
- confirming that workloads cannot reach unintended namespaces or external endpoints; and
- reviewing a sample of recent deployments for compliance with the build pipeline.

Validation must distinguish compliant, non-compliant, and unable-to-assess states. Workloads for which image provenance cannot be verified should not be silently treated as compliant.

## Failure correction

When a container-security control fails, follow a documented path.

1. Confirm the failure against the live cluster rather than only the dashboard.
2. Identify the layer at which the failure occurred and any contributing layers.
3. Apply the corrective change through the change management process.
4. Verify with new evidence rather than a closed ticket.
5. Update the relevant baseline, policy, or build-pipeline configuration if the issue is systemic.

Common failure modes include:

- using a base image maintained by an upstream community without scanning and signing rules of its own;
- granting cluster administrators privileges that exceed what the role requires;
- treating "latest" as a version pin in production deployments;
- configuring network policies that default to allow;
- storing secrets in container images or environment variables instead of using the orchestrator's secret store; and
- relying on vulnerability scanners without enforcing their blocking rules at admission.

## Limitations

SP 800-190 is dated relative to several platform developments that have become operationally important, including:

- micro-VMs and confidential containers, which require platform- or vendor-specific guidance;
- admission control and supply-chain controls standardized through projects such as Sigstore, in-toto, and SLSA, which should be paired with the publication's recommendations; and
- managed container services whose control planes are partially operated by the provider, requiring a shared-responsibility model that the publication does not specify in detail.

The publication also describes an *expected* control set, not a normative mandate. Programs should pair its recommendations with a current CIS Benchmark or Kubernetes hardening guide appropriate to the orchestrator version in use.

## Canonical sources

- NIST SP 800-190 — *Application Container Security Guide*, final, September 2017: https://csrc.nist.gov/pubs/sp/800/190/final
- NIST DOI mirror for SP 800-190: https://doi.org/10.6028/NIST.SP.800-190
- NIST Computer Security Resource Center — Application Container Security landing page: https://csrc.nist.gov/publications/detail/sp/800-190/final

## Scope note

This article summarizes reusable governance practices derived from SP 800-190. It is not a substitute for the NIST publication, does not assert conformity with any U.S. federal requirement, and does not constitute professional advice on a specific orchestrator, cloud platform, or runtime.
