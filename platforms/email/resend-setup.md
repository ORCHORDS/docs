# resend-setup

**Issue:** Configuring Resend as a transactional email provider
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New projects need a simple, developer-friendly transactional email API with good deliverability defaults and modern SDK support.

## Pattern / Solution
1. Sign up at resend.com and verify your domain via DNS records (SPF, DKIM added automatically in dashboard).
2. Install SDK: `npm install resend`
3. Initialize and send:
`js
import { Resend } from 'resend';
const resend = new Resend(process.env.RESEND_API_KEY);
await resend.emails.send({ from: 'noreply@yourdomain.com', to: 'user@example.com', subject: 'Hello', html: '<p>Hello</p>' });
`
4. Use React Email components with Resend's `react` field for templated sends.
5. Configure webhooks in dashboard for delivery events.

## Gotchas
- Free tier limited to 3,000 emails/month and 100/day.
- Domain verification can take up to 48 hours for DNS propagation.
- `from` address must use a verified domain; cannot send from unverified domains.
- Rate limits apply per API key; rotate keys per environment.

## Related
- react-email-components, sendgrid-setup, postmark-setup, ses-bounce-complaint-webhooks
