# DANE / TLSA for SMTP (DNSSEC-based transport security)

**Issue:** Opportunistic TLS for SMTP can be downgraded by an active attacker to plaintext (STARTTLS stripping), and even enforce-mode MTA-STS relies on a Web PKI certificate authority model that has failed before (CA compromise, mis-issuance). You want a stronger, DNS-anchored guarantee that inbound SMTP to your domain uses the correct TLS certificate.
**Date:** 2026-08-13
**Author:** ORCHORDS
**Status:** documented

**DANE** (DNS-based Authentication of Named Entities, RFC 6698) binds a domain's expected TLS certificate (or CA) to its DNS records, secured by DNSSEC. For SMTP, DANE is implemented via **TLSA** records published at `_25._tcp.mail.example.com` that tell sending MTAs which certificate to expect when delivering mail to your MX. A sending MTA with DANE support will refuse to deliver if the TLS handshake does not match the TLSA record — defeating STARTTLS stripping and CA mis-issuance.

## Symptom

- Inbound mail to your domain is intermittently intercepted/stripped (rare, but happens on hostile networks or misconfigured middleboxes).
- You want defense in depth beyond MTA-STS because you do not fully trust the CA system (or you operate your own CA).
- Sending MTAs that support DANE (Postfix with DANE support, Exim, Halon, large European providers) cannot validate your MX and fall back to opportunistic TLS.
- You see TLS-RPT reports from DANE-capable senders showing "DANE validation failed" or no DANE validation at all.
- You want to comply with BSI / German federal email standards (BSI TR-03182) that recommend DANE for government domains.

The cause is usually: no TLSA record published, DNSSEC not enabled on the domain (DANE requires DNSSEC validation to be trustworthy), or a TLSA record that does not match the actual MX certificate (selector/usage mismatch).

## Gotchas

- **DANE requires DNSSEC on the domain.** Without DNSSEC validation of the zone, a TLSA record can be forged and provides no real security. Enable and sign DNSSEC first, then publish TLSA records. A TLSA record on an unsigned zone is worse than useless — it implies security that does not exist.
- **TLSA record placement must match the MX hostname and port.** The record goes at `_port._tcp.mxhostname`. For SMTP on port 25 to `mx1.example.com`, that is `_25._tcp.mx1.example.com`. Publishing TLSA at the apex or at the wrong hostname does nothing.
- **Selector and usage fields are easy to get wrong.** The TLSA record has three fields: `<usage> <selector> <matching-type>`. Common SMTP patterns:
  - `3 1 1` — pin the exact leaf certificate's SubjectPublicKeyInfo (SPKI). Most secure, breaks on cert rotation.
  - `3 0 1` — pin the exact leaf certificate's full DER. Same rotation problem.
  - `2 1 1` — trust the SPKI if it chains to a CA in the TLSA record (intermediate pinning).
  - Usage `3` (DANE-EE, trust this exact cert) is most common for SMTP; usage `0`/`1` map to PKIX and are rarely used for mail.
- **Certificate rotation breaks `3 1 1` pins silently.** If your MX certificate renews and you published a `3 1 1` SPKI pin, DANE-validating senders will refuse delivery until you update the TLSA record. Publish the new TLSA record *before* switching the certificate, with overlap, or publish multiple TLSA records (old + new) during rotation.
- **DANE and MTA-STS can coexist but can also conflict.** MTA-STS says "require TLS, this is the policy." DANE says "require TLS *and* this specific cert." If a sender supports both and they disagree, behavior depends on implementation. Generally DANE is stricter; ensure they are consistent.
- **Not all senders validate DANE.** Major supporters include Postfix (≥3.3 with dnssec support), Exim (with patches/config), Halon, and several European providers (German, Dutch, Swiss mail hosts are strong DANE adopters). Gmail/Microsoft support has been uneven — do not assume DANE replaces MTA-STS; use both.
- **DNSSEC operational risk is real.** If your DNSSEC signatures expire (failed RRSIG rollover) or the zone is misconfigured, the domain goes dark for DNSSEC-validating resolvers — which is worse than no DANE. Monitor DNSSEC health continuously.
- **Testing from a DANE-capable client is mandatory.** A `dig` lookup showing the TLSA record is not enough; you need a real DANE-validating SMTP client to confirm the handshake matches. Use the [SIDN DANE checker](https://internet.nl/) or `swaks --tls --tls-dane` with a DNSSEC-validating resolver.

## Practical setup

**1. Enable DNSSEC on the domain:**
- Sign the zone via your DNS provider (Cloudflare, Route 53, BIND, etc.).
- Publish the DS record at the registrar.
- Verify with: `dig +dnssec example.com DS` and `dig +dnssec example.com RRSIG`.

**2. Confirm the MX certificate:**
- Identify the certificate presented by your MX on port 25 (opportunistic TLS).
- Extract the SPKI hash for a `3 1 1` pin:
```bash
echo | openssl s_client -connect mx1.example.com:25 -starttls smtp 2>/dev/null \
  | openssl x509 -pubkey -noout \
  | openssl pkey -pubin -outform der \
  | openssl dgst -sha256 -binary \
  | base64
```
For DANE TLSA the hash is hex, not base64 — use:
```bash
... | openssl dgst -sha256
```

**3. Publish the TLSA record:**
```
_25._tcp.mx1.example.com.  IN TLSA  3 1 1 <sha256-hex-of-spki>
```
- During certificate rotation, publish both old and new TLSA records simultaneously, then remove the old one after the new cert is live and verified.

**4. Publish TLS-RPT to receive failure reports:**
```
_smtp._tls.example.com.  IN TXT  "v=TLSRPTv1; rua=mailto:tls-reports@example.com"
```
TLS-RPT reports from DANE-capable senders will tell you if DANE validation is failing in the wild.

**5. Verify end-to-end:**
- [internet.nl](https://internet.nl/) — full DANE/DNSSEC/MTA-STS check for mail.
- `swaks --to you@example.com --from test@example.org --server mx1.example.com --tls --tls-dane` from a DNSSEC-validating host.
- Send test mail from a known DANE-capable provider (e.g., a Postfix server with `smtp_tls_security_level = dane`) and confirm receipt.

## Verification
- DNSSEC validates: `delv example.com` or `dig +dnssec +multi example.com DNSKEY`.
- TLSA record present and matches the live MX certificate (recompute the SPKI hash and compare).
- DANE handshake succeeds from a real DANE-capable client (`swaks --tls-dane` or internet.nl).
- TLS-RPT reports show zero DANE/TLS failures over a 2-week window.
- During a planned certificate rotation: publish new TLSA → switch cert → verify → remove old TLSA. No mail loss.

## Sources
- [RFC 6698 — The DNS-Based Authentication of Named Entities (DANE)](https://www.rfc-editor.org/rfc/rfc6698.html)
- [RFC 7672 — SMTP DANE transport](https://www.rfc-editor.org/rfc/rfc7672.html)
- [RFC 8460 — SMTP TLS Reporting (TLS-RPT)](https://www.rfc-editor.org/rfc/rfc8460.html)
- [internet.nl — DANE/DNSSEC mail test](https://internet.nl/)
- [Postfix DANE documentation](https://www.postfix.org/TLS_README.html#client_dane)
