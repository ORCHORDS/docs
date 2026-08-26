# reverse-dns-ptr-configuration

**Issue:** Before a receiving MTA evaluates SPF, DKIM, or DMARC, most spam filters perform a cheaper check: resolve the sending IP's PTR record and confirm forward-confirmed reverse DNS (FCrDNS) — the PTR hostname must have an A record pointing back to the same IP. Send from an IP with missing, generic (pool-72-3-1-2.isp.example), or unconfirmed reverse DNS and mail is rejected or junk-foldered by Gmail, Outlook.com, and most corporate gateways regardless of perfect authentication alignment; Microsoft's own support threads document deliveries failing on PTR mismatch while SPF/DKIM/DMARC all pass. PTR lives in the IP owner's reverse zone (in-addr.arpa), so developers on cloud/VPS infrastructure cannot fix it in their own DNS console — it must be planned, requested, and verified through the provider.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How FCrDNS validation works

1. **Reverse lookup first.** The receiver queries PTR for the connecting IP (1.2.0.192.in-addr.arpa) and gets a hostname — or NXDOMAIN, which is an immediate reputation fail at many receivers.
2. **Forward confirmation second.** The receiver resolves that hostname's A record and requires it to return the original IP. A PTR pointing at a name whose A record is absent or different (a CNAME chain or a shared web host) fails forward confirmation.
3. **Generic names fail policy even when technically valid.** Names that embed the IP or look like dynamic pool assignments (dhcp-72-3-1-2.isp.example, aws-static-1.2.3.4.example) are treated as residential or unmanaged space. The hostname should be a real, intentional mail infrastructure name like mt1.mail.yourdomain.example.
4. **EHLO agreement is the tiebreaker.** Beyond FCrDNS, many filters warn or score against mismatches between the EHLO hostname the server announces and the PTR hostname. Alignment across PTR, A record, and EHLO is the clean state.

## Setting PTR records on cloud and ISP space

1. **Identify who owns the reverse zone.** Only the IP block owner (AWS, GCP, Azure, Hetzner, your colo ISP) can serve in-addr.arpa. On AWS this is done by creating a hosted zone for the reversed IP range or using the VPC console's edit hostname; GCP and Azure expose it on the instance/public-IP object; many VPS providers (Hetzner, OVH, Linode) expose a self-service rDNS field.
2. **Create the forward A record first, then the PTR.** Point mt1.mail.yourdomain.example at the IP via your normal DNS, then set the PTR to that name. Doing PTR first creates a window where forward confirmation fails.
3. **One sending IP, one deliberate mail hostname.** If multiple services share the IP, pick the mail hostname — but note the better answer is that mail should not share an IP with random other services at all; see dedicated-ip-vs-shared.md for the isolation argument.
4. **Handle the /24 boundary problem.** If your IPs straddle a /8, /16, or /24 boundary delegated to a different provider zone, rDNS requests route to the wrong owner; providers resolve this with special requests or RFC 2317-style delegation, which is why this belongs in planning, not day-of.

## Verification and monitoring

1. **Verify with paired dig queries.** Resolve the PTR from the IP, then the A from that name, and confirm round-trip identity. MXToolbox's smtp reverse DNS check and PTR: reverse DNS lookup tools automate the pair; run them from outside your network.
2. **Check the EHLO name as receivers see it.** Use a telnet/openssl s_client connection to your own submission port or inspect received headers on mail you send yourself — the EHLO argument your MTA sends is configured in the MTA (postfix smtp_helo_name or equivalent), not in DNS, and is a frequent silent mismatch.
3. **Fold PTR checks into the deliverability audit.** Any new sending IP must have FCrDNS verified before warming begins (see ip-warming-strategy.md); add it as a gate in infrastructure-as-code so a forgotten PTR cannot reach production traffic.
4. **Monitor acceptance signals after changes.** Rejections citing "reverse DNS", "no rDNS", or SMTP banner mismatch in bounce logs are the signature failure; grep for them after any IP or MTA hostname change.

## Common failure modes

1. **Cloud default hostnames left in place.** A new VPS ships with an rDNS of a provider default or none at all; everything else is configured perfectly and Gmail still 550s. This is the single most common first-send failure for self-hosted senders.
2. **PTR pointing at a CNAME or a name without an A record.** Technically a PTR exists, but forward confirmation fails because the final A record does not match (or does not exist). Always validate the full loop, not just the PTR answer.
3. **EHLO advertising a name different from PTR.** Postfix defaults to the system hostname, which drifts from the carefully-set PTR. Set the EHLO explicitly and treat hostname changes as coordinated PTR+A+EHLO three-way changes.
4. **IPv6 forgotten.** Delivery over IPv6 gets the same FCrDNS treatment via ip6.arpa PTRs, and dual-stack senders frequently configure v4 only, yielding intermittent filtering that looks nondeterministic. See email-ipv6-deliverability.md for the v6 sending path.
5. **Assuming ESPs need nothing from you.** Shared ESP pools have their PTRs managed, but the same discipline applies to your HELO-facing infrastructure — inbound gateways, relays, and DMARC-report forwarders — anywhere an MTA you control speaks SMTP to the world.
