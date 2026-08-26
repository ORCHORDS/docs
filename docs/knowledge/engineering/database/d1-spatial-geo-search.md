# D1 Spatial Queries with Approximate Geo Search

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Cloudflare Workers application needs to find records near a geographic
coordinate (stores, venues, users, delivery addresses) without a PostGIS extension
or a dedicated spatial database. You store latitude/longitude in D1 and want
"find N nearest" or "find all within X km" queries that run fast enough for
real-time API responses.

## Context

D1 is SQLite without geospatial extensions. SQLite does not ship with `ST_Distance`,
`ST_Within`, or spatial indexes. Approximate geo search in SQLite relies on:

1. **Bounding box pre-filter** — a rectangular lat/lon range that over-selects
   candidates, followed by an exact Haversine distance calculation in SQL or in
   the Worker.
2. **Haversine formula in SQL** — computes great-circle distance inside the query.
   Works on modern SQLite (D1) via math functions (`sin`, `cos`, `acos`, etc.).
3. **Geohash bucketing** — encode locations as geohash strings; prefix-match
   geohash to retrieve candidates in a tile; no math in the query but requires
   multi-prefix queries for edge tiles.

For most SaaS use-cases (find nearest store, find events within 50 km) the
**bounding box + Haversine** pattern performs adequately and is the simplest to
maintain.

If sub-10 ms P99 is required with millions of rows, move geo search to
Cloudflare Vectorize (embedding lat/lon as vectors) or an external spatial index.

## Schema Design

```sql
-- Locations table with geo columns
CREATE TABLE locations (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  name        TEXT NOT NULL,
  lat         REAL NOT NULL,    -- WGS 84 decimal degrees, -90 to 90
  lon         REAL NOT NULL,    -- WGS 84 decimal degrees, -180 to 180
  category    TEXT,
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Composite index: tenant first, then lat for bounding-box scans
CREATE INDEX idx_locations_tenant_lat ON locations(tenant_id, lat);
CREATE INDEX idx_locations_tenant_lon ON locations(tenant_id, lon);

-- For geohash bucketing (alternative approach)
CREATE TABLE locations_geo (
  id       TEXT PRIMARY KEY,
  geohash6 TEXT NOT NULL,    -- 6-char geohash ≈ 1.2 km × 0.6 km tiles
  geohash5 TEXT NOT NULL,    -- 5-char geohash ≈ 4.9 km × 4.9 km tiles
  lat      REAL NOT NULL,
  lon      REAL NOT NULL
);

CREATE INDEX idx_geo_geohash6 ON locations_geo(geohash6);
CREATE INDEX idx_geo_geohash5 ON locations_geo(geohash5);
```

## Bounding Box + Haversine Filter

### SQL Haversine Implementation

SQLite 3.35+ (which D1 uses) supports `sin()`, `cos()`, `asin()`, `sqrt()`,
`pow()`, and `radians()` / `degrees()` via built-in math functions.

```sql
-- Find all locations within :radius_km of (:lat, :lon)
-- Step 1: bounding box eliminates most rows using the index
-- Step 2: Haversine refines to exact great-circle distance

WITH params AS (
  SELECT
    :lat  AS clat,
    :lon  AS clon,
    :radius_km AS radius,
    -- Bounding box deltas (1 degree lat ≈ 111 km; lon degree shrinks with cos(lat))
    :radius_km / 111.0               AS dlat,
    :radius_km / (111.0 * cos(radians(:lat))) AS dlon
)
SELECT
  l.id,
  l.name,
  l.lat,
  l.lon,
  -- Haversine formula (result in km)
  6371.0 * 2 * asin(sqrt(
    pow(sin(radians((l.lat - p.clat) / 2)), 2) +
    cos(radians(p.clat)) * cos(radians(l.lat)) *
    pow(sin(radians((l.lon - p.clon) / 2)), 2)
  )) AS distance_km
FROM locations l, params p
WHERE l.is_active = 1
  -- Bounding box pre-filter (uses index)
  AND l.lat BETWEEN p.clat - p.dlat AND p.clat + p.dlat
  AND l.lon BETWEEN p.clon - p.dlon AND p.clon + p.dlon
  -- Exact distance post-filter
  AND 6371.0 * 2 * asin(sqrt(
        pow(sin(radians((l.lat - p.clat) / 2)), 2) +
        cos(radians(p.clat)) * cos(radians(l.lat)) *
        pow(sin(radians((l.lon - p.clon) / 2)), 2)
      )) <= p.radius
ORDER BY distance_km
LIMIT 50;
```

### Worker Helper Function

