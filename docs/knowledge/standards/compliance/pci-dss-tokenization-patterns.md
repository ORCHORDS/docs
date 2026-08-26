# pci-dss-tokenization-patterns

**Issue:** Implementing tokenization to reduce PCI DSS CDE scope
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tokenization replaces Primary Account Numbers (PANs) with non-sensitive tokens, removing most application components from PCI DSS scope. It is distinct from encryption (which requires key management in scope).

## Pattern / Solution
Tokenization architecture:

```
Client -> API Gateway -> Tokenization Vault -> Returns Token
                              |
                              +-> Encrypted PAN stored in Vault DB
                              +-> Token <-> PAN mapping (isolated)

Application uses Token throughout
Payment processing: send Token to Vault, Vault returns PAN to processor directly
```

Token types:
- Format-Preserving Token: looks like PAN (16 digits); useful for systems expecting PAN format
- Random Token: UUID or random string; more secure; may require application changes

Vault requirements (if self-hosted):
- Vault is the CDE — apply all PCI DSS controls to vault only
- HSM (Hardware Security Module) for encryption keys
- Strict access control: only tokenization service can access vault
- Audit log all detokenization requests

Third-party tokenization services (recommended):
- Stripe (PaymentIntents), Braintree, Adyen — they hold PANs; your environment stays out of scope
- Verify service is PCI DSS Level 1 certified (annually; check their AOC)

Scope reduction test:
- After tokenization: search entire codebase and databases for PAN patterns
- Use regex: `4[0-9]{12}(?:[0-9]{3})?` (Visa); `5[1-5][0-9]{14}` (MC)
- No PANs should appear outside vault

## Gotchas
- Token must not be reversible without vault access — pure algorithmic tokens may not qualify
- Tokens stored alongside expiry date and last 4 digits are still restricted data
- If application stores tokens AND full card data in other systems, both are in scope
- Format-preserving tokenization using FPE may have export control implications

## Related
- `pci-dss-network-segmentation.md`
- `pci-dss-v4.md`
- `pci-dss-tokenization-deep-dive-2026.md`
