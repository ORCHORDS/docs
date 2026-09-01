# Postfix TLS Policy Map Overrides

Postfix's default posture toward TLS is opportunistic: try STARTTLS, proceed in cleartext if the peer does not offer it, and never let a certificate problem stop delivery. That default is right for the open internet and wrong for the destinations that matter - partners under contractual encryption requirements, internal zones where cleartext is prohibited, hosts whose certificates you can pin. The TLS policy map is the override mechanism: `smtp_tls_policy_maps` points at a lookup table keyed by destination, and each entry sets a security level plus optional attribute constraints that tighten, never loosen, the site default. Because a mistyped entry can silently defer all mail to a destination, the mechanism rewards deliberate table hygiene: explicit levels, minimal attribute sprawl, and verification that what you wrote is what the running MTA enforces.

## Scope

This article covers configuration and operation of Postfix SMTP client TLS policy overrides: the security levels available in policy maps, per-domain entries, attribute syntax, the interaction with DANE, and safe change practice. It applies to outbound-relaying Postfix systems. It does not cover server-side settings, MTA-STS policy caching internals, or TLSRPT report generation beyond their interaction with policy-map precedence.

## Workflow or implementation guidance

**Establish the baseline.** Set the site-wide client posture with `smtp_tls_security_level` - `may` for opportunistic TLS as the floor. Do not raise the global level to `encrypt` as a substitute for per-destination policy; partner exceptions and legacy destinations make global enforcement a deferral generator, and the policy map exists precisely so enforcement can be scoped.

**Build the map.** Point `smtp_tls_policy_maps` at a lookup table, for example `hash:/etc/postfix/tls_policy`. Each line keys on the next-hop destination as the SMTP client resolves it - the domain, or a bracketed `[host]` form when routing forces a specific next hop. The value is a security level with optional whitespace-separated attributes:

```
example.com       encrypt protocols=>=TLSv1.2 ciphers=high
partner.example    secure match=partner.example
legacy.example     none
```

**Choose levels deliberately.** `none` disables TLS for a destination (rare, and worth a comment explaining why). `may` restates the default. `encrypt` requires STARTTLS but performs no certificate validation - encryption without authentication, for when the goal is wire confidentiality and no better evidence exists. `fingerprint` requires the peer certificate to hash to the pinned value. `verify` requires a validated chain with hostname matching governed by the `match` attribute; `secure` is `verify` plus a stricter trust demand. The `dane` and `dane-only` levels activate DNSSEC-validated TLSA handling and take precedence over policy-map entries for destinations where usable TLSA records exist - do not fight that precedence; if DANE applies, let it.

**Constrain attributes sparingly.** `protocols=` narrows acceptable TLS versions; `ciphers=` shapes the suite list; `match=` supplies expected names. Every attribute is a future failure in waiting when the peer upgrades - pin versions no tighter than the requirement, and pin fingerprints only where the peer's operational owner is contractually reachable.

**Deploy with verification.** After `postmap` and reload, confirm the table compiled, then observe actual session behavior for one representative destination per security level via logging. Postfix logs the negotiated security level per delivery; that log line, not the config file, is the source of truth for what is enforced.

**Operate the lifecycle.** Fingerprint pins rotate when peers change certificates; protocol floors age as the ecosystem moves. Calendar both, with the peer owner's contact recorded in the table comments.

## Controls

- Table change control: every entry carries a comment naming the requirement it serves and an owner; unattributed entries are removed at audit.
- `postmap` compilation wired into deployment so a hand-edited source without a compiled map cannot silently diverge.
- Post-reload log verification that each security level appears in delivery logs for its destinations.
- Deferral monitoring segmented by TLS policy failure versus other causes, so an over-tight entry surfaces as a distinct queue signature.
- Fingerprint pin registry with expiry and peer-owner contacts, reviewed quarterly.
- Site-wide protocol floor policy so entries do not accumulate contradictory version constraints.
- Key-form verification: policy-map keys match actual next-hop strings, since a key that never matches is a silent no-op.
- No `none` entries without an explanatory comment and an expiry review date.

## Validation evidence

- Delivery log lines showing the enforced security level for each mapped destination, captured after reload as the deployment record.
- A positive enforcement test: point an `encrypt` entry at a staging peer offering no STARTTLS and confirm the mail defers rather than proceeding in cleartext.
- A fingerprint mismatch test against a staging peer with the wrong certificate, confirming deferral.
- An attribute drift test: downgrade a staging peer's TLS version below a `protocols=` floor and confirm rejection.
- `postmap -q` output for each key demonstrating the running table returns the intended policy string.
- Queue telemetry during a planned fingerprint rotation showing recovery without manual queue manipulation.

## Failure modes and correction

Mail deferring to a destination the day its certificate renewed, with handshake failures logged, is classic fingerprint-pin staleness - update the pin from the peer's published new certificate and calendar the next rotation before it is discovered. An entry that never applies, with logs still showing the default level, means the key does not match the next-hop form Postfix actually looks up - domain form versus bracketed relayhost form is the usual divergence; compare `postmap -q` against the exact next-hop string in the log. Deferral storms after tightening a `protocols=` floor indicate the peer population is older than assumed; relax the floor to the true requirement rather than exempting individual hosts, which fragments the table. `encrypt` entries giving false comfort should be upgraded to `verify` with a `match` attribute as soon as the peer's naming is stable. `none` entries accreting for "temporary" legacy destinations outlive their rationale; audit them out. DANE-protected destinations ignoring policy-map constraints is correct precedence, not a bug - document them as DANE-governed and remove redundant entries. A corrupted compiled map after a crash produces lookup failures resembling policy misfires; rebuild with `postmap` from source.

## Limitations

Policy maps are static configuration: they cannot express conditional enforcement and know nothing of a destination's current state, unlike MTA-STS senders that cache and apply policy dynamically. Fingerprint pinning is brittle by design and shifts certificate-rotation cost onto the pin maintainer. Keys bind to routing identities, so routing changes silently invalidate entries. CA trust for `verify`/`secure` rides on the system's CA bundle, inheriting its update cadence. The map tightens only outbound delivery, not inbound sessions or submission. Hash tables need recompilation on change, and every skipped `postmap` creates divergence between what is written and what is enforced.

## Canonical sources

- [Postfix TLS Support (TLS_README: security levels, policy maps)](https://www.postfix.org/TLS_README.html)
- [Postfix postconf(5) parameter reference](https://www.postfix.org/postconf.5.html)
- [RFC 3207: SMTP Service Extension for Secure SMTP over Transport Layer Security](https://www.rfc-editor.org/rfc/rfc3207.html)
- [RFC 8461: SMTP MTA Strict Transport Security (MTA-STS)](https://www.rfc-editor.org/rfc/rfc8461.html)
- [M3AAWG: TLS for Mail baseline recommendations](https://www.m3aawg.org/published-documents/)
