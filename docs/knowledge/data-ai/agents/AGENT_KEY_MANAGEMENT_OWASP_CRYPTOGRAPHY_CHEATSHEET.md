# Key Management for Agent Services from the OWASP Cryptography Cheatsheet

## Purpose

Agent systems need cryptographic keys for transport security, request signing, evidence integrity, workload identity, encrypted memory, secret retrieval, and signed approvals. OWASP’s Cryptographic Storage and Communication Security Cheatsheets provide baseline guidance on choosing algorithms, generating randomness, storing keys, and protecting communications. The cheatsheet is not a substitute for organizational policy, HSM-backed services, or certified protocols, but it gives developers an explicit starting point.

A correct algorithm is not enough if the key, randomness source, or distribution path is weak. A uniform policy that ignores workload context tends to misclassify keys, place secrets in model context, or embed them in image layers.

## Implementation workflow

1. Inventory cryptographic uses by protection objective: confidentiality of data at rest and in transit, integrity of evidence and prompts, authentication of services and workloads, non-repudiation of approvals, and key establishment.
2. Choose protocols before algorithms. Prefer authenticated, versioned standards for transport and message security, and prefer vetted libraries over ad-hoc combinations.
3. Select algorithms from current approved suites appropriate to data lifetime and classification. Document hash, symmetric, and asymmetric choices, plus permitted key lengths, modes, and message authentication constructions.
4. Generate keys using an approved random bit generator with sufficient entropy. Reject seeds that reuse weak entropy sources, low-resolution time, or construction-time randomness alone.
5. Store keys in a managed key service or HSM where policy requires. Use envelope encryption for large data and allow independent rotation of data keys and key encryption keys.
6. Separate keys by purpose and trust boundary. Do not reuse the same key for transport, content signing, and approval. Separate production, staging, and test keys, and keep customer-tenant keys in isolated namespaces.
7. Rotate keys on schedule and on incident-driven triggers. Re-encrypt protected data when policy requires retiring the old key. Document revocation procedures and timelines.

## Controls

Do not place raw keys, signed URLs that grant access, or long-lived tokens in model prompts, memory, tool arguments, log files, or environment files readable to the model. Treat the language-model context as low-trust storage and use short-lived, narrowly scoped, auditable credentials that the runtime resolves just before use.

Separate configuration from secrets. Pull secrets from a managed secrets manager through a workload-identity-asserted principal, restrict retrieval by scope, and avoid persisting secrets to disk. Disable persistent plaintext logging of cryptographic inputs and outputs, including signed messages and session identifiers where they act as authorization.

Bound credential scope. A signature key for one tool registry should not authorize another, and a customer data key should not also decrypt administrative secrets. Avoid placing cryptographic trust in pattern-matching around key strings because model output is not a reliable secret retrieval path.

## Validation and evidence

Run negative and positive cryptographic tests. Verify algorithm and key length acceptance, signature verification, AEAD authentication, replay protection, key-derivation determinism for required cases, and correct refusal of weak parameters. Test rotation by exercising the new and old credentials within their overlap window and by ensuring retired keys no longer authorize new operations.

Confirm that cryptographic operations use approved libraries, not custom or model-generated code. Run dependency scans, configuration reviews, and integrity checks for installed artifacts. Verify workload identity assertion before key retrieval to demonstrate that only authorized callers receive material.

Evidence should include algorithm and version inventory, key management topology, rotation history, configuration snapshots, test results, dependency review, and storage access logs. Do not claim FIPS or certification status unless the actual deployment, modules, and procedures fall within the validated configuration; mention only what is verifiable.

## Failure handling

If a key, signed token, or approval evidence is suspected to be exposed, revoke it immediately, scope the investigation to all systems that could have accessed it, and rotate affected data keys with re-encryption of stored material. For tests, use synthetic values rather than reusing production credentials.

If a cryptographic test fails, stop promotion. Determine whether the failure is configuration, library, parameter, or protocol error before re-running. If a managed service is unavailable, define a fallback policy with bounded duration, and avoid the temptation to embed secrets in configuration as a workaround. On algorithm deprecation, schedule migration, monitor for remaining uses, and document compliance windows.

## Canonical sources

- OWASP, *Cryptographic Storage Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP, *Communication Security Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Communication_Security_Cheat_Sheet.html
- OWASP, *Key Management Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html
- NIST, *Recommendation for Key Management* (SP 800-57 Parts 1–3): https://csrc.nist.gov/pubs/sp/800/57
- IETF, *JSON Web Signature* (RFC 7515): https://www.rfc-editor.org/rfc/rfc7515