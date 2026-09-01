# IETF RFC 8255 Network Service Manifests

## Purpose

IETF RFC 8255, "Network Service Headers (NSH) — Service Function Chaining (SFC) Architecture," defines a control-plane and forwarding model for chaining network services. While most platforms do not run NSH themselves, RFC 8255 is the authoritative baseline for the concept of a service manifest — a structured declaration of the services that apply to a flow — and it influences how platforms document and govern service-chaining decisions in API gateways, service meshes, and managed-service offerings.

## Scope

The publication addresses service function chaining (SFC), the metadata that travels with a flow, and the control-plane elements that interpret it. It is not a deployment guide for any specific SFC implementation, nor does it prescribe a particular forwarding plane. It pairs with RFC 7665 (SFC problem statement) and RFC 8300 (NSH encapsulation).

## Manifests as a governance tool

A service manifest is a structured declaration of which services apply to which flows, in what order, with what policy. Manifests let platform owners review and approve service chains before they are deployed, audit changes to those chains, and reproduce chains for incident analysis. The governance value comes from making the chain explicit, version-controlled, and reviewable — not from any specific format.

## Metadata flow

RFC 8255 defines metadata that accompanies a flow through the chain. The metadata is interpreted by SFC-aware service functions (SFFs, SFs) and is updated by them. The chain is consumed in order, with the possibility of failure handling and re-routing. For governance, the metadata model implies that the manifest must be complete enough to reconstruct the chain from the documentation alone.

## Control-plane responsibilities

The reference architecture identifies several control-plane elements:

- **SFC classifier**: assigns flows to chains based on policy.
- **SFC forwarder (SFF)**: forwards flows along the chain.
- **Service function (SF)**: performs the actual packet processing for a chain step.
- **SFC controller**: programs the classifier and the forwarders based on the manifest.

Each element has a distinct responsibility; conflating them is a common defect in vendor implementations.

## Engineering workflow

1. For each in-scope service chain, document the manifest with the chain order, the SFs involved, the classifier rules, and the failure-handling policy.
2. Version the manifest in source control; review manifest changes through the same process as code changes.
3. Verify that the runtime classifier and forwarder state matches the manifest; treat drift as an incident.
4. Rehearse failure handling by killing a step in the chain and confirming the failure-handling policy fires.
5. Re-evaluate the chain after any SF upgrade or replacement.

## Controls and evidence

- Manifest repository with versioned, reviewed chains.
- Classifier and forwarder state exports that can be diffed against the manifest.
- Failure-handling runbook per manifest.
- Chain-change tickets tied to manifest revisions.

## Validation

- Independent reviewer diffs runtime state against the latest manifest.
- At least one failure-handling exercise per quarter exercises a real failure path.
- Manifest version and runtime version are reported in dashboards and verified after every deployment.

## Failure modes and corrections

- Treating the manifest as a documentation artifact rather than a configuration artifact — correct by versioning the manifest in source control and reviewing it like code.
- Letting classifier rules drift from the manifest — correct by re-syncing rules whenever the manifest changes and alerting on drift.
- Hiding failure handling in service-function code — correct by externalizing failure handling to the control plane.
- Skipping chain-change review — correct by requiring a manifest diff and a reviewer approval before runtime changes.

## Manifest content checklist

A reviewable manifest should record at least:

- the chain identifier and version;
- the ordered list of service functions with their identifiers and versions;
- the classification rules that assign traffic to the chain;
- the metadata elements carried on the flow and which functions may read or write them;
- the failure-handling policy per hop (bypass, retry, terminate, or re-route);
- the ownership of each service function; and
- the rollback path to the previous manifest version.

A manifest lacking any of these cannot be fully audited and should not be promoted to production.

## Manifests beyond NSH

The manifest discipline generalizes. API gateways, service meshes, ingress controllers, and managed WAF offerings all implement chain-like behavior where a request traverses an ordered set of policy-enforcing components. The same governance applies regardless of the underlying technology:

- the chain must be declared in a versioned artifact;
- changes must be reviewed and traceable;
- runtime state must be verifiable against the declaration; and
- failure handling must be explicit and rehearsed.

Teams that treat these chains as console configuration rather than manifests lose the auditability that the reference architecture is designed to provide.

## Limitations

- RFC 8255 is a reference architecture; the SFC ecosystem has multiple competing implementations.
- Some implementations do not expose all of the metadata described in the RFC; review the implementation's scope before assuming compliance.
- It does not address the cross-domain case where multiple operators contribute to the chain.
- It does not, by itself, define security controls; pair with the relevant control catalog and threat model.

## Canonical sources

- IETF RFC 8255 (IETF, primary authority) — Network Service Header (NSH) — Service Function Chaining (SFC) Architecture: https://datatracker.ietf.org/doc/html/rfc8255
- IETF RFC 7665 (IETF, primary authority) — Service Function Chaining (SFC) Architecture: https://datatracker.ietf.org/doc/html/rfc7665

## Scope note

This article summarizes project-neutral use of RFC 8255 as a manifest-governance baseline. It does not claim that any specific SFC implementation is RFC-compliant and does not prescribe any particular chain format.