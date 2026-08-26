# Workers `request.cf` Geolocation: Mobile Accuracy Reference

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A Worker gates 21+ content and geo-restricted material using
`request.cf.country` and sub-fields. Mobile users are blocked
from permitted regions; roaming users pass gates for their
home country while physically abroad; some iPhone Safari
users resolve to a US city regardless of their actual
location. Compliance audit flags the pattern: false allows
and false denies concentrate on cellular traffic.

## Context

Every inbound request carries a `cf` object Cloudflare
populates from the connecting IP using IPinfo (refreshed
multiple times per week). The lookup is accurate; the
problem is what a mobile IP _means_. Three structural paths
produce systematically wrong values: home-routed roaming,
iCloud Private Relay, and carrier IPv6 gateway egress.
`cf.asn` identifies which path is active and is the most
reliable field for all connection types.

## Field accuracy matrix

```
Field              Broadband   Domestic    Roaming     iCloud
                               mobile      mobile      Relay
──────────────────────────────────────────────────────────────
cf.country         high        usually ✓   home SIM    usually ✓
                                           country ✗   (coarse)
cf.region /        high        gateway     gateway     relay
cf.regionCode                  region ✗    region ✗    region ✗
cf.city            city-level  gateway     gateway     relay
                               city ✗      city ✗      city ✗
cf.postalCode      usually ✓   gateway     gateway     relay
                               ZIP ✗       ZIP ✗       ZIP ✗
cf.latitude /      city        gateway     gateway     relay
cf.longitude       centroid    centroid ✗  centroid ✗  centroid ✗
cf.timezone        derived     gateway TZ  home TZ ✗   coarse
                   from city   (close)
cf.asn /           ISP name    carrier ✓   home        relay
cf.asOrganization              (correct)   carrier ✓   operator ✓

✓ reliable   ✗ structurally wrong (not a database error)
```

## Why each path fails

**Home-routed roaming.** Consumer roaming routes data through
the subscriber's home carrier packet gateway (P-GW / UPF),
so `cf.country` returns the home SIM's country — not where
the user is standing. IPX-hub roaming adds a third variant:
traffic exits through a neutral IPX hub and geolocates to
that hub's country. Full detail:
`geolocation-accuracy-mobile-carrier-roaming.md`

```
German SIM roaming in the US  →  cf.country = "DE"
US SIM roaming in Germany     →  cf.country = "US"
```

**iCloud Private Relay.** A two-hop proxy (iCloud+, iOS 15+,
Safari-only). The Worker sees only the egress IP (AS13335
Cloudflare or partner CDNs). Country is usually preserved;
city/region reflects the relay egress, not the user. Apple
publishes egress ranges at
`https://mask-api.icloud.com/egress-ip-ranges.csv`. Full
detail: `icloud-private-relay-geolocation-rate-limiting.md`

**Carrier IPv6 gateway cities.** IPv6 prefixes are allocated
per packet gateway, not per city. Every subscriber behind a
gateway hub shares the same `cf.city` / `cf.postalCode`.

```
T-Mobile US hub in Bellevue, WA  →  cf.city = "Bellevue"
for subscribers across WA, OR, ID, MT
```

## Detecting unreliable geolocation (ASN + IP class)

```javascript
const CELLULAR_ASNS = new Set([
  21928,  // T-Mobile US
  22394,  // Cellco / Verizon Wireless
  20057,  // AT&T Mobility
  // expand per observed traffic
]);

function geoConfidence(request, relayRanges) {
  const cf    = request.cf;
  const ip    = request.headers.get('CF-Connecting-IP') ?? '';
  const cell  = CELLULAR_ASNS.has(cf.asn);
  const relay = relayRanges && isInRanges(ip, relayRanges);
  return {
    country:      cf.country,
    countryConf:  (cell || relay) ? 'medium' : 'high',
    regionConf:   (cell || relay) ? 'low'    : 'high',
    cellular: cell, relay: !!relay,
  };
}
// Relay ranges: fetch mask-api.icloud.com/egress-ip-ranges.csv
// daily, cache in KV, load once per isolate.
```

Use `cf.asn` (integer, stable) not `cf.asOrganization` (free
text, changes with rebranding) in set membership checks.

## cf.country (edge inference) vs user-declared locale

These are semantically different signals:

```
Signal              What it means
──────────────────────────────────────────────────────────────
cf.country          IP egress country. Wrong for roamers.
Accept-Language     User's OS/browser locale preference.
Account country     Jurisdiction at signup time.
KYC document        Legal identity country — authoritative.
Declared locale     What the user asserts; audit-trailed.
```

