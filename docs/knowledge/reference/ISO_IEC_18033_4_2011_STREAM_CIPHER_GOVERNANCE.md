# ISO/IEC 18033-4:2011 Stream Cipher Governance

## Purpose

ISO/IEC 18033-4:2011, "Information technology — Security techniques — Encryption algorithms — Part 4: Stream ciphers," specifies stream cipher mechanisms that can be used to protect the confidentiality of data. The standard defines stream cipher primitives (SNOW 2G, SNOW 3G, MUGI, KNOT, DECIM, and ZUC among them in the 2020 amendment), and the construction modes of operation. This article governs the application of ISO/IEC 18033-4 so stream cipher usage follows the standard's structure.

## Scope

The standard applies to any organization using stream ciphers for confidentiality protection. Within this knowledge base, the article covers the stream cipher primitives, the construction modes (counter mode, OFB, etc.), the IV/nonce requirements, and the documentation of the stream cipher usage. It does not cover block ciphers (readers should consult ISO/IEC 18033-3 for those); stream ciphers and block ciphers have different requirements for IVs and authentication.

## Workflow

1. Establish the stream cipher policy: scope, algorithms, modes, the relationship to the broader encryption policy, and the authentication requirements.
2. Select the stream cipher primitive appropriate to the context (SNOW, ZUC, ChaCha20). Confirm the primitive is approved for the deployment context (regulatory, sector).
3. Apply the primitive in a construction mode (CTR, OFB) using a unique IV/nonce per operation per the mode's specification.
4. Add authentication to the stream cipher output: an HMAC over the ciphertext, or use an authenticated mode (GCM is for block ciphers; for stream ciphers, use ChaCha20-Poly1305, AES-GCM, or an explicit MAC).
5. Manage the key lifecycle per the project's key management policy.
6. Document the primitive, the mode, the IV/nonce management, the authentication, and the use of the ciphertext.

## Controls and evidence

Stream cipher controls include the documented algorithm, the key management, the IV/nonce management, the authentication, and the integrity controls. Each encryption should be traceable to the primitive and the key used.

## Validation

Validation should confirm the stream cipher is correctly implemented, the key management follows the policy, the IV/nonce is unique per operation, the authentication operates, and the ciphertext is used appropriately. Test vectors confirm the implementation.

## Failure correction

Common failure modes: IV/nonce is reused (correct: enforce uniqueness per key); stream cipher is used without authentication (correct: add an explicit MAC or use an authenticated combination); the primitive is deprecated or weak (correct: replace with an approved primitive); key management is not aligned with the policy (correct: apply the controls of ISO/IEC 11770-1).

## Limitations

ISO/IEC 18033-4 specifies the stream ciphers; it does not certify any implementation. The standard does not address every stream cipher; readers should select primitives appropriate to the context. The standard does not replace block ciphers (AES-GCM is often preferred for new designs); stream ciphers are most useful where the stream cipher primitive is required for interop or for hardware reasons.

## Scope note

This article summarizes project-neutral reference use of ISO/IEC 18033-4:2011 (with the 2020 amendment). It does not assert any specific implementation's conformance or claim any certification outcome.

## Canonical sources

- ISO/IEC 18033-4:2011 — Information technology — Security techniques — Encryption algorithms — Part 4: Stream ciphers: https://www.iso.org/standard/54580.html
- ISO/IEC 18033-4:2011/Amd:2020 — Stream cipher amendments: https://www.iso.org/standard/76386.html