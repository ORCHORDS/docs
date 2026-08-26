# Location Data Privacy: Cross-Regulatory Compliance in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers API collects or relays precise geolocation (GPS coordinates, persistent device location history, or IP-derived location) and you need a single enforcement layer that satisfies simultaneous obligations under GDPR, CPRA, WMHMDA, and FTC guidance on location data.

## Context
Precise location data is classified as sensitive or special-category data under multiple regimes: CPRA treats precise geolocation as Sensitive Personal Information requiring opt-in for certain uses; GDPR processing of location data capable of revealing health or religious affiliation triggers Art. 9; the Washington My Health My Data Act (WMHMDA) treats location data near healthcare facilities as consumer health data regardless of purpose; and FTC enforcement actions (X-Mode, Kochava, InMarket) treat deceptive location data collection as an unfair practice under Section 5 of the FTC Act. Workers are the natural enforcement point because they receive every API call before storage.

## Precision Bucketing: Approximate vs. Precise

Reduce regulatory surface by degrading location to the minimum precision required for the use case. Precise geolocation (within ~1 km) triggers sensitive-data treatment under CPRA and GDPR opinion 5/2020; city-level does not.

```typescript
// src/location-precision.ts

export interface RawCoordinate {
  lat: number;
  lng: number;
}

export type PrecisionLevel = 'exact' | 'neighborhood' | 'city' | 'region';

/**
 * Degrade a coordinate to an approximate bounding box.
 * - neighborhood: ±0.01° (~1 km) — still "precise" under CPRA §1798.140(ae)
 * - city:         ±0.1°  (~10 km) — falls outside CPRA sensitive threshold
 * - region:       ±1.0°  (~100 km)
 */
export function degradeCoordinate(
  coord: RawCoordinate,
  level: PrecisionLevel
): RawCoordinate {
  if (level === 'exact') return coord;
  const precision = level === 'neighborhood' ? 2 : level === 'city' ? 1 : 0;
  const factor = Math.pow(10, precision);
  return {
    lat: Math.round(coord.lat * factor) / factor,
    lng: Math.round(coord.lng * factor) / factor,
  };
}

export function isPreciseLocation(coord: RawCoordinate, stored: RawCoordinate): boolean {
  // Haversine-lite: check if distance < 1 km
  const R = 6371000;
  const dLat = ((stored.lat - coord.lat) * Math.PI) / 180;
  const dLng = ((stored.lng - coord.lng) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((coord.lat * Math.PI) / 180) *
      Math.cos((stored.lat * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) < 1000;
}
```

## Consent and Legal-Basis Gate

Precise location requires opt-in under CPRA §1798.121 and a valid Art. 6 + Art. 7 GDPR basis. The gate middleware enforces this before any coordinate is written to D1.

```typescript
// src/location-gate.ts
interface Env {
  DB: D1Database;
}

type LocationPurpose =
  | 'navigation'
  | 'local_search'
  | 'delivery_tracking'
  | 'fraud_prevention'
  | 'analytics';

interface LocationConsentRecord {
  user_id: string;
  purpose: LocationPurpose;
  precision_level: PrecisionLevel;
  gdpr_lawful_basis?: 'consent' | 'legitimate_interest' | 'contract';
  ccpa_sensitive_opted_in: boolean;
  consented_at: string;
  expires_at: string; // location consent should not be indefinite
}

export async function checkLocationConsent(
  env: Env,
  userId: string,
  purpose: LocationPurpose,
  requestedPrecision: PrecisionLevel
): Promise<{ allowed: boolean; maxPrecision: PrecisionLevel }> {
  const record = await env.DB.prepare(`
    SELECT precision_level, ccpa_sensitive_opted_in, expires_at
    FROM location_consents
    WHERE user_id = ? AND purpose = ?
      AND revoked_at IS NULL AND expires_at > ?
    ORDER BY consented_at DESC
    LIMIT 1
  `).bind(userId, purpose, new Date().toISOString()).first<{
    precision_level: PrecisionLevel;
    ccpa_sensitive_opted_in: number;
    expires_at: string;
  }>();

  if (!record) {
    return { allowed: false, maxPrecision: 'region' };
  }

  // Exact or neighborhood precision requires CPRA sensitive opt-in
  if (
    (requestedPrecision === 'exact' || requestedPrecision === 'neighborhood') &&
    !record.ccpa_sensitive_opted_in
  ) {
    return { allowed: true, maxPrecision: 'city' }; // downgrade silently
  }

  return { allowed: true, maxPrecision: record.precision_level };
}

export async function storeLocationEvent(
  env: Env,
  userId: string,
  coord: RawCoordinate,
  purpose: LocationPurpose,
  precision: PrecisionLevel,
  legalBasis: string
): Promise<void> {
  const degraded = degradeCoordinate(coord, precision);
  await env.DB.prepare(`
    INSERT INTO location_events
      (user_id, lat, lng, precision_level, purpose, legal_basis, recorded_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(
    userId,
    degraded.lat,
    degraded.lng,
    precision,
    purpose,
    legalBasis,
    new Date().toISOString()
  ).run();
}
```

## Retention and Automated Deletion

FTC guidance and state AG opinions uniformly recommend short retention windows for location data (30-90 days for most purposes). Longer retention requires specific justification.

```typescript
// src/location-retention.ts

