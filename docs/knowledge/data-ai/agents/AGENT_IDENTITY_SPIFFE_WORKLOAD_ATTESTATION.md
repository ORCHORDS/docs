# Agent Identity with SPIFFE Workload Attestation

## Purpose

An agent process needs an identity that represents the running workload, not merely the machine, deployment name, or human who initiated it. SPIFFE defines a workload-identity model in which a trust domain issues SPIFFE IDs and verifiable identity documents to workloads. This is useful for agent runtimes that call tools, delegate work, or communicate across services: policy can be attached to an authenticated workload identity rather than to a reusable API key embedded in configuration.

A SPIFFE ID is a URI such as `spiffe://example.org/agents/research`. It is a name, not a credential. A workload proves control of that identity with a SPIFFE Verifiable Identity Document (SVID), commonly an X.509-SVID or JWT-SVID. The SPIFFE Workload API lets a workload obtain short-lived SVIDs and trust bundles without carrying a bootstrap secret. The node and workload attestation mechanisms behind the API determine which identity may be issued.

## Implementation workflow

1. Define trust domains around real administrative and security boundaries. Do not assume that two domains with similar DNS names trust each other.
2. Create a registration policy that maps attested workload properties—such as orchestrator namespace, service account, image identity, or process attributes—to one narrowly scoped SPIFFE ID.
3. Make the local Workload API available only through the platform-supported endpoint. The agent should request its identity from that endpoint rather than reading a long-lived private key from an environment variable.
4. Configure the agent transport to use X.509-SVIDs for mutual TLS, or use JWT-SVIDs only where bearer-token semantics and audience validation are appropriate.
5. Authorize the authenticated SPIFFE ID at every tool or peer boundary. Authentication establishes identity; it does not grant permission by itself.
6. Consume updated SVIDs and trust bundles continuously. Rotation must not require an agent restart, and new outbound connections should use current material.

## Controls

Treat selectors and attestation evidence as security-sensitive inputs. Registration entries should be reviewed like authorization policy, because an overly broad selector can cause several workloads to receive the same identity. Keep production and test identities in separate trust domains or under policy boundaries that prevent accidental cross-use.

For X.509-SVID authentication, validate the certificate chain against the correct trust-domain bundle and verify the expected SPIFFE ID. Do not substitute a DNS-name check for SPIFFE identity validation. For JWT-SVIDs, validate signature, expiry, issuer rules, and the audience intended for the receiving service. A recipient must not accept a token minted for another audience.

Do not log private keys, complete JWT-SVIDs, or Workload API responses. Logs may include the SPIFFE ID, trust domain, validation outcome, and non-secret certificate serial or expiry information where operationally useful. Apply least privilege to local access to the Workload API, since a process able to impersonate the workload at that endpoint may obtain its credentials.

## Validation and evidence

Test identity issuance using both positive and negative attestation cases. A correctly selected agent instance should receive the intended SPIFFE ID; a process with a changed service account, namespace, image selector, or node status should not. Capture the registration-entry review, attestation result, issued identity, and authorization decision as evidence without retaining secret key material.

Exercise rotation by shortening credential lifetimes in a test environment. Verify that established behavior follows the selected transport policy, new connections use renewed SVIDs, and trust-bundle updates are observed. Test federation explicitly: a remote trust domain should be accepted only when its bundle and policy are configured, and an unconfigured domain should fail authentication.

## Failure handling

If the Workload API is unavailable, distinguish temporary inability to renew from loss of a valid identity. Continue only while an existing SVID remains valid and policy permits; never extend its expiry locally. Stop opening privileged sessions before expiry leaves insufficient time to complete them. If validation fails because the bundle is stale or the peer identity is unexpected, fail closed, preserve diagnostic metadata, and avoid falling back to unauthenticated transport or a shared secret.

A suspected attestation-policy error requires disabling or narrowing the affected registration entry, terminating sessions authenticated under the unintended identity where feasible, and reviewing authorization logs for misuse. Credential rotation is not enough if the mapping itself remains too broad.

## Canonical sources

- SPIFFE, *SPIFFE Identity and Verifiable Identity Document*: https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/
- SPIFFE specification, *SPIFFE ID*: https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE-ID.md
- SPIFFE specification, *X.509-SVID*: https://github.com/spiffe/spiffe/blob/main/standards/X509-SVID.md
- SPIFFE specification, *JWT-SVID*: https://github.com/spiffe/spiffe/blob/main/standards/JWT-SVID.md
- SPIFFE specification, *Workload API*: https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE_Workload_API.md
