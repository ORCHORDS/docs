# can-spam-compliance

**Issue:** Meeting US CAN-SPAM Act requirements for commercial email
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Sending commercial email to US recipients without following CAN-SPAM exposes you to FTC enforcement and per-email fines up to $51,744.

## Pattern / Solution
CAN-SPAM requirements checklist:

| Requirement | Implementation |
|-------------|---------------|
| Accurate `From:` name and address | Use your real brand name and sending domain |
| Non-deceptive subject line | No misleading subjects; no "Re:" or "Fwd:" prefixes on new messages |
| Identify as advertisement | "Advertisement" label or clear marketing context if not an existing customer |
| Physical postal address | Include in email footer |
| Clear unsubscribe mechanism | Link in every commercial email |
| Honor unsubscribes within 10 days | Process immediately; 10 days is the legal max |
| No sending after opt-out | Once suppressed, no marketing; transactional is still allowed |

Footer template:
```html
<p style="font-size:12px;color:#999;">
  You are receiving this because you signed up at yourdomain.com.<br>
  YourCompany Inc. · 123 Main St, Springfield, ST 00000<br>
  <a href="https://mail.yourdomain.com/unsub?t={{token}}">Unsubscribe</a>
</p>
```

## Gotchas
- CAN-SPAM applies to the "sender" — if you send on behalf of another company, both parties may be liable
- Transactional email (order confirmations, password resets) is exempt from most requirements but must not include commercial content that "predominates"
- CAN-SPAM does not require opt-in; it only requires opt-out, making it less strict than GDPR/CASL

## Related
- `gdpr-email-consent.md`
- `casl-canada-compliance.md`
- `unsubscribe-handling-rfc.md`
