# google-postmaster-setup

**Issue:** Setting up Google Postmaster Tools for Gmail deliverability monitoring
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Gmail handles ~35% of global email; Postmaster Tools provides reputation and spam rate data for Gmail delivery.

## Pattern / Solution
1. Visit postmaster.google.com, sign in with a Google account.
2. Add domain -> verify ownership via TXT record: `google-site-verification=...` in DNS.
3. Wait 24-48 hours for data to appear.
4. Monitor dashboards:
   - **Domain Reputation:** Bad/Low/Medium/High — target High.
   - **IP Reputation:** Same scale per sending IP.
   - **Spam Rate:** Target < 0.10%; above 0.10% triggers filtering, 0.30% is critical.
   - **Authentication:** SPF, DKIM, DMARC pass rates — target 100%.
   - **Encryption (TLS):** Should be 100% for modern infrastructure.
5. Investigate and address any reputation degradation immediately.

## Gotchas
- Domain reputation reflects aggregate history; recovery from Bad takes weeks of clean sends.
- Postmaster Tools data is only available if you send enough volume to Gmail to generate data.
- Spam rate shown is complaint rate from Gmail users marking as spam; it's a subset of total complaints.
- DMARC must be published for data to appear in Authentication dashboard.

## Related
- postmaster-tools-setup, microsoft-snds-setup, email-deliverability-audit, dmarc-policy-setup
