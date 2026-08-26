# smtp-recon-vrfy-user-enumeration

**Issue:** Internet-facing MTAs expose SMTP verbs that were designed for diagnostics but now serve primarily as reconnaissance tools. `VRFY` confirms whether a mailbox exists, `EXPN` expands aliases and mailing lists into member addresses, and even with both disabled, the `RCPT TO` response and timing differences leak the same information. An attacker enumerating valid usernames gets a target list for password spraying against IMAP/webmail, credential stuffing, and targeted spear-phishing — and your organization's alias structure tells them which distribution lists map to finance, IT, or executives. Any self-hosted mail infrastructure should assume it is being probed and close these channels deliberately, while engineering teams that build probing tooling (list verification, delivery checking) must understand the same techniques to stay compliant and undetectable-as-attackers.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Reconnaissance techniques against MTAs

1. **VRFY command probing.** `VRFY ceo@example.com` returns `250` (exists), `550` (does not), or `252` (cannot verify). Any server answering 250/550 differentially hands out a username oracle. Most modern MTAs default to 252 or disable it, but misconfigured and legacy appliances still answer honestly.
2. **EXPN list expansion.** `EXPN all-staff` asks the MTA to expand an alias into its members. Beyond enumeration, EXPN reveals organizational structure (which addresses are groups, their membership) — a goldmine for BEC targeting.
3. **RCPT TO differential analysis.** Even with VRFY off, submitting `RCPT TO: known-good@example.com` versus `RCPT TO: random@example.com` during a normal transaction returns `250` versus `550` — an enumeration oracle indistinguishable from normal mail. This is the primary technique tools like `smtp-user-enum` and Metasploit's `smtp_enum` fall back to.
4. **Timing side channels.** Some configurations answer identically but slower for existing users (backend lookup, LDAP call). Statistical timing analysis over many probes can still separate valid from invalid addresses when response codes are normalized.
5. **Banner and HELP harvesting.** `HELP`, `EHLO` feature lists, and banners disclose software, versions, and supported extensions (AUTH mechanisms, STARTTLS, SIZE limits) — the pre-work for exploit selection and for crafting convincing internal-looking mail.

## Hardening your own MTA

1. **Disable VRFY and EXPN outright.** Postfix: `disable_vrfy_command = yes`. Exchange/other MTAs have equivalent policy switches. Returning `502 command not implemented` is fine; there is no legitimate modern use from arbitrary internet hosts.
2. **Return 252, never 250/550 for external verification.** If a gateway must accept VRFY syntax for compatibility, answer `252` (cannot VRFY user) unconditionally — it neither confirms nor denies and stops the oracle without breaking clients that expect a response.
3. **Normalize RCPT behavior.** Configure recipient validation to defer unknown-user rejection to after `DATA` (accept-then-bounce is backscatter-prone, so weigh this carefully) or, more commonly, accept the risk consciously: if you must reject at RCPT, rate-limit per source IP and monitor. There is no perfect defense — the goal is making enumeration slow and loud.
4. **Rate-limit and tarpit port 25.** Connection limits, SMTP conversation delays for unknown senders, and fail2ban-style auto-blocking on probe patterns (many VRFY verbs in one session, dictionary-like RCPT sequences) raise enumeration cost dramatically.
5. **Restrict access at the network layer.** Port 25 should only be reachable where the internet must reach it; internal relays, monitoring probes, and appliances should talk on an internal listener with its own policy. Reduce the exposed surface before configuring it.

## Detection and monitoring

1. **Alert on probe signatures.** Sessions issuing VRFY/EXPN at all (since you disabled them, any attempt is hostile recon), high RCPT-to-unknown-address ratios per source, and `EHLO`-only sessions that never send data — classic scanner fingerprints.
2. **Instrument per-IP counters.** Track distinct-recipient-attempts per connecting IP per hour. A normal sending server contacts a handful of your addresses; an enumeration hits hundreds or thousands sequentially, often alphabetically.
3. **Scan yourself with the attacker's tools.** Run `smtp-user-enum`, Nessus plugin 10249 (EXPN/VRFY information disclosure), and Nmap `smtp-commands` scripts against your own perimeter from an external vantage point. Verify: no VRFY, no EXPN, no differential RCPT leaks, nothing juicy in the banner.
4. **Feed detections into blocking automation.** Enumeration today is usually a precursor to password spraying tomorrow — share the offending IPs with your IMAP/webmail authentication layer and abuse pipelines, not just the MTA firewall.

## Engineering probing the right way

1. **Respect disabled verbs when testing deliverability.** Address-verification features in your own product must not fall back to VRFY-style SMTP probing of third-party MTAs: it is unreliable (252 everywhere), considered abusive at volume, and trivially detected as hostile. Use signup-time confirmation mail (double opt-in) instead.
2. **Prefer inbox providers' official signals.** Bounce/DSN processing (VERP), ESP webhooks, and List-Unsubscribe feedback loops are the sanctioned channels for knowing which addresses are real; SMTP-layer probing is neither compliant nor accurate in 2026.
3. **Get authorization before scanning anything you do not own.** Port-25 enumeration of other organizations' MTAs without permission crosses from recon research into unauthorized access territory in many jurisdictions; scope penetration tests in writing.
4. **Fuzz your own edge like an attacker.** Bare VRFY after STARTTLS, VRFY pipelined mid-DATA, EXPN with encoded alias names — the hardening you configured on one listener must be verified on every listener (IPv6 included, where exposure audits are routinely forgotten).
5. **Keep the hardening in deployment checklists.** New relays, spam appliances, and test MTAs come with permissive defaults. A `disable_vrfy_command` check (and an external probe) belongs in the standard go-live checklist, not in tribal memory.
