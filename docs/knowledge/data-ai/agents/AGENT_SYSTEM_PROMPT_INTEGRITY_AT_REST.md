# System Prompt Integrity at Rest Using Web Cryptography Primitives

## Scope

System prompts, instruction hierarchies, guardrail text, and few-shot exemplars are configuration artifacts with security consequence. An attacker who can modify a stored prompt can redirect tool use, weaken refusal behavior, or open an exfiltration path, all without touching application code. Most deployments protect prompts no better than any other row in a configuration table, and few can answer the question of whether the prompt that executed this morning is byte-identical to the one that was approved.

This article covers integrity protection for prompts at rest: hashing for change detection, signatures for origin authentication, and key handling appropriate to a browser-based or server-side agent host. The W3C Web Cryptography API defines the primitive operations available in browser contexts, and the same discipline transfers to server keystores. Integrity is deliberately scoped separately from confidentiality; hiding a prompt is a different and weaker goal than proving it has not changed, and conflating the two produces false assurance.

## Workflow or implementation guidance

1. Treat every prompt artifact as a versioned, reviewable object. Store the prompt text, a semantic identifier such as purpose and audience rather than a bare filename, owning team, approval record, and effective date. Integrity controls on an unversioned blob protect nothing because any change is indistinguishable from legitimate editing.
2. Compute a cryptographic digest over the canonical byte representation at write time. Canonicalization must be explicit and documented: fix the encoding, normalize line endings deterministically, and define whether trailing whitespace is significant. Most integrity failures in practice are canonicalization disputes rather than cryptographic breaks.
3. On load, recompute the digest and compare against the stored value before the prompt enters the model request path. Fail closed on mismatch: abort the run, quarantine the object, and alert. Never fall back to a cached copy without applying the identical check to that copy.
4. Separate detection from attribution. A digest proves the prompt is unchanged but not who changed it. For attribution, wrap the digest in a signature produced by a key held by the approval authority, so the runtime verifies both that the prompt matches its approved content and that the approving authority signed it.
5. In a browser host, use the Web Cryptography API for both operations: `crypto.subtle.digest` for integrity checking, and `crypto.subtle.importKey` with `verify` for signature validation. Keys for verification are public and can be embedded or fetched with integrity metadata; signing keys must never be present in the browser.
6. On the server, keep signing keys in a managed keystore or hardware-backed module with non-exportable key material, and restrict signing to the release or approval pipeline. Interactive human edits should produce unsigned draft states that cannot execute until the signing step runs.
7. Bind integrity to execution. Record the verified digest in each run's audit entry, alongside model identifier, tool set revision, and policy revision. Without that binding you can prove the prompt store was intact on average but not which text any particular request used.
8. Rotate verification keys with a defined overlap window where both old and new keys validate, and re-sign the full corpus atomically during rotation. Document the accepted key set per environment so a signature from a test authority cannot satisfy production verification.

## Controls

Access control on the prompt store must be independent of the integrity mechanism: least privilege on write, mandatory review on merge, and no shared service account that both authors and verifies prompts. Change history should be append-only where feasible, with deletion producing a tombstone rather than silent absence, so removal of a guardrail is at least as visible as addition of text.

Rate and audit verification failures. A stream of digest mismatches across many objects is a signal of tampering or of a broken deployment pipeline, and the two require different responses; log enough context to distinguish them. Protect the verification path itself from becoming a denial-of-service vector by caching verified digests for a short, bounded period tied to object revision rather than re-verifying on every request when volume is high.

Keep canonicalization documentation under the same review discipline as the prompts, because a change to line-ending or encoding policy silently invalidates every stored digest. When the store is backed up or replicated, verify integrity after restore; backup pipelines that transcode text are a recurring source of false positives and, worse, genuine undetected modification.

## Validation evidence

Demonstrate the positive case: an approved prompt loads, verifies, and executes, with the verified digest recorded in the audit trail. Then demonstrate the negative cases: a single character modification, a whitespace-only change under the documented canonicalization, an encoding change, a truncated object, a prompt signed by an unaccepted key, and a prompt with no signature at all. Each must fail closed with a distinct, logged reason.

Show key lifecycle evidence: rotation performed with overlap, old keys rejected cleanly after expiry, and a test authority signature rejected in production. Show restore evidence: a backup restored and verified, including at least one restore where a deliberate pre-backup corruption is detected rather than silently healed.

Finally, show execution binding: given an audit entry, a reviewer can retrieve the exact prompt bytes, recompute the digest, and confirm it matches the recorded value and the stored signed object. If that reconstruction is not possible end to end, the integrity system is documentation rather than control.

## Failure modes and correction

The most common failure is a mismatch storm after a legitimate pipeline change that altered canonicalization or re-encoded text. Correct by freezing execution on affected objects, determining whether the new bytes are approved content, re-signing if so, and updating canonicalization policy with a migration that re-hashes the entire corpus atomically. Do not respond by loosening comparison to fuzzy matching; that converts an integrity control into a suggestion.

A second failure is silent bypass: verification enabled in one environment and absent in another, or a code path that loads prompts through a cache that skips verification. Correct by making verification the only load path, testing for the existence of unverified load paths explicitly, and failing audits when a run records no digest.

Browser-specific failures include relying on `crypto.subtle` in insecure contexts where it is unavailable, and assuming embedded verification keys cannot be replaced. Treat the browser as an untrusted runtime for signing purposes only; verification in the browser is a tamper-evidence aid, not a guarantee against a fully compromised host, and server-side verification must remain authoritative.

## Limitations

Integrity at rest does not protect a prompt in transit without transport security, does not prevent a compromised runtime from substituting text after verification, and does not establish that an approved prompt is actually safe or effective. Web Cryptography availability varies by context and requires secure delivery. Signature schemes require algorithm agility planning; a fixed choice eventually becomes a migration project. The scheme also does nothing about prompt leakage through model output, which is an orthogonal problem requiring separate detection and containment controls.

## Canonical sources

- **W3C, Web Cryptography API:** https://www.w3.org/TR/WebCryptoAPI/
- **W3C, Verifiable Credentials Data Model v2.0 (integrity and proof mechanisms):** https://www.w3.org/TR/vc-data-model-2.0/
- **OWASP Cheat Sheet Series, Secrets Management (key handling discipline):** https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
