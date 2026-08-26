# padding-oracle-attack-cbc

**Issue:** A padding oracle attack is a chosen-ciphertext attack against encryption that uses CBC mode with padded plaintext (PKCS#7) but checks padding validity before verifying authenticity. The server's error behavior — different responses, different status codes, or even different response times between "bad padding" and "bad MAC/content" — becomes an oracle that leaks one bit per query. Vaudenay's 2002 attack and its descendants (POODLE, Lucky13-style TLS oracles, and countless bespoke web decryptors) let an attacker decrypt arbitrary ciphertext without ever recovering the key, typically a few hundred requests per byte. The root cause is architectural: unauthenticated CBC. The industry conclusion, reinforced by Cloudflare's retrospective on the removal of CBC cipher suites from TLS, is that CBC plus a separate MAC is too easy to get wrong; authenticated encryption (AEAD) is the correct default, and legacy CBC code needs explicit interim controls.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Attack Explained

1. **CBC decryption structure.** In CBC mode, each plaintext block is recovered by XORing the decryption of the ciphertext block with the previous ciphertext block (the IV for the first block). An attacker who can modify ciphertext therefore controls the bytes that come out of the XOR, one block at a time.
2. **Padding as the oracle.** PKCS#7 padding says the last N bytes of the final block must all equal N. The server decrypts, checks padding, and then checks content or MAC. If those checks produce distinguishable outcomes, the attacker learns whether a guessed padding byte was correct.
3. **Byte-by-byte recovery.** By systematically mutating the previous ciphertext block and watching which queries yield valid padding, the attacker determines each plaintext byte in at most 256 tries, then repeats per block. Cost is linear and modest — a fully automated process.
4. **Oracles hide in subtlety.** The distinguishing signal can be an explicit padding error, a different HTTP status, a redirect-versus-200 difference, or a timing delta between the padding check path and the MAC check path (the Lucky13 problem in TLS, where MAC-then-encrypt made timing minimization extremely difficult).
5. **It is decryption, not key theft.** The key stays safe; the confidentiality of every ciphertext the attacker can capture and submit is what fails. This is why the fix is about mode and error handling, not key length.

## Where Oracles Appear in Applications

1. **Encrypted cookies and tokens.** Homegrown "encrypt the session cookie with AES-CBC" schemes are the classic web instance: the application decrypts an incoming cookie, errors differently on bad padding versus bad content, and hands the attacker a decryption service for all captured cookies.
2. **Encrypted URL parameters and API fields.** Any endpoint that accepts, decrypts, and reports problems with ciphertext blobs (password-reset tokens, signed links, encrypted IDs) is a candidate; test each with truncated, bit-flipped, and re-padded inputs.
3. **Legacy TLS configurations.** CBC cipher suites in TLS 1.0-1.2 historically exposed timing oracles (POODLE, Lucky13); modern stacks removed CBC suites entirely, so any environment still negotiating them carries known-attack surface.
4. **Message-queue and database field encryption.** Services that decrypt stored blobs and surface distinct error classes to callers replicate the same oracle pattern internally, where a compromised adjacent service can query it.
5. **Custom wrappers around crypto libraries.** The library rarely has the bug; the wrapper that catches BadPadding and converts it to a 400 while other failures become a 500 re-creates the oracle one layer up.

## Primary Defense: AEAD

1. **Use AES-GCM, AES-GCM-SIV, or ChaCha20-Poly1305.** AEAD modes authenticate the ciphertext before any plaintext is released; there is no padding step, so a padding oracle cannot exist by construction.
2. **Let the library handle it.** High-level constructs (libsodium's secretbox, AWS Encryption SDK, Fernet, or the platform AEAD APIs) apply versioning, nonces, and tag verification correctly; hand-assembled Encrypt-then-MAC code is where mistakes breed.
3. **Never release unauthenticated plaintext.** The architectural rule: decryption output must not be acted upon, logged, or branched on until the authentication tag verifies — this single ordering decision kills the entire class.
4. **Fresh nonces under the same key.** AEAD with a repeated (key, nonce) pair is catastrophic; derive nonces per message using library guidance rather than inventing counters or randoms.
5. **Rotate to key-committing constructions where relevant.** For multi-key setups (contexts where the attacker may control which key decrypts), prefer committing AEAD or add a wrapping hash, per recent academic guidance on key-committing AEAD.

## Interim Controls for Legacy CBC

1. **Encrypt-then-MAC ordering.** If CBC cannot be removed yet, compute an HMAC over the IV plus ciphertext and verify it before any decryption attempt; MAC-first ordering removes the padding check from the request path entirely.
2. **Single generic error.** Collapse padding failures, MAC failures, and content failures into one status code, one body, and one code path — distinguishability is the vulnerability, so make the observable behavior identical.
3. **Constant-time failure handling.** Perform dummy work on early failure so timing does not leak which check failed; this is hard to get right, which is exactly why it is an interim control with a deadline to migrate.
4. **Rate-limit and monitor decryption endpoints.** Padding oracle attacks require many structured queries against the same endpoint; per-identity query ceilings and alerts on high 4xx-decrypt-failure rates blunt automated extraction even if an oracle exists.
5. **Retire CBC on a published timeline.** Track CBC usage as an inventory item with an owner and a removal date; oracles get re-introduced when new code copies old patterns, so the pattern must die with the mode.

## Detection and Code Review

1. **Grep for mode red flags.** Search for AES.MODE_CBC, Cipher.getInstance("AES/CBC/PKCS5Padding"), and raw cipher references without an accompanying MAC or AEAD tag — each hit is a review item.
2. **Differential testing.** Submit ciphertexts with corrupted padding versus corrupted MAC versus truncated blobs and diff responses byte-for-byte and in latency; any observable difference is a finding regardless of exploitability today.
3. **Fuzz decryption endpoints.** Include bit-flipped, block-truncated, zero-IV, and re-padded ciphertexts in automated fuzz suites so regressions in error handling surface in CI rather than in an attacker's logs.
4. **Audit encrypted-token formats.** Review every token that a client can submit for decryption (cookies, reset links, encrypted IDs) and confirm each uses AEAD with tag verification before parsing.
