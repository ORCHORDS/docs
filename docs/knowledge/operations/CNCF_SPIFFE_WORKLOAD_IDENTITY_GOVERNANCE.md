# CNCF SPIFFE Workload Identity Governance

## Purpose

Govern the use of SPIFFE (the Secure Production Identity Framework For Everyone) so that workloads authenticate to each other with cryptographic identity issued at runtime, replacing long-lived shared secrets and static API keys as the basis for service-to-service trust.

## Scope

Applies to every workload enrolled in the studio's SPIFFE/SPIRE infrastructure: identity issuance, SVID usage, trust domain design, and federation. It does not cover human identity (covered by identity and access management) or authorization policy design (covered by API authorization guidance).

## Workflow

1. Design the trust domain structure before enrolling workloads: one or few trust domains, named for the organization or environment boundary they represent, with federation between domains that must trust each other.
2. Enroll workloads through workload attestors that select on workload properties (namespace, label, K8s projected service account token); selection rules are the identity policy and live in version control.
3. Issue SVIDs (SPIFFE Verifiable Identity Documents) with short lifetimes; the default rotation window should leave no operational reason for manual certificate handling.
4. Reference workload identities in authorization policies using SPIFFE IDs (`spiffe://trust-domain/path`), not IP addresses or shared secrets.
5. Federation: register bundle trust between trust domains explicitly, with an owner and review record for each federation; implicit cross-domain trust is prohibited.
6. Monitor SVID issuance and rotation; a workload unable to rotate its SVID must fail closed in mTLS enforcement rather than fall back to plaintext.
7. Audit selection rules on a recurring cadence: any rule that matches more workloads than intended is a mis-issuance risk and is corrected immediately.

## Controls and evidence

- Trust domain design document with federation registry (each entry: peer domain, owner, review date).
- Workload registration entries in version control with selection criteria and reviewers.
- SVID lifetime and rotation configuration per workload class.
- Issuance and rotation monitoring dashboards with alerting on rotation failure.
- Selection-rule audit results with corrections applied.

## Validation

- Sample 10 workload registrations and confirm each selection rule matches only the intended workloads.
- Confirm no production service-to-service authentication depends on shared static secrets for SPIFFE-enrolled paths.
- Confirm rotation failure alerting fires in a test (forced-expiry drill) and the workload fails closed.

## Failure correction

- **Mis-issued SVID (rule too broad)** → revoke the registration, correct the selector, rotate affected SVIDs, and audit what the over-broad rule authenticated.
- **Rotation failure** → the workload must fail closed; investigate the SPIRE agent or registration before re-enabling.
- **Unregistered federation** → remove the bundle trust immediately and review how it was introduced.

## Limitations

- SPIFFE solves authentication, not authorization; policies over SPIFFE IDs provide the authorization layer.
- Attestation strength depends on the platform; selections on mutable properties are weaker than selections on cryptographic workload identity.
- Federation increases blast radius; each federated domain's security becomes your own.

## Scope note

This article is part of the operations leaf and pairs with zero-trust and service-mesh guidance. Cross-reference: `infra/zero-trust-network-access.md`, `infra/kubernetes-network-policies-service-mesh.md`, and `monitoring/service-mesh-observability.md`.

## Canonical sources

- SPIFFE — Specifications: https://spiffe.io/docs/latest/spiffe-about/overview/
- SPIFFE — SPIRE Documentation: https://spiffe.io/docs/latest/spire-hands-on/
- SPIFFE — Federation: https://spiffe.io/docs/latest/architecture/federation/
- NIST SP 800-207 — Zero Trust Architecture: https://csrc.nist.gov/publications/detail/sp/800-207/final
- mTLS — NIST SP 800-52 Rev 2, Guidelines for the Selection and Use of Transport Layer Security (TLS) Implementations: https://csrc.nist.gov/publications/detail/sp/800-52/rev-2/final