```typescript
// src/services/geo-service.ts
import { D1Database } from '@cloudflare/workers-types';

interface GeoLocation {
  id: string;
  name: string;
  lat: number;
  lon: number;
  distance_km: number;
}

interface NearbyOptions {
  lat: number;
  lon: number;
  radiusKm: number;
  tenantId: string;
  category?: string;
  limit?: number;
}

const EARTH_RADIUS_KM = 6371.0;

/**
 * Returns locations within radiusKm of the given coordinate.
 * Uses a bounding-box pre-filter (indexed) + SQL Haversine refinement.
 */
export async function findNearby(
  db: D1Database,
  opts: NearbyOptions,
): Promise<GeoLocation[]> {
  const { lat, lon, radiusKm, tenantId, category, limit = 50 } = opts;

  // Bounding box deltas
  const dlat = radiusKm / 111.0;
  const dlon = radiusKm / (111.0 * Math.cos((lat * Math.PI) / 180));

  const haversine = `
    ${EARTH_RADIUS_KM} * 2 * asin(sqrt(
      pow(sin(radians((l.lat - ?) / 2)), 2) +
      cos(radians(?)) * cos(radians(l.lat)) *
      pow(sin(radians((l.lon - ?) / 2)), 2)
    ))
  `;

  const categoryClause = category ? 'AND l.category = ?' : '';
  const categoryParams = category ? [category] : [];

  const sql = `
    SELECT l.id, l.name, l.lat, l.lon,
           ${haversine} AS distance_km
    FROM locations l
    WHERE l.tenant_id = ?
      AND l.is_active = 1
      AND l.lat BETWEEN ? AND ?
      AND l.lon BETWEEN ? AND ?
      ${categoryClause}
      AND ${haversine} <= ?
    ORDER BY distance_km
    LIMIT ?
  `;

  // Parameter order must match the ? placeholders above
  const params = [
    // First haversine (distance_km in SELECT)
    lat, lat, lon,
    // WHERE clause
    tenantId,
    lat - dlat, lat + dlat,
    lon - dlon, lon + dlon,
    ...categoryParams,
    // Second haversine (in WHERE)
    lat, lat, lon,
    radiusKm,
    limit,
  ];

  const result = await db.prepare(sql).bind(...params).all<GeoLocation>();
  return result.results;
}

/**
 * Returns the N nearest locations regardless of distance.
 */
export async function findNearest(
  db: D1Database,
  opts: Omit<NearbyOptions, 'radiusKm'> & { n?: number },
): Promise<GeoLocation[]> {
  const { lat, lon, tenantId, n = 10 } = opts;

  // Use a generous initial bounding box (500 km) and rely on ORDER + LIMIT
  return findNearby(db, { ...opts, radiusKm: 500, limit: n });
}
```

## Geohash Bucketing Approach

Geohashes encode a lat/lon into a string where longer prefixes mean smaller tiles.
A prefix-match query retrieves all points in a tile without any math.

```typescript
// src/lib/geohash.ts — minimal geohash encoder (no external deps)
const BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz';

export function encode(lat: number, lon: number, precision = 6): string {
  let minLat = -90, maxLat = 90, minLon = -180, maxLon = 180;
  let hash = '';
  let bits = 0, bitsTotal = 0, hashValue = 0;
  const isEven = { value: true };

  while (hash.length < precision) {
    if (isEven.value) {
      const mid = (minLon + maxLon) / 2;
      if (lon >= mid) { hashValue = (hashValue << 1) + 1; minLon = mid; }
      else             { hashValue = hashValue << 1;        maxLon = mid; }
    } else {
      const mid = (minLat + maxLat) / 2;
      if (lat >= mid) { hashValue = (hashValue << 1) + 1; minLat = mid; }
      else             { hashValue = hashValue << 1;        maxLat = mid; }
    }
    isEven.value = !isEven.value;
    bits++;
    bitsTotal++;

    if (bits === 5) {
      hash += BASE32[hashValue];
      bits = 0;
      hashValue = 0;
    }
  }
  return hash;
}

/**
 * Returns the 9 neighboring geohash cells for a given hash.
 * Querying all 9 cells covers the area around a point even at tile boundaries.
 */
export function neighbors(hash: string): string[] {
  // Simplified: in production use a full neighbor algorithm
  // or the `ngeohash` library (inline it — no external CDN in Workers)
  return [hash]; // placeholder — replace with real neighbor computation
}
```

```typescript
// Geohash-based search
export async function findByGeohash(
  db: D1Database,
  lat: number,
  lon: number,
  precision: 5 | 6 = 6,
): Promise<GeoLocation[]> {
  const hash = encode(lat, lon, precision);
  const cells = neighbors(hash);   // current cell + 8 neighbors

  // Build placeholders for IN clause
  const placeholders = cells.map(() => '?').join(', ');
  const column = precision === 6 ? 'geohash6' : 'geohash5';

  const result = await db
    .prepare(`
      SELECT id, lat, lon
      FROM locations_geo
      WHERE ${column} IN (${placeholders})
    `)
    .bind(...cells)
    .all<GeoLocation>();

  // Refine with Haversine in JS (small candidate set after geohash filter)
  return result.results
    .map((loc) => ({
      ...loc,
      distance_km: haversineKm(lat, lon, loc.lat, loc.lon),
    }))
    .sort((a, b) => a.distance_km - b.distance_km);
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}
```

