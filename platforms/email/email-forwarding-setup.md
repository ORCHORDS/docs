# email-forwarding-setup

**Issue:** Setting up email forwarding from custom domain to external mailbox
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Small projects or aliases need to receive email at a custom domain without managing a full mail server.

## Pattern / Solution
Options:
1. **Cloudflare Email Routing** (free): add MX records, configure routing rules in dashboard, verify destination.
2. **ImprovMX** (freemium): add their MX records, configure forwarders in dashboard.
3. **Google Workspace/Microsoft 365**: full-featured with routing rules.
4. **Postfix on VPS**: `virtual_alias_maps = hash:/etc/postfix/virtual` with `alias@domain.com destination@gmail.com`.

DNS setup for third-party forwarding:
- Remove existing MX records.
- Add provided MX records.
- Add SPF: `v=spf1 include:forwarding-provider.com ~all`.

## Gotchas
- Forwarded email may fail SPF at destination (FROM header is original sender, but MX is forwarder).
- ARC (Authenticated Received Chain) helps forwarded email pass DMARC at destination.
- DMARC alignment issues are common with forwarding; consider DMARC `p=none` if forwarding is primary use.
- Some Gmail accounts reject forwarded email that fails SPF; destination may require allowlisting.

## Related
- cloudflare-email-routing, arc-authenticated-received-chain, mx-record-configuration, spf-record-setup
