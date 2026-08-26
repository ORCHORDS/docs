# email-header-injection-security

**Issue:** Any feature that turns user input into an email — contact forms, "tell a friend" widgets, signup confirmations, password resets, ticket-by-mail — is a code-injection surface if raw request parameters flow into MIME headers. Injecting CRLF sequences (`\r\n`, or bare `%0d%0a` after URL-decoding) into a subject, recipient, or reply-to field lets an attacker forge additional headers (`Bcc:`, `From:`, `Received:`), splice an entirely new MIME body, and turn the application into an authenticated spam/phishing relay sent from your domain (with your SPF/DKIM alignment, making it pass DMARC). Real-world cases remain current: MimeKit shipped a CRLF-injection fix for SMTP envelope addresses in 2025 (GHSA-g7hc-96xr-gvvx), and Mailpit's header handling drew a 2026 CVE — the bug class is alive in both libraries and hand-rolled mailers.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Attack mechanics

1. **Header termination via CRLF.** Headers are line-delimited; a `%0d%0a` in a form field ends the current header and starts attacker-controlled ones. Classic payload: `subject=Hi\r\nBcc: victim1@evil.com, victim2@evil.com` — the mail library happily emits the Bcc header and the MTA fans out copies.
2. **Body splicing with a blank line.** `comment=Hello\r\n\r\n<html><body>Buy pills at...` injects a full alternative body; in libraries that build the message by string concatenation, this replaces or supplements the legitimate content.
3. **Envelope vs header targets.** Injection can hit SMTP envelope commands (RCPT TO arguments — the MimeKit 2025 advisory class), header values, or both; envelope injection can also smuggle raw SMTP protocol data on naive socket-based senders.
4. **Bare-LF/Bare-CR variants.** Some parsers accept lone `\n` or `\r` as line breaks; filtering only the exact `\r\n` pair misses these. The 2023 SMTP-smuggling research showed entire MTAs accepting bare-LF line endings — sanitize each control character independently.
5. **Second-order injection through stored data.** A "name" captured safely in one flow, stored, and later concatenated into a different message (e.g., admin notification with the name in a custom header like `X-Ticket-Owner`) re-introduces the vulnerability where nobody expected input.

## Vulnerable code patterns

1. **String-concatenated messages.** `msg = f"From: {from}\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"` — any field containing CRLF (or a lone newline that the MTA normalizes) breaks out. This pattern survives in legacy PHP (`mail()`'s `$additional_params` era), shell-outs to `/usr/sbin/sendmail`, and quick Node/Python scripts.
2. **Unvalidated contact-form fields passed as headers.** Reply-To set from the form's "your email" box, subject from a free-text input, or the recipient chosen from a client-supplied `to` parameter (worse: header injection plus open-relay — attacker picks the victim list entirely).
3. **Template engines that interpolate into header sections.** Handlebars/Liquid templates whose output includes headers, or subject lines assembled via string concat of user tokens, inherit the bug unless the mail library re-sanitizes.
4. **URL-decoded parameters used directly.** Query params (`?email=...%0d%0aBcc:...`) decoded after validation bypass checks that ran on the encoded form; always sanitize the decoded value, at the last point before header assignment.
5. **Custom X-headers built from user data.** `X-User-Id`, `X-Campaign-Name`, or threading headers (`In-Reply-To`, `References`) built by concatenation are injection points people forget because they are "internal" headers.

## Exploitation impact

1. **Spam relay from your infrastructure.** Your IPs send the spam; your reputation (Postmaster spam rate, blocklists) takes the damage, and your sending domain can be blocklisted downstream of the abuse.
2. **DMARC-passing phishing.** Mail originates from your domain with your DKIM signature — recipients see authenticated mail from you, which defeats the visual and authentication checks that would flag ordinary spoofing; ideal for targeted BEC-style lures.
3. **Internal header forging.** Injected `Received:`/`Message-ID:`/`Return-Path:` can confuse spam filters, break DMARC alignment checks, or manipulate threading to attach phishing content to legitimate conversations.
4. **Data exfiltration and mail-flooding.** Bcc lists harvested or used to blast victims; injected bodies can carry malware links under your brand.
5. **Pipeline pivot.** If the injected message is later parsed by your inbound system (auto-reply loops, ticketing), attacker-controlled headers become parser input — header injection feeding header-parsing vulnerabilities.

## Prevention

1. **Use a structured mail library and its header API — never concatenation.** Nodemailer (`headers` object), Python `email.message.EmailMessage` (`msg['Subject'] = value`), PHPMailer (`addCustomHeader`) reject or encode CRLF in values. Keep the library current: MimeKit's fix, PHPMailer's historic hardening, and framework mailers carry years of these patches.
2. **Reject CR and LF in every header-bound input, unconditionally.** Single test that catches the class: `if /[\r\n]/ in value: raise`. Do this per-field at the validation layer AND rely on the library's internal guard as defense-in-depth.
3. **Validate addresses against a strict grammar.** Email fields should pass a real address parse (local@domain, no control chars, no folding whitespace) — not a regex that allows `evil@x.com\r\nBcc:...`.
4. **Never trust client-supplied recipient lists.** Recipient selection must resolve server-side from allow-lists (e.g., department constants); a `to` request parameter mapping to raw recipients is an open relay with extra steps.
5. **Encode non-ASCII headers properly.** Use RFC 2047 encoded-words / RFC 2231 via the library rather than hand-building `=?UTF-8?B?...?=` strings — hand-rolled encoders are where CRLF sneaks back in.
6. **Free-text subjects: also cap length and strip control characters** (beyond CR/LF: NUL, vertical tab). Header lines have practical length limits (998 chars per RFC 5322) and control chars can corrupt MIME structure in downstream parsers.
7. **Sanitize at the boundary AND encode at the sink.** Validate on input for UX (reject with 400), enforce at the mail-building sink for security — the sink check is the one that must never be skipped, including for stored/second-order data.

## Testing and detection

1. **Fuzz every header-bound field.** Payloads: `%0d%0aBcc:...`, bare `\n`, bare `\r`, `%0a%0d`, header-folding (`\r\n `), and NUL bytes — against subject, reply-to, from-name, and each custom header. Assert the generated message (capture via a local SMTP sink like Mailpit — itself keep updated — or a test transporter) contains no injected lines.
2. **Automate in CI with a message-assertion test.** Round-trip every transactional template with hostile inputs and assert the parsed output has exactly the expected header set; this catches template regressions and library upgrades that loosen sanitization.
3. **Monitor outbound for anomalies.** Alert on messages with unexpected Bcc volume, multiple distinct recipients from single-recipient templates, or outbound mail whose headers fail your own schema — the signature of an active injection.
4. **Review third-party integrations that send mail on your behalf.** Form builders, CRM auto-responders, and serverless functions (Cloudflare Workers `send_email` bindings) often concatenate headers internally; test them with the same payloads you'd test your own code with.
5. **Track advisories in your mail stack.** CVEs and GHSAs in MimeKit, PHPMailer, Nodemailer, Mailpit, and MTAs (Postfix/exim smuggling fixes) recur; pin versions and subscribe to security feeds for the components in your send path.
