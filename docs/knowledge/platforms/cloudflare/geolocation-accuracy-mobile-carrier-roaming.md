# IP Geolocation Accuracy: Mobile Carrier Traffic vs Desktop Broadband

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project's compliance Worker gates content by `request.cf.country` /
`regionCode`, and mobile users are the ones it gets wrong. A user in
El Paso on T-Mobile LTE is placed in Dallas and served the wrong
state's ruleset. A US subscriber roaming in Germany still shows
`country: "US"` and sails past the region gate; a German visitor on
a German SIM in the US is blocked as "outside the US." Support sees
"I'm in an allowed state but blocked" almost exclusively from
cellular traffic — desktop broadband users almost never hit it —
and the false-allow side is invisible until an audit finds it.

## Context

Cloudflare resolves the connecting IP against a geo database
(updated multiple times per week) and exposes the result as the
`CF-IPCountry` header and `request.cf` fields (`country`, `region`,
`regionCode`, `city`, `latitude`, `longitude`, `postalCode`,
`metroCode`, `timezone`, `asn`, `asOrganization`, `isEUCountry`).
The lookup is fine — the problem is what a mobile IP *means*. A
desktop broadband IP is assigned by a local ISP head-end and
usually geolocates to the right city. A cellular IP is assigned at
the carrier's packet gateway (P-GW in 4G, UPF in 5G) — one of a
handful of national egress sites, behind CGNAT pools spanning whole
regions. The IP locates the gateway, not the phone. (iCloud
Private Relay is a separate mechanism with its own entry.)

## Why carrier IPs geolocate poorly

```
Desktop broadband                 Mobile carrier (4G/5G)
─────────────────────             ──────────────────────────────
Home → local ISP head-end         Phone → tower → carrier core →
→ public IP tied to a city        P-GW/UPF at a national egress
                                  hub → CGNAT public IP

  User in El Paso                   User in El Paso
  IP geolocates: El Paso ✓          IP geolocates: Dallas ✗

Three compounding causes on mobile:
1. Centralized gateways — a national carrier runs few egress
   sites, at major peering hubs. Every subscriber in a wide
   area exits there, so city/region resolve to the hub,
   hundreds of km from the user.
2. CGNAT pools — one public IP fronts thousands of
   subscribers, and pools are re-mapped across gateway sites
   as capacity shifts, so a prefix's "location" drifts.
3. Roaming home-routing — next section: the user is not even
   in the country the IP says.

Reliable on mobile: ASN / asOrganization (which carrier).
Unreliable on mobile: city, region, postal, metro, lat/long.
Country: usually right for domestic users, wrong for roamers.
```

## Roaming: the country field itself lies

```
Roaming architecture      Who assigns the IP     Geolocates to
──────────────────────────────────────────────────────────────
Home-Routed (HR)          Home carrier's P-GW    HOME country,
                           back home              not the user's
Local Breakout (LBO)      Visited network        Visited country
IPX Hub Breakout (IHBO)   Third-party IPX hub    The hub's
                                                  country

Home-routing is the default for most consumer roaming, so:

  German subscriber physically in Spain  → cf.country = DE
  US subscriber physically in Germany    → cf.country = US
  German subscriber visiting the US      → cf.country = DE
    → example project blocks them (false deny) or applies German
      rules to someone standing in Texas (false allow).

IPinfo measured hundreds of IPv4 prefixes carrying
home-routed roaming traffic, many shared with non-roaming
users — one prefix serves people in different countries at
once and can flip country in the databases week to week.

MCC/MNC vs IP: the MCC/MNC (carrier lookup, or a native
app's telephony API) identifies the SERVING network and
country — what the phone actually attaches to; the IP only
identifies internet egress. Trust the network-side signal.
```

## Cloudflare geo fields: granularity vs trustworthiness

```
Field (request.cf)     Granularity       Mobile-carrier caveat
──────────────────────────────────────────────────────────────
country / CF-IPCountry country (ISO2)    Wrong for home-routed
                                         roamers
isEUCountry            country-derived   Same roaming caveat
region, regionCode     ISO 3166-2        Gateway's region, not
                       first-level        the user's
city, postalCode,      city/ZIP/DMA      Gateway city; treat as
metroCode                                 noise on cellular ASNs
latitude / longitude   point estimate    Centroid of the above
timezone               region-derived    Follows the bad region
asn, asOrganization    network           RELIABLE — names the
                                         carrier; how you
                                         detect "cellular"

All fields can be null. Database refreshes multiple times
per week; corrections go through Cloudflare's form (~48h).
Neither fixes the structural gateway problem — the data is
"correct" about the gateway.
```

## Compliance impact: errors concentrate on mobile

```
                      Desktop broadband     Mobile carrier
──────────────────────────────────────────────────────────────
Country accuracy      very high             fails on roamers
Region/city accuracy  usually city-level    often wrong region
False DENY (blocked   rare                  common near
 though eligible)                           gateways/borders
False ALLOW (served   rare                  roamers + gateway
 though ineligible)                         placement

For a 21+ platform with state-by-state US rules and
sanctions screening, both directions are compliance events:
a false allow serves gated content into a restricted
jurisdiction; a false deny hits whole metro areas at once.
Regulators judge whether controls are reasonable — "IP said
Texas" is weak evidence when your own logs show cellular IPs
misplacing users. IP geo stays a legitimate COARSE signal;
it just cannot be the only one.
```

## Defense-in-depth in the Worker

