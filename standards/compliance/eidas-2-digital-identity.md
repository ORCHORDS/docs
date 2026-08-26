# eidas-2-digital-identity

**Issue:** eIDAS 2.0 (EU Regulation 2024/1183) digital identity wallet and trust service requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
eIDAS 2.0 mandates EU Digital Identity Wallets (EUDIW) that member states must offer to citizens by 2026. Large online platforms and regulated services must accept EUDIW for authentication. Extends qualified trust services to attestations of attributes.

## Pattern / Solution
EU Digital Identity Wallet (EUDIW):
- Mobile app issued by or under supervision of member state
- Contains: national eID, professional qualifications, diplomas, driving license, prescriptions
- Architecture: selective disclosure (reveal only needed attributes); ISO 18013-5 / SD-JWT W3C VC

Who must accept EUDIW:
- Very Large Online Platforms (>45M EU users) — mandatory by 2026
- Regulated services: banking (mandatory KYC), healthcare, public services
- Any service that requires strong authentication or attribute verification

Integration for relying parties (service providers):
1. Register as relying party with EUDIW infrastructure
2. Specify which attributes you need and legal basis for requesting them
3. Implement OpenID4VP (presentation protocol) endpoint
4. Verify signed attestations from wallet
5. Log attribute requests per eIDAS 2 audit requirements

```
Relying Party flow:
- Send presentation request (specify required attributes, purpose)
- Wallet shows user what is being requested and why
- User approves selective disclosure
- RP receives verified attribute attestation (not PAN-linked to full identity)
```

Qualified Trust Services:
- Qualified Electronic Signatures (QES): legally equivalent to handwritten signature in all EU
- Qualified Website Authentication Certificates (QWAC): replacing EV certificates
- Qualified Electronic Attestations of Attributes (QEAA): new — certified attribute assertions

## Gotchas
- EUDIW implementation varies by member state — cross-border interoperability is via common protocol
- eIDAS 2 does not replace GDPR — data minimization and purpose limitation still apply to attributes received
- Wallets must support "non-linkability" — RP cannot correlate user across different wallet interactions
- EAA (European Accessibility Act) also applies to digital identity interfaces — check WCAG 2.1 AA

## Related
- `eidas-20-eid-wallet-2026.md`
- `accessibility-wcag-21-compliance.md`
