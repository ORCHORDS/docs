# mta-sts-tls-enforcement

**Issue:** SMTP TLS is opportunistic by default: if an attacker on-path strips the STARTTLS command or presents an invalid certificate, most sending MTAs silently fall back to plaintext delivery (or accept the bad cert) and your inbound mail is readable or modifiable in transit. MTA-STS (RFC 8461) fixes this by letting your domain publish an HTTPS-hosted policy that instructs senders to require valid TLS to your MX hosts and refuse delivery otherwise. Deploying it wrong, however, causes silent mail loss — senders cache your policy and will bounce mail rather than downgrade — so the rollout, `id` rotation, and unwinding procedures matter as much as the initial setup.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Architecture and components

1. **DNS TXT record at `_mta-sts`.** A TXT record at `_mta-sts.example.com` containing `v=STSv1; id=20260815T000000;` signals that a policy exists. The `id` is the cache-buster — senders refetch `policy.json` only when it changes, so every policy edit must bump it.
2. **The policy file over HTTPS.** Senders fetch `https://mta-sts.example.com/.well-known/mta-sts.txt`, which contains `version: STSv1`, `mode:` (`enforce`, `testing`, or `none`), one or more `mx:` hostnames, and `max_age:` in seconds. This host needs a valid public CA certificate on port 443 — Let's Encrypt with auto-renewal is standard.
3. **TLS-RPT as the observability channel.** A TXT record at `_smtp._tls.example.com` (`v=TLSRPTv1; rua=mailto:tls-reports@example.com;`) makes senders email you daily aggregate reports of successful and failed TLS connections. Without TLS-RPT you are flying blind in `testing` mode and will not know when to flip to `enforce`.
4. **Receiving-side enforcement.** It is the *sender* who validates your MX certificates against the policy. Your MX hosts must present certificates that are unexpired, chain to a public root, and match the exact hostnames listed in `mx:` — SANs must cover every MX entry, and the hostname in your DNS MX record must appear in the policy.

## Deployment sequence

1. **Fix the certificate story first.** Ensure every MX hostname has a valid publicly-trusted cert that matches exactly what the policy will list. Self-signed, expired, or wildcard-mismatched certs are the single most common cause of enforcement-mode mail loss.
2. **Publish TLS-RPT and collect baseline reports.** Before publishing any MTA-STS record, stand up report ingestion so you can see current TLS success/failure rates for inbound mail. A week of baseline tells you what "normal" looks like.
3. **Start with `mode: testing` and short `max_age`.** Publish the DNS record and policy with `mode: testing` and `max_age: 86400` (one day). In testing, senders never delay or bounce mail — failures only appear in TLS-RPT reports as `policy_failure` entries.
4. **Triage report failures.** Iterate until reports show negligible failures. Typical offenders: backup MX not in the policy, MX cert not covering a hostname, and senders on old stacks that cannot do TLS 1.2+.
5. **Flip to `enforce` and lengthen `max_age` gradually.** Change mode to `enforce`, bump the `id`, and raise `max_age` in stages (1 day to 1 week to 2-4 weeks). Longer values mean better protection but slower recovery if you ever need senders to forget a broken policy.
6. **Bump the `id` on every policy change.** Adding or removing an MX, changing mode, or editing `max_age` does nothing until the `id` changes — senders keep the cached policy until its `max_age` expires otherwise. This is the most frequently forgotten step.

## Failure modes and pitfalls

1. **Certificate expiry becomes mail loss.** In `enforce` mode, an expired MX cert means senders refuse delivery for up to `max_age` (or until fixed) and bounce with `5xx` errors. Monitoring cert expiry on MX hosts must be more aggressive than on ordinary web endpoints; automate renewal.
2. **MX and policy drift.** If DNS MX records and the policy's `mx:` entries diverge — e.g., you migrate MX but forget the policy — senders may refuse the new MX (not listed) or try the removed one. Treat policy files as code and change MX + policy in the same reviewed change.
3. **Improper removal causes outages.** RFC 8461 defines an unwinding procedure: switch the policy to `mode: none` with a short `max_age`, wait for cached policies to expire (at least the old `max_age`), and only then delete the DNS records. Deleting both records at once strands senders that cached an old `enforce` policy, and they will keep refusing plaintext fallback.
4. **The HTTPS endpoint is part of the mail path.** If `mta-sts.example.com` goes down, existing cached policies keep working (senders retry fetch and fall back to cache), but new senders cannot fetch the policy — they fall back to opportunistic TLS rather than enforcing. Still, monitor the endpoint's uptime and cert.
5. **Backup MX in the policy that cannot meet the bar.** Every `mx:` entry must serve valid TLS. Legacy backup relays or spam appliances with self-signed certs either need fixing or exclusion — but an MX not covered by an `enforce` policy will cause sender confusion between the two signals.

## Verification and monitoring

1. **Validate with external checkers.** Hardenize, MXToolbox, and `starttls-check` style tools confirm the DNS record, policy fetch, and MX cert chain as a sender would see them. Run these after every change, not just at launch.
2. **Parse TLS-RPT continuously.** Feed reports into a parser and alert on: failure-count spikes, new `failure_reason` codes (`validation_failure`, `sts-policy-fetch-error`), and any sender domain reporting repeated certificate failures.
3. **Test from a big sender.** Gmail publishes TLS-RPT data in Google Postmaster Tools v2 — after enabling, watch Postmaster for delivery-TLS stats to corroborate your own reports.
4. **Document the break-glass procedure.** If enforcement starts bouncing mail (bad cert rotation, botched policy), the fast path is: fix the underlying cert/policy, bump `id`, publish. The slow path is unwinding to `testing`/`none` — know both before you need them, and rehearse on a secondary domain first.
5. **Pair with DANE where supported.** MTA-STS covers Web-PKI-validating senders (including large US providers); DANE/TLSA covers DNSSEC-validating ones (Postfix, many European providers). They complement each other — keep both consistent so senders supporting both never see contradictory requirements.
