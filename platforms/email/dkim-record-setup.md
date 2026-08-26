# dkim-record-setup

**Issue:** Generating and publishing DKIM keys so outbound mail is cryptographically signed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mail passes SPF but fails DKIM because no signing key is published, or the key in DNS does not match the one used by the mail server.

## Pattern / Solution
Generate a 2048-bit RSA key pair:
```bash
openssl genrsa -out dkim_private.pem 2048
openssl rsa -in dkim_private.pem -pubout -out dkim_public.pem
# Extract raw public key (strip header/footer and newlines)
grep -v "^-" dkim_public.pem | tr -d '\n'
```

Publish as a DNS TXT record at `selector._domainkey.yourdomain.com`:
```
v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
```

- `selector` — a label you choose (e.g. `s1`, `mail2026`); allows key rotation
- `k=rsa` — algorithm
- `p=` — base64-encoded public key

Configure your MTA to sign with the matching private key.

Verify:
```bash
dig TXT s1._domainkey.yourdomain.com
# Online: mxtoolbox.com/dkim.aspx
```

## Gotchas
- 1024-bit keys are no longer accepted by Gmail/Yahoo as of 2024; use 2048
- DNS TXT records have a 255-char string limit; split long keys across multiple quoted strings separated by spaces — they are concatenated automatically
- Key rotation: publish the new selector, update the signer, wait 48 h TTL propagation, then remove the old selector record
- Some providers (SendGrid, Postmark) generate and manage DKIM keys for you; check their UI before generating your own

## Related
- `spf-record-setup.md`
- `dmarc-policy-setup.md`
- `email-authentication-check-tools.md`
