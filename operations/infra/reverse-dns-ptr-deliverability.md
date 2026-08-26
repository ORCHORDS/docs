# reverse-dns-ptr-deliverability

**Issue:** Reverse DNS — the PTR record that maps an IP address back to a hostname — is one of the oldest and least glamorous parts of internet infrastructure, yet it remains a first-line trust check at every major receiving mail server. A sending IP whose PTR does not forward-confirm to a matching A record is treated as a strong spam signal by Gmail, Microsoft, and most self-hosted MTAs, frequently outweighing everything else in a message's authentication posture. Operators who provision cloud VMs, rent IP space, or run their own ASNs routinely discover that mail, SSH host-trust warnings, and even some IRC or game-server communities break because nobody set up the in-addr.arpa zone. This article covers how PTR resolution actually works, who controls it, the forward-confirmed pattern receivers check, and how to manage reverse DNS as code across cloud and colo environments.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How reverse DNS works

1. **The PTR record and in-addr.arpa.** A PTR record lives in a special reverse zone: IP 203.0.113.10 is looked up as 10.113.0.203.in-addr.arpa. Unlike forward zones, this tree is delegated from whoever owns the address block, not from a registrar you chose — which is why you cannot simply "add a PTR" at your DNS provider unless they also control the delegation.
2. **Forward-confirmed reverse DNS.** Receivers do not just resolve the PTR — they then resolve the returned hostname's A/AAAA record and require it to point back at the original IP (FCrDNS). A PTR claiming mail.example.com is worthless unless mail.example.com actually resolves to that same address; the pair must match in both directions.
3. **Checked before authentication.** Receiving MTAs evaluate the connecting IP's rDNS and HELO/EHLO hostname early in the SMTP conversation, often before SPF or DKIM are even examined; a mismatch or generic reverse name (203-0-113-10.dynamic.isp.net) can trigger rejection or a spam-folder decision immediately.
4. **HELO alignment matters too.** The hostname your MTA announces in HELO should resolve to the connecting IP and share the FCrDNS pair; Postfix's smtpd_reverse_dns checks and most anti-spam stacks compare the HELO string against the PTR as a cheap consistency test.

## Who controls the record

1. **Cloud providers expose an API or console field.** AWS lets you set a PTR on Elastic IPs; GCP and Azure do the same for their reserved public IPs; Hetzner, OVH, and Vultr expose per-IP reverse entries in their panels or APIs. For these, the provider holds the delegation and you only set the value — automate it through their API like any other infrastructure attribute.
2. **Rented colo and ISP space needs a delegation.** If you lease rack space with your own IPv4 block, ask the upstream to delegate the /24's in-addr.arpa zone to your nameservers (NS records for the reversed octet zone), then serve PTR records yourself from the same authoritative DNS tooling that serves your forward zones.
3. **Smaller than a /24 is awkward.** Classless delegations (RFC 2317) use CNAME tricks to delegate sub-/24 slices, and many upstreams botch them; if you only hold a handful of IPs, the pragmatic answer is to ask the provider to host the PTR values on their authoritative servers rather than fight for delegation.
4. **One hostname per IP is the safe rule.** PTR zones give one name per address; multiple services behind one IP should pick a stable infrastructure hostname (host-10.example.net) for the PTR and let SRV records, SNI, and MX records do the service-level naming.

## PTR and modern deliverability

1. **Necessary but not sufficient.** Since the 2024 Gmail/Microsoft bulk-sender rules, correct rDNS is table stakes alongside SPF, DKIM, and DMARC alignment; receivers grade all of them together, and a perfect PTR cannot rescue a missing DMARC record any more than DMARC rescues a generic PTR.
2. **Set it before warming an IP.** Configure forward-confirmed PTR on any new sending IP before the first message, because early mail from an IP with no reverse entry seeds a bad reputation that the subsequent warm-up has to overcome.
3. **Generic names are a spam signal.** A PTR containing pool, dynamic, dhcp, or a bare reverse octet string is treated as presumptively residential or botnet space by many receivers and by policy blocklists; even a neutral infra name you control is strictly better.
4. **Check alignment per sending IP.** Enterprises with multiple MTAs and failover IPs often warm one IP and forget its failover twin; audit every address in your SPF range (and any MX) with a dig -x plus a forward re-resolve, not just the primary.

## Managing reverse DNS as code

1. **Treat PTRs like any other managed record.** Whichever IaC tool provisions the IP (Terraform, Pulumi, Crossplane) should also set its reverse entry in the same change; PTR drift shows up as deliverability regressions weeks later, which makes it much harder to trace than a broken A record.
2. **Serve reverse zones from the same authoritative stack.** Where you hold delegation, publish in-addr.arpa zones from the same primary/secondary DNS infrastructure (with the same change control and zone transfers) as forward zones, so monitoring and validation cover both directions.
3. **Add a forward-confirmation CI check.** A scheduled job that, for every sending IP, resolves the PTR then re-resolves the answer forward and compares, catches the classic failure mode: someone updates the PTR hostname but forgets the matching A record (or vice versa).
4. **Document the HELO contract for every MTA.** Keep a table mapping each sending host to its HELO name, PTR, and A record as the machine-readable source of truth; MTA configuration, DNS, and this table must agree, and the table is what a new engineer reads during a deliverability incident.
