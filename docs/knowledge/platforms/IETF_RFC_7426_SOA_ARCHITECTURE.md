# IETF RFC 7426 Service-Oriented Architecture

## Purpose

IETF RFC 7426, "Service-Oriented Architecture (SOA) Reference Architecture," defines the foundational vocabulary and structural decomposition for service orientation. Although it is a decade old, it remains the authoritative IETF reference for distinguishing service, capability, contract, and orchestration, and it provides the conceptual model that most managed-service documentation implicitly uses. Platform teams that govern APIs, microservices, and managed services benefit from a common vocabulary that survives changes in implementation technology.

## Scope

RFC 7426 is a vocabulary and reference architecture, not a protocol, deployment guide, or technology prescription. It pairs naturally with RFC 8255 (network service manifests), RFC 8322 (L2VPN service models), and ISO/IEC 22123 (cloud reference architecture).

## Core model

The reference architecture defines eight core concepts:

- **Service**: a mechanism to enable access to one or more capabilities.
- **Capability**: the ability to effect a change in the state of the world.
- **Resource**: a physical or software component that delivers a capability.
- **Service description**: the information needed to use the service.
- **Consumer**: the entity that uses the service.
- **Provider**: the entity that delivers the service.
- **Contract**: a specification of how the consumer and provider agree to interact.
- **Policy**: a set of conditions on the use, delivery, or behavior of a service.

Each concept is intentionally abstract. The reference architecture explicitly avoids committing to SOAP, REST, gRPC, or any specific binding.

## Service description and contract

A service description tells a consumer what the service does and how to invoke it; a contract adds the agreement between consumer and provider about how the service will be delivered. Conflating the two is a common defect. The description is documentation that can be re-read; the contract is an agreement that can be enforced.

## Composition and orchestration

Composition describes how capabilities are combined into a new capability. Orchestration describes how a coordinator invokes composed capabilities to deliver a result. In managed-service platforms, orchestration is typically the responsibility of the platform or a separate orchestration system, not the underlying services.

## Policy

Policy is the lever that lets a managed-service platform adapt a service to multiple consumers without forking the service code. Policy decisions (rate limits, retries, authn/authz, routing) are applied at a known chokepoint and audited. Without policy, every variation becomes code.

## Engineering workflow

1. For each in-scope service, document the service description, the contract, and the policies applied.
2. For each composition, document the orchestration owner and the failure-handling strategy.
3. Use the eight concepts as headings when reviewing a new service design or a service refactor.
4. When integrating with a partner or provider, translate their vocabulary into the RFC 7426 model before aligning on terms.
5. Re-evaluate the vocabulary when the platform's implementation technology changes; the model should outlast the protocol.

## Controls and evidence

- Service catalog with one row per service, naming the description URL, the contract, and the policies.
- Composition map showing how composed capabilities are orchestrated.
- Policy decision log keyed to services and chokepoints.
- Review log signed by platform and service owners.

## Validation

- Independent reviewer confirms each service has a current description, contract, and policy set.
- A composition exercise verifies that an orchestrated capability fails over per the documented strategy.
- Policy decisions are sampled and verified against the chokepoint code or configuration.

## Failure modes and corrections

- Confusing description and contract — correct by separating documentation (description) from enforceable agreements (contract).
- Hardcoding policy in service code — correct by externalizing policy to a known chokepoint with audit.
- Letting composition become a single monolithic service — correct by re-decomposing capabilities along the natural seams.
- Adopting a new protocol without re-checking the vocabulary — correct by mapping the new protocol to the RFC 7426 concepts before adopting.

## SOA and cloud-native alignment

Modern managed-service platforms frequently claim to have moved "beyond SOA." RFC 7426 remains useful precisely because the concepts survive the implementation churn. A Kubernetes deployment with a service mesh is still describable as a set of capabilities exposed as services, with contracts (the mesh policy), consumers (client workloads), and policies (the mesh and gateway rules). Teams that keep the vocabulary can compare a REST service, a gRPC service, and a message-driven service on equal footing, which vendor terminology often obscures.

## Governance implications

Because the model separates contract from implementation, it supports a governance posture where:

- consumers depend on contracts, not implementations, so providers can replace the implementation without renegotiating;
- policies are visible and auditable at named chokepoints rather than distributed invisibly through code;
- compositions are documented artifacts that can be reviewed, diffed, and rehearsed; and
- retirement of a service is a contract-level decision with a migration path for consumers, not a code-level deletion.

## Limitations

- The reference architecture is deliberately abstract; concrete protocols change faster than the model.
- It does not specify governance processes; the model is the input to governance, not the governance itself.
- It does not address consumer-side concerns such as data residency or jurisdictional compliance.
- It does not, by itself, prescribe observability, but it implies that policy decisions should be observable.

## Canonical sources

- IETF RFC 7426 (IETF, primary authority) — Service-Oriented Architecture Reference Architecture: https://datatracker.ietf.org/doc/html/rfc7426
- IETF RFC 8322 (IETF, primary authority) — Network Service Models for Layer 2 VPN: https://datatracker.ietf.org/doc/html/rfc8322

## Scope note

This article summarizes project-neutral architecture guidance from RFC 7426. It does not claim that any specific system implements the reference architecture and does not prescribe any particular binding or implementation technology.