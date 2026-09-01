# DANE SMTP TLSA Record Validation

DANE for SMTP inverts the usual certificate story. Instead of asking a browser-style CA whether an MX host's certificate is trustworthy, the receiving domain publishes, in its own DNSSEC-protected zone, a TLSA record stating exactly which certificate or public key is legitimate for that host on that port. RFC 7672 adapts this to mail's opportunistic model: when a validated TLSA record exists, the sending MTA requires TLS and requires the presented certificate to match the record - no downgrade, no cleartext fallback. When no secure TLSA data exists, behavior falls back to ordinary opportunistic TLS. The design deliberately differs from HTTPS DANE: SMTP lacks the "abort on failure" economics of web browsing, so the protocol specifies precisely how senders must degrade, and when they must not.

## Scope

This article covers TLSA validation for SMTP from the sending MTA's perspective and the publishing domain's: record types and meaning, certificate association matching, the fallback rules distinguishing usable from unusable DNSSEC state, and the operational coupling between DNSSEC health and mail delivery. It does not cover DNSSEC key rollover mechanics generally, MTA-STS as the policy-record alternative, or TLSRPT beyond noting which result types surface DANE failures.

## Workflow or implementation guidance

Validation on the sending side is a decision ladder with five rungs, each rung's output determining the next.

1. **Resolve MX over DNSSEC.** Fetch the MX set with a validating resolver and classify the chain Secure, Insecure, or Bogus. Only a Secure chain contributes usable TLSA data. Insecure means the zone is unsigned - proceed with opportunistic TLS and no DANE. Bogus means validation failed, and RFC 7672 treats bogus as unusable data rather than a hard error, a deliberate divergence from HTTPS DANE.
2. **Enumerate candidate TLSA base domains.** TLSA records live at `_25._tcp.<mx-host>`, port and transport prefixed. Expand CNAMEs where present and collect records for each MX host at the delivery port. The MX hostname, not the mail domain, is the naming base - a common misconfiguration publishes TLSA under the domain instead of the host.
3. **Filter by usage and usability.** Discard unusable combinations: usages 0 (PKIX-TA) and 1 (PKIX-EE) additionally require a CA-validatable chain; if either half is absent the record is unusable, not a failure. Usages 2 (DANE-TA) and 3 (DANE-EE) depend only on DNSSEC plus the record itself. If every record is unusable, behavior is opportunistic.
4. **Match on handshake.** When usable records remain, TLS is mandatory. Apply the selector (0 = full certificate, 1 = SubjectPublicKeyInfo) and matching type (0 = exact, 1 = SHA-256, 2 = SHA-512) and compare the computed association data against the presented certificate. Any match among usable records satisfies validation.
5. **Fail or fall back by rule.** No usable TLSA data: opportunistic TLS, cleartext permitted. Usable data but handshake failure or no match: the connection fails and the message defers - never deliver in cleartext past a usable TLSA set. That is the downgrade resistance the mechanism exists to provide.

On the publishing side, the workflow mirrors it: sign the zone, publish `3 1 1` records (usage 3, selector 1, matching type 1 - the SHA-256 of the public key) for each MX host, verify externally with a validating resolver, and sequence certificate changes so the new hash is resolvable before the new certificate is served, with the old record retained through cutover.

## Controls

- Validating resolver infrastructure on all sending MTAs, with monitoring of validation-failure rates per destination zone.
- TLSA publication checklist binding record publication to certificate lifecycle: hash computed from the SPKI, published at `_port._tcp.host`, externally verified before serving.
- Deliberate record-type policy: prefer `3 1 1` for operational simplicity; document any usage-2 trust-anchor decision and the rollover burden it adds.
- Dual-record overlap during certificate rotation, removed only after the old certificate retires from all MX hosts.
- Zone-signing continuity: RRSIG expiry monitoring alerting well ahead of signature lapse, since an expired signature silently removes downgrade protection.
- Queue telemetry classifying "DANE validation failed" separately from ordinary TLS and network failures.
- Scheduled external probes of each published TLSA record from a validating resolver.
- Change-freeze coordination between DNS operators and mail administrators, since neither can act safely alone.

## Validation evidence

- External resolver output showing a Secure chain from the MX set down to each `_25._tcp.<host>` TLSA record.
- A live handshake capture where the sending MTA negotiates TLS and logs DANE validation success against the published hash.
- Negative test: alter the served certificate without updating TLSA and confirm sending MTAs defer rather than deliver, demonstrated in staging first.
- Fallback test: a destination with an unsigned zone where the sender proceeds opportunistically without error classification.
- Bogus-chain test: a deliberately corrupted signature in a test zone treated as unusable, not as a validation pass.
- Rotation rehearsal artifacts showing zero delivery impact across a certificate change with dual publication.

## Failure modes and correction

Mail deferring to a previously working destination with DANE failures logged is most often an expired DNSSEC signature or a stale TLSA hash after certificate renewal - the zone operator changed the certificate without re-publishing the SPKI hash. Publish the matching record; senders recover on the next attempt. Validation succeeding locally but third parties reporting failures suggests split DNS or a resolver path returning Insecure where others get Secure; compare validator outputs from outside your network. Records that never take effect mean TLSA was published under the wrong name - the MX host with port and transport prefixes, not the mail domain. Usage 0 and 1 records appearing ignored are being correctly discarded when the CA half cannot be satisfied; switch to usage 3 if CA validation is not part of the design. A zone-wide validation outage turning all destinations opportunistic points at your resolver infrastructure - alarm on aggregate validation-state shifts. Deferred mail after a DNS provider migration indicates the signing workflow did not survive the move; re-verify the full chain, not just record presence.

## Limitations

DANE's protection is exactly as strong as the DNSSEC chain behind it, and uneven DNSSEC adoption means many destinations have no usable records, leaving those connections opportunistic. The mechanism authenticates the TLS endpoint, not the sender or message content. SMTP DANE cannot signal policy the way MTA-STS can - there is no enforce-or-test mode in the record - so staging is operational discipline rather than a policy field. Hash pinning increases coupling between certificate lifecycle and DNS publishing, trading operational fragility for removal of CA trust; deployments that reissue automatically must automate record publication in the same pipeline. Bogus-is-unusable semantics, necessary for mail's delivery economics, means a validation-infrastructure attack degrades security rather than failing loudly. Middleboxes terminating TLS on behalf of MX hosts break the hash binding unless they serve the exact pinned key.

## Canonical sources

- [RFC 7672: SMTP Security via Opportunistic DANE TLS](https://www.rfc-editor.org/rfc/rfc7672.html)
- [RFC 6698: The DANE Protocol: TLSA](https://www.rfc-editor.org/rfc/rfc6698.html)
- [RFC 8460: SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)
- [RFC 7672 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc7672.html)
- [Postfix TLS Support (DANE security level)](https://www.postfix.org/TLS_README.html)