const LOCATION_RETENTION_DAYS: Record<LocationPurpose, number> = {
  navigation: 7,
  local_search: 30,
  delivery_tracking: 90,
  fraud_prevention: 180,
  analytics: 30, // aggregate only; delete raw after aggregation
};

export async function purgeExpiredLocationData(env: Env): Promise<number> {
  let purged = 0;
  for (const [purpose, days] of Object.entries(LOCATION_RETENTION_DAYS)) {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);

    const result = await env.DB.prepare(`
      DELETE FROM location_events
      WHERE purpose = ? AND recorded_at < ?
    `).bind(purpose, cutoff.toISOString()).run();

    purged += result.meta.changes ?? 0;
  }

  // Log purge event for audit trail
  await env.DB.prepare(`
    INSERT INTO location_purge_log (purged_count, purged_at)
    VALUES (?, ?)
  `).bind(purged, new Date().toISOString()).run();

  return purged;
}
```

## Anti-patterns
- Storing exact GPS coordinates without precise-location consent under CPRA §1798.121
- Sharing raw location history with ad networks or data brokers without explicit disclosure
- Retaining location history beyond the stated or reasonable purpose window
- Deriving sensitive inferences (religion, health status, political affiliation) from location without disclosing this inference capability
- Treating IP-derived city-level location as non-personal data — it can still identify individuals in sparse areas
- Using a single generic consent checkbox to cover both basic location (city) and precise location
- Ignoring WMHMDA when a coordinate places a user near a pharmacy, clinic, or reproductive health provider

## Gotchas
- CPRA defines "precise geolocation" as within a 1-mile (1,850 m) radius — the 1 km bucket in this article is conservative and satisfies both CPRA and most EU DPA guidance
- FTC has brought enforcement actions against companies that claimed location data was "anonymised" when it could still identify individuals — re-identification from location traces is well-documented in research
- GDPR Recital 51 notes that location data is not inherently special-category, but the combination of regular location patterns can reveal health conditions, religious practices, or political activities, triggering Art. 9
- The Washington WMHMDA treats *any* location signal capable of identifying proximity to a healthcare facility as consumer health data — not just GPS
- Under US state laws, the recipient of a GPC (Global Privacy Control) signal must treat the user as having opted out of sharing for cross-context behavioural advertising, including location-based ad targeting
- Cloudflare's `cf.longitude` / `cf.latitude` request properties are approximate (city-level) and do not constitute precise geolocation; however they may still indicate proximity to a healthcare facility under WMHMDA

## Verification

```sql
-- Precise location events stored without sensitive opt-in (CPRA violation risk)
SELECT le.user_id, le.precision_level, le.recorded_at
FROM location_events le
LEFT JOIN location_consents lc
  ON le.user_id = lc.user_id
  AND le.purpose = lc.purpose
  AND lc.ccpa_sensitive_opted_in = 1
  AND lc.revoked_at IS NULL
WHERE le.precision_level IN ('exact', 'neighborhood')
  AND lc.id IS NULL
LIMIT 100;

-- Location data past retention window
SELECT purpose, COUNT(*) AS stale_rows,
       MIN(recorded_at) AS oldest
FROM location_events
WHERE (purpose = 'navigation'  AND recorded_at < DATE('now', '-7 days'))
   OR (purpose = 'local_search' AND recorded_at < DATE('now', '-30 days'))
   OR (purpose = 'analytics'    AND recorded_at < DATE('now', '-30 days'))
GROUP BY purpose;

-- Consent coverage for precise-location users
SELECT u.id, u.email, le.purpose,
       lc.precision_level AS consented_precision,
       lc.ccpa_sensitive_opted_in
FROM location_events le
JOIN users u ON le.user_id = u.id
LEFT JOIN location_consents lc
  ON le.user_id = lc.user_id AND le.purpose = lc.purpose
WHERE le.precision_level = 'exact'
LIMIT 50;
```

## Related
- `washington-my-health-my-data-workers.md`
- `ccpa-cpra-consumer-rights-operations.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `data-minimization-workers-d1-pii-redaction.md`
- `data-retention-automated-deletion-workers.md`
- `california-opt-out-preference-signal-processing-evidence.md`

## Sources
- https://oag.ca.gov/privacy/ccpa (CPRA sensitive personal information)
- https://gdpr-info.eu/recitals/no-51/ (GDPR Recital 51 — location as special category)
- https://www.ftc.gov/business-guidance/blog/2022/08/location-location-location-ftc-warns-about-privacy-risks-location-data (FTC warning)
- https://www.ftc.gov/news-events/news/press-releases/2023/01/ftc-bans-kochava-selling-sensitive-location-data
- https://app.leg.wa.gov/RCW/default.aspx?cite=70.372 (WMHMDA)
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
