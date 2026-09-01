# NIST SP 800-145 Cloud Computing Definition

## Purpose

NIST Special Publication 800-145, "The NIST Definition of Cloud Computing," establishes the canonical U.S. federal definition of cloud computing and its five essential characteristics, three service models, and four deployment models. Engineering and procurement teams should use it as the authoritative baseline when classifying a managed service, drafting an architecture decision record, or evaluating vendor claims of "cloud" delivery.

## Scope

The publication provides terminology and conceptual boundaries. It is not a control catalog, reference architecture, risk assessment framework, or compliance program. Programs that need control content should pair it with NIST SP 800-53 (security and privacy controls), NIST SP 800-204 (cloud-native security), and ISO/IEC 27017 (cloud-specific information security controls).

## Essential characteristics

A service is "cloud computing" only when it exhibits all five essential characteristics. A capability missing any single attribute is not, by this definition, cloud computing, even if a vendor markets it as such.

- **On-demand self-service**: consumers provision compute capabilities automatically without human interaction at the provider.
- **Broad network access**: capabilities are available over the network and reached through standard mechanisms used by heterogeneous client platforms.
- **Resource pooling**: provider resources are pooled to serve multiple consumers using a multi-tenant model with physical and virtual resources reassigned dynamically.
- **Rapid elasticity**: capabilities can be scaled out or in, in many cases automatically, to match demand.
- **Measured service**: cloud systems automatically control and optimize resource use by leveraging metering at a level appropriate to the service.

## Service models

- **Software as a Service (SaaS)**: the consumer uses the provider's applications running on cloud infrastructure; the consumer does not manage or control the underlying infrastructure.
- **Platform as a Service (PaaS)**: the consumer deploys onto the cloud infrastructure applications created using programming languages, libraries, services, and tools supported by the provider; the consumer does not manage the underlying infrastructure.
- **Infrastructure as a Service (IaaS)**: the consumer provisions processing, storage, networks, and other fundamental computing resources and can deploy and run arbitrary software; the consumer does not manage the underlying physical infrastructure but may control selected networking components.

## Deployment models

- **Private cloud**: provisioned for exclusive use by a single organization; may be owned, managed, and operated by the organization, a third party, or some combination.
- **Community cloud**: provisioned for exclusive use by a specific community of consumers with shared concerns.
- **Public cloud**: provisioned for open use by the general public.
- **Hybrid cloud**: a composition of two or more distinct cloud infrastructures (private, community, or public) that remain unique entities but are bound together by standardized or proprietary technology enabling data and application portability.

## Engineering workflow

1. Record the candidate service in a registry entry with the vendor, service name, region(s), and claimed service/deployment model.
2. Verify each of the five essential characteristics is present in observable evidence: portal-driven provisioning, public-network access, multi-tenant resource pooling, elastic scaling, and metered usage.
3. Classify the service model by what the consumer controls vs. what the provider controls; document the division of responsibility.
4. Classify the deployment model by tenant boundary and exclusivity; record who owns and operates the infrastructure.
5. Re-evaluate classification when the vendor introduces a new SKU, changes the deployment footprint, or rebrands.

## Controls and evidence

- Essential-characteristic checklist with concrete evidence links (console screenshots, API traces, billing telemetry).
- Division-of-responsibility matrix for each service model in use, cross-referenced to SP 800-53 control families.
- Deployment-model statement with tenancy diagram, network boundary, and customer exclusivity attestation.

## Validation

- Independent reviewer walks the essential-characteristic checklist against current vendor documentation and the live console.
- A second reviewer checks the division-of-responsibility matrix against the actual contract and any statements of work.
- The classification is updated at least annually and after any material service change.

## Failure modes and corrections

- Treating every remote SaaS as "private" because it is single-tenant at the application layer — correct by verifying the underlying cloud deployment model, not the application tenancy model.
- Assuming PaaS excludes any infrastructure responsibility — correct by mapping the provider's documented responsibilities against the consumer's obligations.
- Reclassifying a deployment when one essential characteristic is missing — correct by recording it as "not cloud" under SP 800-145 and using adjacent guidance such as SP 800-204 for managed-service considerations.
- Conflating "cloud" with "any hosted service" — correct by requiring the full five-characteristic evidence chain.

## Limitations

- The definition is a vocabulary, not a security baseline; it does not, by itself, justify any specific control selection.
- It does not specify SLAs, data-residency guarantees, or contractual terms.
- It does not address hybrid topologies that include non-cloud components.
- The line between PaaS and SaaS is intentionally fuzzy where the provider exposes application-level configuration; teams should document the boundary rather than assert one.

## Canonical sources

- NIST SP 800-145 (NIST, primary authority) — The NIST Definition of Cloud Computing: https://csrc.nist.gov/pubs/sp/800/145/final
- NIST SP 800-145 (PDF, primary authority) — full text: https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-145.pdf

## Scope note

This article restates project-neutral terminology from NIST SP 800-145. It does not provide legal, contractual, or compliance advice and does not certify any particular service as "cloud" beyond what the source publication defines.