## Choosing Precision and Radius

| Geohash precision | Tile size (approx.) | Use-case |
|:-----------------:|---------------------|----------|
| 4 | 39 km × 20 km | Country-level |
| 5 | 4.9 km × 4.9 km | City-level "nearby" |
| 6 | 1.2 km × 0.6 km | Neighborhood |
| 7 | 153 m × 153 m | Street-level |

For a "within 5 km" search, use geohash precision 5 and query 9 neighbor cells.
For a "within 500 m" search, use precision 6 or 7.

The bounding-box formula scales the degree delta correctly for latitude:

```
dlat = radius_km / 111.0
dlon = radius_km / (111.0 * cos(lat_radians))
```

Note that `dlon` grows toward the poles (1 degree of longitude covers less distance
near the equator but SQLite math handles this correctly).

## Anti-patterns

- **Using `ORDER BY distance LIMIT N` without a bounding box**: A full table scan
  computing Haversine for every row is extremely slow at scale. Always use the
  bounding box first.
- **Storing lat/lon as TEXT**: Comparisons like `lat BETWEEN ? AND ?` require
  numeric types. Store as `REAL` (SQLite's 64-bit float), not TEXT.
- **Expecting meter-level precision from Haversine**: The formula is accurate to
  about 0.5% for distances under 1 000 km. For exact distance calculations
  (mapping, navigation), use Vincenty's formula instead.
- **Querying only the center cell in geohash approach**: Points just across a tile
  boundary are missed. Always query the center cell plus 8 neighbors.
- **Indexing only lat or only lon**: A compound `(lat)` index helps the bounding
  box filter on latitude but leaves longitude as a post-filter. For best results,
  create separate indexes on `lat` and `lon` and let SQLite's query planner pick
  the most selective, or use a compound `(lat, lon)` index with a covering
  select list.

## Gotchas

- SQLite's `cos()`, `sin()`, `asin()`, `sqrt()` math functions require the library
  to be compiled with `-DSQLITE_ENABLE_MATH_FUNCTIONS`. D1 enables these. Verify
  with `SELECT cos(0);` — should return `1.0`.
- At latitudes above 70°N or below 70°S, the longitude delta formula produces very
  large values. Clamp `dlon` to 180 as a safety guard.
- The bounding box is a rectangle in lat/lon space, not a circle. It over-selects
  near the corners. The Haversine post-filter removes these false positives but
  you pay for the index scan of the extra rows.
- D1's row limit per query result (currently 10 000 rows) can be hit if the
  bounding box is very large. Always include a `LIMIT` clause.

## Verification

```sql
-- Spot-check: distance from London (51.5074, -0.1278) to Paris (48.8566, 2.3522)
-- Expected: ~340 km
SELECT 6371.0 * 2 * asin(sqrt(
  pow(sin(radians((48.8566 - 51.5074) / 2)), 2) +
  cos(radians(51.5074)) * cos(radians(48.8566)) *
  pow(sin(radians((2.3522 - (-0.1278)) / 2)), 2)
)) AS distance_km;

-- Verify index is used for bounding box query
EXPLAIN QUERY PLAN
SELECT id FROM locations
WHERE lat BETWEEN 51.0 AND 52.0
  AND lon BETWEEN -1.0 AND 1.0;
-- Expected: SEARCH locations USING INDEX idx_locations_tenant_lat (or similar)

-- Count candidates returned by bounding box vs exact filter (should be close)
SELECT
  COUNT(*) FILTER (WHERE lat BETWEEN 50.0 AND 53.0 AND lon BETWEEN -3.0 AND 3.0) AS bbox_count,
  COUNT(*) FILTER (WHERE
    6371.0 * 2 * asin(sqrt(
      pow(sin(radians((lat - 51.5074) / 2)), 2) +
      cos(radians(51.5074)) * cos(radians(lat)) *
      pow(sin(radians((lon - (-0.1278)) / 2)), 2)
    )) <= 150
  ) AS exact_count
FROM locations;
-- bbox_count should be within ~20% of exact_count for a good bounding box
```

## Related

- `postgis-spatial-data.md` — PostGIS extension for full spatial queries in Postgres
- `d1-sqlite-query-optimization.md` — EXPLAIN QUERY PLAN for D1
- `d1-json-column-patterns.md` — storing GeoJSON shapes in JSON columns
- `d1-vector-hybrid-search-vectorize.md` — Vectorize for semantic proximity search
- `partial-indexes.md` — index only active locations to reduce index size

## Sources

- SQLite math functions: sqlite.org/lang_mathfunc.html
- Haversine formula: movable-type.co.uk/scripts/latlong.html
- Geohash specification: en.wikipedia.org/wiki/Geohash
- Cloudflare D1 limits: developers.cloudflare.com/d1/platform/limits
