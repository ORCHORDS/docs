# Sender Rewriting Scheme SRS Deployment

Forwarding breaks SPF by construction. A message authored at `user@example.org`, forwarded by your service, arrives with your forwarding server in the connecting IP - SPF evaluates against your infrastructure and fails against the author domain. The Sender Rewriting Scheme resolves this by rewriting the envelope sender at the forward step into an address under the forwarder's own domain, carrying the original sender inside a cryptographically protected encoding. Bounces then flow to the forwarder, which decodes, verifies integrity, and re-emits them toward the original sender - restoring accountability while keeping SPF aligned with the connecting infrastructure. Deployed correctly, SRS is nearly invisible; deployed casually, it manufactures unreplyable addresses, misdirected bounces, and a spam-amplification surface through its rewritten addresses.

## Scope

This article covers SRS deployment on forwarding infrastructure: the SRS0 and SRS1 address forms, the rewriting and bounce-verification workflow, key management, and the integrity obligations that keep rewritten addresses from being forged. It is aimed at operators of forwarding services, alias providers, and mailing platforms re-emitting third-party mail. It does not cover DKIM preservation through forwarding, ARC sealing, VERP as an alternative pattern, or DMARC policy interpretation, though each interacts with the envelope decisions SRS governs.

## Workflow or implementation guidance

**Rewrite at the forward boundary.** When re-emitting a message whose envelope sender is outside your domain, replace MAIL FROM with an SRS0 address of the form `SRS0=HHH=TT=domain=localpart@forwarder.example`, where `TT` is a timestamp bucket, `domain` and `localpart` encode the original sender, and `HHH` is a keyed hash over the preceding components. The hash is what prevents third parties from fabricating addresses your bounce processor will honor.

**Time-bound validity.** The timestamp bounds how long a rewritten address remains usable for bounce return. Set the window generously - bounces arrive days late - but finitely, since an unbounded lifetime turns every rewritten address into a permanent replayable token. Weeks to a month is a common ceiling, encoded coarsely to keep addresses short.

**Handle SRS1 for chained forwarding.** When you forward a message already carrying an SRS0 envelope from a prior forwarder, do not nest a second SRS0; collapse instead into `SRS1=HHH=first-forwarder==TT=domain=localpart@your-domain`, preserving the original sender and first hop's identity in one layer. Chained SRS0 nesting grows addresses without bound; SRS1 exists so a second forwarder can re-protect an already-rewritten address while the bounce still routes home.

**Verify on bounce receipt.** Mail arriving at your SRS namespace should only ever be bounces - messages with a null reverse-path. Recompute the hash, check the timestamp window, and only then re-emit toward the encoded original sender, stripping the SRS machinery from headers. A hash mismatch or expired timestamp means forgery or staleness: discard, never bounce the bounce, and log the attempt.

**Never rewrite headers.** SRS is envelope-only. From:, Reply-To, and the DKIM signatures over them pass through untouched; rewriting header addresses destroys DKIM and buys nothing, since receivers evaluate SPF against the envelope.

**Rotate keys safely.** The hash key is the forgeability boundary. Rotate on a schedule, retaining the prior key for verification through the address-validity window, since addresses minted under the old key must verify until they expire.

## Controls

- Rewrite trigger scoped strictly to outbound re-emission of third-party envelope senders; first-party mail keeps its own envelope.
- Keyed hash over timestamp, domain, and local part with a secret never shared across services; dual-key overlap during rotation covering maximum address lifetime.
- Bounce-only acceptance on the SRS namespace: non-null reverse-path arrivals rejected; null-path verified then relayed or discarded.
- Timestamp validity window documented and tested; expiry is silent discard with logging, never an outward bounce.
- Address length budget: monitor rewritten lengths, since downstream systems impose local-part limits and SRS1 chains grow.
- SRS1 collapsing rule enforced in code: second-hop rewriting never produces nested SRS0.
- Hash-failure rate monitoring as a forge-attempt signal.
- Logging mapping each rewritten address to the originating forwarding transaction for abuse reconstruction.

## Validation evidence

- Round-trip test: forward a message, bounce against the rewritten envelope, and confirm the bounce decodes, verifies, and reaches the original sender with correct headers.
- Tamper test: modify one character of an SRS0 address and confirm discard with a hash-failure log entry.
- Expiry test: mint an address aged beyond the window and confirm discard behavior.
- Chain test: forward an already-SRS0'd message through a second hop, confirm SRS1 form, and verify a bounce through both layers returns to the original sender.
- Key-rotation drill with dual-key verification and zero bounce-processing failures across the overlap window.
- Null-path enforcement test: a non-bounce message to an SRS address is rejected.

## Failure modes and correction

Bounces vanishing instead of reaching original senders is the highest-impact failure; when discard logs show hash failures on legitimate traffic, the usual cause is a second service sharing the SRS namespace with a different key - consolidate keying or namespace per rewriting service. Rewritten addresses bouncing as undeliverable at intermediate systems point at length limits; shorten time encodings or reconsider SRS1 chains. Spam arriving to fabricated SRS addresses that your system re-emits toward third parties is the forgeability failure the hash prevents - its presence means the key leaked or the hash dropped a component; rotate immediately. First-party mail rewritten unnecessarily inflates SRS volume and misattributes accountability; tighten the trigger to third-party envelopes only. Expired-address discards clustering after key rotation indicate the overlap was shorter than address lifetime; hold dual keys for the full maximum validity. Non-bounce traffic reaching bounce-processing logic - a forged sender submitting mail with an SRS envelope - is stopped by null-path enforcement; its absence in logs means that control is not wired to the inbound path.

## Limitations

SRS repairs SPF evaluation and bounce routing; it does nothing for DKIM breakage caused by body modification, which forwarding services address by not modifying signed content, or by ARC for evidence preservation. DMARC evaluates the visible From domain, so SRS does not make forwarded mail pass DMARC - receivers apply their own indirect-mail handling. The scheme depends on receivers bouncing to the envelope sender; systems that bounce to header addresses bypass the construction. Address rewriting leaks the existence of forwarding relationships into observable envelope traffic. Timestamp windows trade bounce reachability against replay resistance, and no setting optimizes both. SRS1 chain handling varies across implementations, and second-hop interoperability is weaker in practice than the primary path.

## Canonical sources

- [RFC 7208: Sender Policy Framework (SPF)](https://www.rfc-editor.org/rfc/rfc7208.html)
- [RFC 5321: Simple Mail Transfer Protocol (envelope and null reverse-path)](https://www.rfc-editor.org/rfc/rfc5321.html)
- [RFC 3464: Delivery Status Notifications](https://www.rfc-editor.org/rfc/rfc3464.html)
- [Postfix: Address Rewriting README (envelope manipulation context)](https://www.postfix.org/ADDRESS_REWRITING_README.html)
- [M3AAWG best practices and published documents](https://www.m3aawg.org/published-documents/)
