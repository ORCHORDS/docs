# RFC 9057 ARC and the Abstract MDA

Forwarding infrastructure sits in an awkward position in modern email authentication: a mailing list or alias service receives authenticated mail, modifies it in ways that break SPF and DKIM, and re-emits it looking worse than spam. ARC (Authenticated Received Chain, RFC 8617) answers this by letting each mediator cryptographically record what it saw and what it did. A useful way to reason about where sealing belongs is the abstract MDA - the Mail Delivery Agent role RFC 5598 defines in the Internet Mail Architecture as the module effecting formal delivery into the recipient's environment. One numbering caveat up front: RFC 9057 itself is titled "Email Author Header Field" and defines an Author: field for preserving original authorship through mediators - a sibling mechanism to ARC, not the ARC specification; the chain protocol described here is RFC 8617. Both address authentication damage caused by intermediaries, and the abstract-MDA framing clarifies why sealing belongs where a trust boundary is crossed, not at every internal hop.

## Scope

This article covers ARC sealing on forwarding infrastructure: the relationship between the abstract MDA role and the sealing decision, what an ARC set contains, how receivers establish trust in a chain, and the operational duties of a sealer. It addresses forwarders that seal and receiving MDAs that evaluate seals. It does not cover DKIM key management fundamentals, DMARC policy evaluation, or content filtering strategy.

## Workflow or implementation guidance

**Step 1 - Classify the hop.** Map your infrastructure onto the RFC 5598 roles and identify which component is the abstract MDA for the boundary in question. The sealing point is the component that accepts mail from outside your authority and hands it to delivery. Internal MTAs within the same ADMD should not seal: each seal adds header bulk and DNS cost without adding a trust boundary.

**Step 2 - Authenticate on receipt.** Before any modification, run SPF, DKIM, and DMARC evaluation and capture the results in an Authentication-Results header exactly as an ordinary receiver would. This snapshot becomes the ARC-Authentication-Results of your seal, and its honesty is the entire value of the chain - downstream evaluators trust your attestation about what you saw.

**Step 3 - Perform mediation.** Apply whatever modifications the service legitimately makes: footer injection, subject tagging, envelope rewriting, header reordering. Order matters - the ARC-Message-Signature covers the message as re-emitted, so edits must complete before signing.

**Step 4 - Emit one ARC set.** Add, in order: ARC-Authentication-Results with an instance number, ARC-Message-Signature over the modified message, and ARC-Seal over all prior ARC headers including your new set. Exactly one of each per instance, instance numbers incrementing by one. With no existing chain, your set is instance 1.

**Step 5 - Publish keys and monitor.** The sealing domain's DNS must publish the public key under the selector referenced by ARC-Seal, as DKIM does. Monitor for resolution failures, key mismatches, and clock skew, because an unverifiable seal is indistinguishable from a broken chain.

On the receiving side, the evaluator walks the chain from instance 1 upward, verifying each seal and signature, computes a validation state - none, fail, pass - and applies local policy mapping trusted-sealer domains to bounded authentication adjustments.

## Controls

- Seal exactly once per boundary crossing; never seal internal hops within one ADMD.
- Snapshot authentication results before modification, never after; retroactive AAR content destroys attestation value.
- Continuous instance numbering: refuse to extend chains with gaps or duplicates rather than sealing over them.
- Key hygiene equal to DKIM: dedicated selector namespace, scheduled rotation, dual publication during cutover.
- Chain length ceiling to bound header growth and DNS cost.
- Sealer allowlist at receivers: unlisted sealers get chain information but no policy benefit.
- Timestamp tolerance windows absorbing modest clock drift across infrastructures.
- Verification-failure monitoring broken out by instance number, localizing whether damage is at your boundary or upstream.

## Validation evidence

- Test vectors: replay a captured three-hop forwarded message and confirm instance numbers, signature coverage, and seal chain verify with a second implementation.
- Tamper test: modify a body byte after sealing and confirm downstream evaluation reports the chain invalid rather than partially trusted.
- Authentication-snapshot fidelity: compare AAR content against an independent verifier's results for the same inbound message.
- Key rotation drill with zero seal-verification failures across the cutover.
- Trust-policy test at a cooperating receiver: a passing chain produces the agreed local outcome; a failing chain does not.
- Growth measurement of header bytes and DNS queries per message as chain depth increases.

## Failure modes and correction

The most common defect is sealing after the fact - generating the AAR from post-modification state, producing chains that verify but attest to nothing. Fix the pipeline order: authenticate, modify, sign, seal. Seals failing downstream usually trace to a DNS race during selector rotation; publish and confirm the new selector before switching the signer. Instance-number corruption from an intermediate stripping headers is corrected by refusing to extend a broken chain - reseal from instance 1 only if you can re-authenticate honestly. Receivers granting ARC too much authority will pass mail whose only credential is a chain from an unknown sealer; enforce an explicit allowlist and treat chain state as one input among reputation and content. Clock-skew failures are addressed by NTP discipline first, widened tolerance second.

## Limitations

ARC remains Experimental, and receivers deploy it unevenly; a perfectly valid chain can be ignored by much of the receiving population. The chain attests handling, not intent - a competent spammer can seal too, so trust must come from sealer reputation rather than cryptographic form. Chain contents leak intermediary domain names and some adjacent evidence, a privacy cost the protocol's own considerations acknowledge. Nothing about a chain repairs a DMARC failure at the authoritative domain; ARC preserves evidence so the receiver can make a better-informed local decision, and RFC 9057's Author: field addresses a different slice of the problem - author identity rather than handling history - with equally uneven adoption. Evaluation cost grows with chain depth, creating a denial-of-service surface the controls mitigate but do not eliminate.

## Canonical sources

- [RFC 8617: The Authenticated Received Chain (ARC) Protocol](https://www.rfc-editor.org/rfc/rfc8617.html)
- [RFC 9057: Email Author Header Field](https://www.rfc-editor.org/rfc/rfc9057.html)
- [RFC 5598: Internet Mail Architecture (abstract MDA, MTA, MSA roles)](https://www.rfc-editor.org/rfc/rfc5598.html)
- [AuthIndicators Working Group (ARC and BIMI) GitHub organization](https://github.com/authindicators)
- [RFC 8617 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc8617/)