A US national roaming in Germany shows `cf.country = "DE"`
but is subject to US account rules. A German roaming in the
US shows `cf.country = "US"` but may have EU content rights.
Age-verification law applies to the jurisdiction of service,
not the user's current IP location.

## Compliance implications (21+ / geo-restricted content)

```
Gate type           IP geo reliability    Recommended control
──────────────────────────────────────────────────────────────
Sanctions (OFAC)    cf.country is the     Fail closed on
                    first filter.         sanctioned country;
                                          KYC overrides logged.
Age gate (21+)      Legally weak alone:   Gate on KYC-verified
                    roamers + relay +     DOB. Use IP geo as
                    CGNAT produce false   coarse pre-filter
                    allows and denies.    only.
Content licensing   Country broadly OK    Accept for country-
(geo-restriction)   for broadband; ~10%   level blocks; provide
                    error on cellular.    mismatch appeal path.
US state-level      cf.regionCode is      Require declared
rules               gateway region on     region + corroboration
                    cellular — wrong.     (KYC / payment) for
                                          cellular ASNs.
```

## Anti-patterns

- **Hard-gating `cf.city` / `cf.regionCode` on cellular
  ASNs** — both fields name the carrier gateway hub.
- **Treating `cf.country` as the user's legal jurisdiction**
  — IP egress country and regulatory jurisdiction differ for
  roaming users and relay users.
- **Blanket-blocking Private Relay ranges** — penalizes
  legitimate iPhone users; relay IPs are not hostile VPNs.
- **Using IP-only for 21+ compliance without KYC** —
  regulators expect age-verification to be reasonably
  reliable; IP geo on mobile does not meet that bar alone.
- **Persisting geo-based entitlements across session** —
  the same device can switch from broadband to cellular
  mid-session; geo entitlements must be re-evaluated.

## Gotchas

- **All `cf` geo fields can be null.** The dashboard preview
  editor always returns null; null-check before comparisons,
  and define a fail-closed default for sanctions gates.
- **Database corrections do not fix the structural problem.**
  A gateway IP is "correctly" placed at the gateway. The
  issue is that the gateway is not the user's city.
- **iCloud relay country is only _usually_ correct.** Apple
  works with geo vendors to register egress CIDRs, but
  un-registered new ranges or stale databases can geolocate
  egress to the CDN operator's country (US for AS13335).
- **IPv6 relay is more accurate than IPv4 relay.** Enabling
  AAAA records on your zone routes relay traffic over IPv6
  egress, which Apple geolocates more precisely than IPv4.

## Verification

- Cellular vs relay classification by ASN / relay-range
  match logged on every geo-gated request.
- Country-gate false-deny rate segmented mobile vs broadband
  in Workers Analytics Engine; gap tracked weekly.
- Region/state gates require a corroborating signal (KYC
  country, payment country, or re-attested declared region)
  for cellular or relay traffic; IP-only region denial
  removed.
- Apple relay CSV refreshed daily in a cron Worker, stored
  in KV; CI test exercises known relay CIDRs.

## Related

- `documentation/categories/cloudflare/geolocation-accuracy-mobile-carrier-roaming.md`
- `documentation/categories/cloudflare/icloud-private-relay-geolocation-rate-limiting.md`
- `documentation/categories/cloudflare/rate-limiting-cgnat-mobile-fingerprinting.md`
- `documentation/categories/compliance/age-gating.md`
- `documentation/categories/compliance/store-region-matrix.md`

## Source URLs (verified 2026-08-17)

- Cloudflare Workers Request cf object —
  https://developers.cloudflare.com/workers/runtime-apis/request/
- Cloudflare IP Geolocation (network settings) —
  https://developers.cloudflare.com/network/ip-geolocation/
- iCloud Private Relay: What Cloudflare Customers Need to
  Know — https://blog.cloudflare.com/icloud-private-relay/
- Apple egress IP range feed —
  https://mask-api.icloud.com/egress-ip-ranges.csv
- IP Geolocation Accuracy on Mobile Networks (ISOC Pulse,
  2026) — https://pulse.internetsociety.org/en/blog/2026/08/why-ip-geolocation-cant-be-trusted-for-mobile-networks-and-the-global-south/
- Mobile Carrier IP Geolocation: Why It Shows the Wrong
  City — https://whatismylocation.org/blog/mobile-carrier-ip-geolocation-wrong
