# SMTP MTA-STS Policy Cache Poisoning Defense

MTA-STS protects inbound mail by letting a domain say, over authenticated HTTPS, "my MX hosts require valid TLS, and only these hosts are mine." Its security model has a well-known soft spot: a sending MTA caches that policy, and an attacker who can corrupt the cached state - or block its refresh - can keep senders pinned to stale or forged policy long after the domain has moved on. Cache poisoning here is not a hypothetical protocol flaw; it is the practical attack surface the design's id rotation, policy-ID comparison, and DNSSEC interplay exist to close. The TXT discovery record at `_mta-sts` is fetched over DNS, the policy document over HTTPS, and the two are glued by a short policy ID. Knowing which piece an attacker must subvert, and what each defense layer contributes, separates an enforced deployment from a decorative one.

## Scope

This article covers defenses against corrupted, forged, or stale cached MTA-STS policy: policy ID rotation discipline, the MX-match rule between DNS and policy, DNSSEC's role in discovery integrity, cache lifecycle management, and failure handling that prevents attackers from weaponizing cache persistence. It is written for operators of sending MTAs (who hold caches) and receiving domains (whose policies are cached). It does not cover initial rollout sequencing, TLSRPT reporting, or DANE as an alternative.

## Workflow or implementation guidance

**Rotation discipline.** The policy ID is the change-detection token: senders compare the TXT record's `id` against the cached policy's ID and only re-fetch the HTTPS document when it differs. Establish the rule that every policy-affecting change - mx list edit, mode change, certificate architecture change - ships with a new, never-before-used ID. IDs must uniquely identify a policy instance, so derive them from content plus a version counter rather than a calendar date that can repeat. Log the ID sequence with timestamps so you can reconstruct which policy any sender held at any moment.

**MX-match enforcement.** The policy's mx patterns and the DNS MX set must agree at all times - policy authoritative for TLS, DNS authoritative for routing. On the sending side, delivery attempts to MX hosts not matching the cached policy's mx patterns must be treated as policy failures and deferred, never silently retried against a mismatched host. On the receiving side, sequence transitions so the policy's mx list is a superset throughout: add the new host to policy, wait out the prior cache lifetime, cut DNS, then trim the old host.

**DNSSEC interplay.** Discovery integrity depends on the resolver path. A DNSSEC-signed zone makes the TXT record unforgeable to a validating resolver, collapsing one attack class. An unsigned zone shifts the entire authentication burden to the policy host's HTTPS certificate - which the design permits, but operators should understand the asymmetry: the certificate for `mta-sts.<domain>` becomes the anchor whenever DNS is untrusted. Sign the zone if you can, and never let the policy host's certificate lapse.

**Cache hygiene on senders.** Respect `max_age` as a ceiling, refresh proactively on a daily cadence rather than at expiry, and - critically - when live discovery fails, continue applying the cached policy for its remaining lifetime instead of falling back to opportunistic cleartext. That fail-closed behavior is what makes blocking refresh unprofitable. Cap `max_age` at operationally short values (days to weeks, not the protocol's one-year ceiling) so even successful poisoning ages out quickly.

**Failure-mode drill.** Rehearse the path where the policy host is down: senders must defer mail per cached policy, and monitoring must distinguish "deferring due to policy host outage" from "MX actually broken," because remediation differs.

## Controls

- Mandatory ID change log with one-way sequential or content-derived IDs; alert on ID reuse.
- Transition runbook ordering - policy superset, cache-lifetime wait, DNS cutover, policy trim - with the wait computed from the maximum `max_age` ever published.
- Documented `max_age` ceiling well below the protocol maximum to bound poisoning lifetime.
- DNSSEC signing of the zone containing `_mta-sts`, with RRSIG validity overlap during key rollovers.
- Policy host redundancy across failure domains, with certificate monitoring alarming weeks before expiry.
- Sender-side cache persistence across restart, keyed by (domain, ID), with integrity protection on the store.
- Queue telemetry classifying policy-induced deferrals separately from transport failures.
- Periodic external verification that the TXT ID and the served policy ID are in sync.

## Validation evidence

- An independent resolver walk showing the published TXT `id` and the HTTPS-served policy ID are identical, executed after every rotation.
- A controlled sender observing an ID change and re-fetching within the expected window, demonstrated in a staging pair.
- A positive tamper test: serve a mismatched ID from a test zone and confirm senders re-fetch rather than trusting the old cache indefinitely.
- An MX-mismatch test: attempt delivery to a host outside the policy mx patterns and confirm deferral, not delivery.
- Policy-host outage drill artifacts showing fail-closed deferral with correct classification and recovery on return.
- Restart test: the sender retains policy state and does not revert to opportunistic behavior.
- DNSSEC chain validation output for the `_mta-sts` name from a validating resolver.

## Failure modes and correction

Mail stops flowing after a policy change because senders hold the old policy: you cut DNS before the policy superset propagated, so enforcing senders deferring against vanished hosts is correct - restore the old MX in policy, wait out cache lifetime, redo the transition in order. Senders pinned to a repudiated policy mean the ID never changed, so caches never re-fetch; enforce the rotation discipline and temporarily drop `max_age` on the next legitimate update to flush caches faster. Poisoning via a forged TXT record succeeds only where DNS is unsigned and the attacker also defeats the policy host's certificate; respond by signing the zone and rotating the certificate if compromise is suspected. Senders falling back to cleartext when discovery fails indicates a sender implementation defect - the cached policy must remain authoritative - and should go to the MTA vendor with drill evidence. Repeated mx-mismatch deferrals after a load-balancer change mean the policy was never updated; treat policy-mx divergence as a hard pre-change gate. An over-long `max_age` found in audit is corrected on the next publication; there is no out-of-band cache flush for senders you do not control.

## Limitations

MTA-STS inherits web PKI's trust anchors; a compromised or mis-issued certificate for the policy host defeats the HTTPS fetch. There is no revocation channel for cached policies held by senders - repudiation propagates only as fast as ID-change detection and cache expiry allow. The mechanism authenticates the policy, not the mail: it constrains transport encryption and does nothing for message-level authentication. Attackers who can block both DNS and HTTPS simultaneously can force deferral - a denial-of-service variant fail-closed designs accept. DNSSEC deployment remains uneven, and operational maturity differs across resolver populations. Policy ID uniqueness is sender-verifiable, but ID predictability is not itself an attack, so rotation discipline is defense-in-depth rather than a hard cryptographic requirement.

## Canonical sources

- [RFC 8461: SMTP MTA Strict Transport Security (MTA-STS)](https://www.rfc-editor.org/rfc/rfc8461.html)
- [RFC 8460: SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)
- [RFC 8461 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc8461.html)
- [RFC 5321: Simple Mail Transfer Protocol](https://www.rfc-editor.org/rfc/rfc5321.html)
- [M3AAWG: TLS for Mail baseline recommendations](https://www.m3aawg.org/published-documents/)