```javascript
// IP geo = one coarse signal, weighted by network type.
const CELLULAR_ASNS = new Set([21928, 22394, 20057 /* ... */]);

function geoSignal(request) {
  const cf = request.cf;
  const cellular = CELLULAR_ASNS.has(cf.asn);
  return {
    country: cf.country,
    region: cf.regionCode,
    // Gateway region/city is not evidence; country survives
    // domestic cellular but not roaming — corroborate it.
    regionAuthoritative: !cellular,
    countryConfidence: cellular ? 'medium' : 'high',
  };
}

function complianceDecision(ipGeo, account) {
  // Corroborating signals, strongest first:
  //  1. KYC / age-verification document country
  //  2. Payment method issuing country
  //  3. Declared location, re-attested when ipGeo disagrees
  //  4. GPS-permission flow — only for the strict gates
  //     (state-level 21+ rules) where it is justified
  const signals = [account.kycCountry, account.paymentCountry,
                   account.declaredRegion, ipGeo];
  // Hard-block only when signals AGREE on ineligibility, or
  // sanctioned-country IP + no contradicting KYC.
  // Disagreement => step-up verification, not silent deny.
  return resolve(signals);
}

// Log disagreement so the error rate is measurable.
function logGeoDisagreement(env, cf, account, platform) {
  env.ANALYTICS.writeDataPoint({
    blobs: [platform, String(CELLULAR_ASNS.has(cf.asn)),
            cf.country ?? 'XX', account.declaredRegion ?? '-'],
    doubles: [cf.country === account.kycCountry ? 0 : 1,
              cf.regionCode === account.declaredRegion ? 0 : 1],
    indexes: [String(cf.asn)],
  });
}
```

Cellular ASNs will show several times the desktop mismatch
rate; a spike on one ASN is usually a re-homed CGNAT pool.

## Anti-patterns

- **Hard region gates on `cf.regionCode` for cellular ASNs** —
  the region is the gateway's, not the user's. Whole metros get
  the wrong state's ruleset. Gate on corroborated signals and
  use IP region only as a tiebreaker or trigger for step-up.
- **Treating `cf.country` as physical presence** — home-routed
  roaming means the country field reports the SIM's home, both
  letting roamers through gates and blocking eligible visitors.
- **Lumping carrier inaccuracy in with VPN abuse** — a VPN is
  a chosen exit; a carrier gateway is unavoidable
  infrastructure. Use proxy/VPN detection lists for the former;
  never "punish" cellular ASNs with VPN-style blocks.
- **Tuning geo logic on desktop traffic, shipping to mobile** —
  desktop's high accuracy hides the error class entirely. Every
  geo-gate metric must be segmented mobile vs desktop.
- **Demanding GPS from everyone** — reserve OS location prompts
  for gates that legally need them; blanket prompts crater
  opt-in and leave you blind when users deny.

## Gotchas

- **The false allows are silent.** False denies generate support
  tickets; false allows only surface in audits. Log both sides
  via the disagreement metric — don't wait for tickets.
- **Wi-Fi vs cellular flips mid-session.** The same phone moves
  from an accurate broadband IP to a gateway IP when it leaves
  Wi-Fi. Re-check on network change; don't hard-flip
  entitlements.
- **Travel eSIMs are roaming at scale** — many geolocate to the
  vendor's home carrier or an IPX hub, not the traveler's
  country, and adoption is growing fast.
- **Geo-database corrections don't fix gateways.** Cloudflare
  accepts correction reports, but the database is "right" about
  where the gateway is. Only prefix-level roaming/mobile flags
  (commercial IP-data vendors) mark the data as untrustworthy.
- **`request.cf` fields can be null** (and absent in the
  dashboard preview editor). A null country fails closed for
  sanctions screening but falls through to step-up, not a
  block, for region gates.

## Verification

- Cellular vs non-cellular classification by ASN deployed in
  the Worker; every compliance decision logs it.
- Region/state gates require a corroborating signal (KYC,
  payment country, re-attested declared location, or GPS flow)
  for cellular traffic; IP-only region denial removed.
- Sanctions screening still fails closed on IP country, with a
  documented KYC-country override path for roamers.
- Geo-disagreement metric (IP vs KYC vs declared) live in
  Workers Analytics Engine, segmented by platform and ASN.
- Mobile vs desktop false-deny rate on the geo gate compared
  weekly; the gap trends toward the desktop baseline.
- VPN/proxy detection runs as a separate rule whose block
  counts no longer include cellular ASNs.

## Related

- `documentation/docs/policies/cloudflare/icloud-private-relay-geolocation-rate-limiting.md`
- `documentation/docs/policies/mobile/carrier-cgnat-shared-ip-rate-limiting.md`
- `documentation/docs/policies/compliance/age-gating.md`
- `documentation/docs/policies/compliance/store-region-matrix.md`

## Source URLs (verified 2026-08-17)

- Cloudflare IP Geolocation —
  https://developers.cloudflare.com/network/ip-geolocation/
- Workers Request cf properties —
  https://developers.cloudflare.com/workers/runtime-apis/request/
- Why Mobile Roaming Breaks IP Geolocation (IPinfo) —
  https://ipinfo.io/blog/mobile-roaming-ip-geolocation-prefix-classification
- VPNs, Age Verification and Location-Based Checks (XConnect) —
  https://www.xconnect.net/vpns-age-verification-why-location-based-checks-dont-work
