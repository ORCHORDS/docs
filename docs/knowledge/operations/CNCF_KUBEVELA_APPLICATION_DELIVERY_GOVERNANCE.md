# CNCF KubeVela — Application Delivery Governance

## Purpose

Establish governance on the use of CNCF-hosted KubeVela as the application delivery control plane for multi-cluster / hybrid environments, particularly where an organization requires explicit application-model abstractions (components, traits, policies, workflows) on top of Kubernetes and the surrounding platform tooling.

## Current status

- KubeVela is a CNCF graduated / incubating project as the published governance article is recorded. KubeVela entered the CNCF as an incubating project and progressed within the CNCF's software supply chain / application delivery portfolio.
- The upstream project is authored and maintained as an open-source CNCF project; the canonical repository is hosted under the KubeVela project's GitHub organization.
- Status as of 2026-09-04: KubeVela remains an active CNCF project; the published governance article should be re-checked periodically against the CNCF landscape because project maturity classifications can change.

## Sources

- Primary: CNCF landscape entry for KubeVela — https://landscape.cncf.io/ and the project page within cncf.io.
- Project repository: https://github.com/kubevela/kubevela (canonical source for releases, version tags, and roadmap).
- Documentation site: https://kubevela.io/ (architecture, concepts, tutorials).
- Companion CNCF projects appearing in the same governance record: Argo CD (CNCF_GITOPS_RECONCILIATION_GOVERNANCE family), Crossplane, Open Cluster Management, Flux. KubeVela integrates with these as the application-model layer above them.

## Scope note

KubeVela's distinguishing governance characteristic is its separation of the application model from the delivery mechanism. Adopting programs should understand this separation before reusing KubeVela as if it were just another GitOps engine — it is not. Key concepts to record in governance:

1. Application-as-a-microservice. KubeVela models an application as a composition of components (atomic deployable units, typically wrapping Helm charts, container images, or cloud services) plus traits (cross-cutting runtime concerns such as scaler, ingress, rollout). Adoption should record the allowed component and trait taxonomy.
2. Policy and workflow separation. Policies ("application policies" such as rollout phases, override semantics) and the Workflow specification (the order of operations across environments) are explicit first-class objects. Governance artifacts should enumerate the approved workflow and policy catalog.
3. Multi-cluster delivery primitives. KubeVela's VelaUX and KubeVela CLI workflows target multi-cluster and multi-environment topologies. Records of multi-cluster delivery should reference the cluster registry and topology provider rather than the underlying CNI or container runtime.
4. Continuous Delivery via the addon system. KubeVela uses addons to extend component and trait types. Adding an addon is a governance event because it changes the vocabulary of legal objects in the application model.
5. Existing CNCF ecosystem positioning. KubeVela is positioned above Argo CD (delivery), Crossplane (infrastructure), and policy engines (e.g., OPA/Kyverno). Governance should avoid claiming KubeVela replaces those functions; it is the model and orchestration layer above them.

Operational adoption requires that the application model catalog (allowed components, allowed traits, allowed workflows) be a versioned, signed artifact. Platform teams should publish changes to the catalog with a release note describing capability impact and deprecations. Application teams consuming KubeVela should reference the catalog version they target, not the platform software version, in deployment records.

This article does not cover underlying GitOps implementations (Argo CD / Flux), policy engines (Kyverno / OPA), or infrastructure provisioning tools (Crossplane / Terraform) — each has separate governance articles.
