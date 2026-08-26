# dnssec-enablement

**Issue:** A zone on Cloudflare needs DNSSEC enabled so that validating resolvers reject forged DNS answers for the domain. The Cloudflare side is one click, but the security only becomes real once a DS (Delegation Signer) record lands at the registrar — and doing the steps out of order (especially during a nameserver migration) causes SERVFAIL for a chunk of the internet. This article covers the enablement flow, the registrar-side mechanics, the breakage modes, and how to verify with dig.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two-sided enablement flow

1. **Cloudflare signs the zone.** DNS > Settings (DNS > Settings in the dashboard) > DNSSEC > Enable DNSSEC. Cloudflare starts signing the zone, publishes the public signing keys, and generates the DS record data you need.
2. **The DS record dialog is the contract.** The enable dialog (re-openable later via "DS record" on the DNSSEC card) contains the key tag, algorithm, digest type, and digest. These exact values must be entered at the registrar — a single wrong character means the chain of trust does not validate.
3. **Algorithm 13 is the target.** Cloudflare's preferred cipher choice is Algorithm 13, which registrars may list under its long name "ECDSA Curve P-256 with SHA-256". If the registrar UI shows neither, treat it as a red flag for the limitations below.
4. **Cloudflare Registrar is the zero-touch case.** For domains registered through Cloudflare Registrar (and for `.ch` / `.cz` TLDs), Cloudflare automatically submits DS records via CDS/CDNSKEY scanning. This "can take one to two days" and there is no manual control over the exact publication timing.
5. **Status is not "on" until the DS is live.** Cloudflare shows the DNSSEC status on the DNS settings card; until the registrar publishes the DS and the parent zone serves it, resolvers are not actually validating your zone even though Cloudflare is already signing.

## Common breakage modes

1. **Registrar does not support DS records at all.** Some registrars offer no DNSSEC UI for third-party nameservers. Your options are limited to switching registrars, or leaving DNSSEC off — a signed zone without a published DS is harmless, but no protection either.
2. **Registrar supports DNSSEC but not Algorithm 13.** Cloudflare documents provider-specific workarounds for a set of registrars (for example Porkbun — where you must *not* fill out the keyData fields — and TransIP). Check the provider-specific instructions before concluding it is impossible.
3. **Nameserver migration with stale DS = SERVFAIL.** If you change nameservers to Cloudflare while the old DS record is still cached at the parent zone, validating resolvers return SERVFAIL "because the cached DS records will not match Cloudflare's DNSSEC keys". This is the single worst outage this feature can cause.
4. **Rollback also respects DS TTL.** To disable DNSSEC safely: remove the DS at the registrar first, then keep zone signing enabled in Cloudflare until the DS TTL has fully expired at the parent. Disabling signing before the DS expires produces the same SERVFAIL window.
5. **Multi-provider DNS needs multi-signer DNSSEC.** If you enable Cloudflare's multi-provider DNS option (apex NS records to other providers), plain DNSSEC breaks; you must run multi-signer DNSSEC (DS records for both providers, DNSKEYs published for both) or the validation chain fails.

## Migration order when DNSSEC is already active elsewhere

1. **Preferred (safe) path.** Remove the DS record at the registrar, wait for the DS TTL to fully expire at the parent (verify with `dig DS example.com` — commonly 24–48 hours for most TLDs), then change nameservers to Cloudflare, wait for the old NS TTL to expire (typically one hour or less), then enable DNSSEC in Cloudflare and publish the new DS. There is a brief window without DNSSEC protection — acceptable for most teams.
2. **Advanced (zero-downtime) path.** If the current provider supports adding external DNSKEY records at the apex, use multi-signer DNSSEC active migration: both providers sign the zone during the transition. Requires careful key management.
3. **Rule of thumb for the wait.** Wait at least one full DS TTL, preferably 1.5x the TTL, before flipping nameservers. Impatience here is the direct cause of the SERVFAIL breakage above.
4. **Never re-enable with old values.** After migration, generate fresh DS values from the Cloudflare dialog; re-using the previous provider's key tag/digest validates nothing.

## Verification with dig

1. **Confirm the DS is published.** `dig DS example.com +short` against the parent (or your resolver) should return the DS record matching the Cloudflare-provided key tag, algorithm 13, and digest. `dig DS example.com` (unfiltered) shows the TTL — the number that governs every migration/rollback wait above.
2. **Confirm signatures are being served.** `dig example.com +dnssec` should return the answer with an RRSIG record in the answer section, proving Cloudflare is signing.
3. **Confirm validation is happening.** Check for the `ad` (authenticated data) flag in the header of `dig example.com +dnssec` — its presence means the resolver validated the chain end-to-end. Pair with `dig +cdflag example.com` to see the same answer with validation deliberately disabled while debugging.
4. **Chase the chain when it fails.** If `ad` is missing and `SERVFAIL` appears, query upstream explicitly (`dig @a.gtld-servers.net example.com DS`) to see whether the TLD nameservers still hold a stale DS. A stale DS at the parent is the fingerprint of the out-of-order-migration failure.
5. **Use an external debugger for a second opinion.** Verisign's DNSSEC Analyzer (dnssec-debugger.verisignlabs.com) renders the full chain of trust and pinpoints the first broken hop — faster than manual dig walks during an incident.

## Related

- `free-tier-domain-security-runbook.md` — DNSSEC is available on every plan including Free; this is one of the free wins worth defaulting on.
- `security-level-ip-access-rules.md` and `under-attack-mode-ddos-runbook.md` — L7 controls complement, but never substitute for, a valid DNSSEC chain at L3/L4.
- `workers-custom-domains.md` — custom hostname wiring inherits the zone's DNSSEC posture; verify the DS before attaching production hostnames.
