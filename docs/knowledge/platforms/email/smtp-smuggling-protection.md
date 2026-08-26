# smtp-smuggling-protection

**Issue:** SMTP smuggling (CVE-2023-51764) lets an attacker exploit inconsistent handling of the end-of-data sequence between mail servers. By sending a message body containing bare-LF line endings followed by a forged `.` terminator, an external sender can make a vulnerable receiving MTA interpret the remainder of the connection as a brand-new SMTP transaction — injecting a spoofed email that appears to originate from inside your own domain, often bypassing SPF checks because the injected message "comes from" your own server. Any self-hosted or forwarding infrastructure running Postfix, Exim, Exchange, or Sendmail must be verified and hardened against this class of attack, because the flaw is in server software, not in your application code.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the attack works

1. **End-of-data ambiguity.** RFC 5321 defines the message terminator as `CRLF . CRLF`, but many MTAs leniently accept a bare `LF . LF`. An attacker submits a DATA payload that ends with a bare-newline dot sequence, then continues the SMTP session with a second `MAIL FROM`/`RCPT TO`/`DATA` exchange smuggled inside the original message body.
2. **Receiver-side interpretation.** A strict server (or one applying different newline normalization than the sender) treats the smuggled commands as a new, separate transaction originating from the trusted relay — so internal recipients see a message whose received chain appears legitimate.
3. **Authentication bypass.** The injected message can carry a `From` matching the victim domain and, because it is emitted by the victim's own or a trusted intermediate MTA, SPF evaluation may pass for the internal hop, defeating naive incoming-allow rules that trust the perimeter server.
4. **Outbound variant (reverse smuggling).** The mirrored case: your server relaying outbound mail to a receiver that interprets newlines differently can be tricked into emitting attacker-controlled additional messages that you then deliver, making your infrastructure the spam source.

## Server-side defenses

1. **Patch Postfix to a protected default.** Postfix 3.9+ and 3.8.6+ ship with `smtpd_forbid_bare_newline = normalize` enabled by default, converting bare newlines instead of disconnecting. Upgrade rather than backporting config if at all possible; distro backports of the fix landed in 3.8.6, 3.7.9, 3.6.13, and 3.5.23.
2. **Enable the guard on unpatchable older versions.** On Postfix 3.8.4 and earlier set `smtpd_forbid_bare_newline = yes` in `main.cf` (rejects clients sending bare newlines), or apply the documented workaround pair `smtpd_data_restrictions = reject_unauth_pipelining` plus `smtpd_discard_ehlo_keywords = chunking`, which blocks the smuggling path via pipeline abuse.
3. **Harden non-Postfix MTAs.** Exim, Courier, and Sendmail each shipped their own advisories and fixes; Microsoft Exchange never gained a direct equivalent setting and required an interim "Extended Protection"/transport-rule workaround — verify current vendor guidance for every MTA and mail appliance in the path, including load balancers that terminate SMTP.
4. **Test before enforcing disconnects.** `smtpd_forbid_bare_newline = yes` (hard reject) can break legitimate clients that send bare LF — some application mailers, appliances, and health checks do. The later `normalize` default exists precisely because of that fallout; prefer patched versions or normalize semantics over blind rejection on customer-facing listeners.
5. **Normalize at the edge only.** Apply newline normalization on inbound internet-facing listeners; keep internal relay-to-relay behavior consistent so policy differences between hops do not recreate the same ambiguity internally.

## Outbound and sender-side risk

1. **Verify your sending chain end to end.** Smuggling is a two-party mismatch: your outbound relay is only safe if every receiver downstream normalizes consistently. Since you cannot control receivers, ensure your own outbound MTA never passes bare-LF bodies through unmodified — normalize on submission.
2. **Watch submission ports.** Ports 587/465 accepting authenticated mail from web apps are a classic injection point: application code that embeds user input in bodies with lone `\n` gives authenticated attackers smuggling-grade payloads. Validate and normalize all injected content at the submission layer.
3. **Re-check middleware.** Spam filters, archive gateways, and SRS/forwarding rewriters that re-emit messages can reintroduce or strip CR characters. Any component that rewrites bodies must emit strict CRLF on output regardless of what it accepted on input.
4. **Pin and monitor third-party SMTP libraries.** MimeKit, PHPMailer, Nodemailer, and Mailpit advisories recur in this space; subscribe to security feeds for your exact send path and pin versions so a transitive upgrade cannot silently regress newline handling.

## Detection and verification

1. **Probe your own perimeter.** Use the PoC tooling released with the original SEC Consult research (or a scripted `nc` session sending a bare-LF dot sequence) against a test mailbox to confirm your edge rejects or normalizes the smuggled second transaction.
2. **Scan for stragglers.** Nessus/GHSAs cover CVE-2023-51764 detection; any legacy relay, test MTA, or forgotten appliance on port 25 in your IP space is a candidate — inventory by scanning, not by memory.
3. **Alert on anomalous transaction shapes.** Logs showing a single client connection performing multiple complete MAIL/DATA cycles at a rate or pattern inconsistent with the client type (e.g., a marketing API connection doing interactive-looking handshakes) deserve alerting.
4. **Investigate reports of self-spoofed mail.** If a user reports mail "from your own domain" that never transited your sending infrastructure, pull the full `Received` chain — smuggling often leaves a visible anomaly in the hop ordering even when headers otherwise look plausible.
5. **Treat this as ongoing, not historical.** The 2023 disclosure is patched in supported software, but unpatched legacy MTAs still exist across the internet in 2026; include newline-strictness checks in your standard MTA deployment checklist and post-mortem reviews.
