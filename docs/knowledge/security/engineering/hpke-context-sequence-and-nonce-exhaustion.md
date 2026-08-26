# HPKE context sequence and nonce exhaustion

**Issue:** An HPKE sender or recipient context is stateful. Its per-message AEAD nonce is `base_nonce` XOR the current sequence number, initially zero, and the sequence advances for every successful operation. Cloning, rolling back, concurrently racing, or reusing a sender context can repeat a nonce under the same key and destroy AEAD security.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Give each HPKE context one direction and one serialized owner: sender contexts encrypt only, recipient contexts decrypt only.
- Do not copy, snapshot-and-restore, fork, or share a live sender context across processes or threads.
- Pair each sender context with the matching recipient context and define ordered delivery; applications are responsible for keeping their sequences aligned.
- Treat a failed recipient open as terminal or follow a reviewed recovery protocol; the RFC increments the recipient sequence only after successful authentication.
- Fail closed before sequence overflow and rotate to a fresh HPKE setup well before the AEAD message limit.
- Bind required protocol metadata into AAD and version the ciphersuite, mode, public-key identity, application context, and framing.
- Store long-term keys separately from ephemeral context state and never log keys, base nonces, exporter secrets, or plaintext.
- Use one-shot setup per message when concurrency, random access, retries, or crash recovery cannot preserve a single ordered context safely.

## Implementation and tests

Wrap `Seal` and `Open` so sequence access is serialized and hidden from callers. Generate golden vectors for several messages, then test dropped, duplicated, reordered, tampered, and concurrent ciphertexts. Assert nonce uniqueness and sequence alignment without exposing production keys.

Use a reduced-limit test context to force the final valid message and overflow error. Test process restart, retry after an ambiguous send, recipient authentication failure, sender/recipient role misuse, context clone detection, key rotation, and AAD mismatch. Any design that can resend with rolled-back context state must establish a new context instead.

## Gotchas

HPKE encryption is unidirectional. It does not provide message ordering, replay detection, durable sequence storage, multi-sender coordination, or application framing automatically. AEAD authentication failure does not authorize skipping arbitrary sequence values.

Sequence overflow must raise an error. A larger integer in application code does not expand the nonce space defined by the selected AEAD.

## Official sources

- [RFC 9180: Hybrid Public Key Encryption—Encryption and decryption](https://www.rfc-editor.org/rfc/rfc9180.html#name-encryption-and-decryption)
- [RFC Editor: RFC 9180 status and errata](https://www.rfc-editor.org/info/rfc9180/)
