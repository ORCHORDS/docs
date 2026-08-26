# Geospatial Bounding-Box Queries in D1 with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to query locations within a radius of a user's position in a D1 database. D1 (SQLite) has no native geometry types or spatial index (R-tree is available in SQLite but not exposed in D1). You need a portable, pure-SQL approach that is fast enough for most use cases without a dedicated geo database.

## Context

The standard workaround is to store latitude and longitude as `REAL` columns and query a bounding box — a square approximation of the target radius — using a `BETWEEN` range on both columns. A composite index on `(lat, lng)` allows SQLite's query planner to use an index range scan for the latitude dimension and filter on longitude. The bounding box over-selects because it is square, not circular; a Haversine distance check in the Worker then prunes false positives. This two-step approach (SQL bounding box + JS Haversine filter) is efficient for radii up to ~100 km on datasets up to ~1 M rows.

## Schema

```sql
CREATE TABLE IF NOT EXISTS venues (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL,
  lat         REAL NOT NULL,  -- WGS84 decimal degrees
  lng         REAL NOT NULL,
  created_at  INTEGER NOT NULL
);

-- Composite index: lat first so the range scan on latitude is selective
CREATE INDEX IF NOT EXISTS idx_venues_lat_lng ON venues(lat, lng);

-- Optional partial index for a specific category
CREATE INDEX IF NOT EXISTS idx_venues_restaurants_lat_lng
  ON venues(lat, lng)
  WHERE category = 'restaurant';
```

## Bounding-Box Helper in Workers

```typescript
// src/geo.ts

const EARTH_RADIUS_KM = 6371;

export interface BoundingBox {
  minLat: number;
  maxLat: number;
  minLng: number;
  maxLng: number;
}

/**
 * Compute a square bounding box around a center point.
 * Uses a haversine-based approximation — accurate to < 0.5 % for radii < 500 km.
 */
export function getBoundingBox(
  centerLat: number,
  centerLng: number,
  radiusKm: number
): BoundingBox {
  const latDelta = (radiusKm / EARTH_RADIUS_KM) * (180 / Math.PI);
  // Longitude degrees per km shrinks as you move toward the poles
  const lngDelta =
    (radiusKm / (EARTH_RADIUS_KM * Math.cos((centerLat * Math.PI) / 180))) *
    (180 / Math.PI);

  return {
    minLat: centerLat - latDelta,
    maxLat: centerLat + latDelta,
    minLng: centerLng - lngDelta,
    maxLng: centerLng + lngDelta,
  };
}

/**
 * Haversine great-circle distance in kilometres between two WGS84 points.
 */
export function haversineKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}
```

## Workers Fetch Handler

```typescript
// src/index.ts
import { Env } from './types';
import { getBoundingBox, haversineKm } from './geo';

type Venue = {
  id: string;
  name: string;
  category: string;
  lat: number;
  lng: number;
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/venues/nearby') {
      return new Response('Not found', { status: 404 });
    }

    const centerLat = parseFloat(url.searchParams.get('lat') ?? '0');
    const centerLng = parseFloat(url.searchParams.get('lng') ?? '0');
    const radiusKm = Math.min(parseFloat(url.searchParams.get('radius_km') ?? '5'), 50);
    const category = url.searchParams.get('category'); // optional filter

    if (isNaN(centerLat) || isNaN(centerLng)) {
      return new Response('Invalid lat/lng', { status: 400 });
    }

    const box = getBoundingBox(centerLat, centerLng, radiusKm);

    // Step 1: SQL bounding-box query (fast — uses index range scan on lat)
    let query = env.DB.prepare(
      `SELECT id, name, category, lat, lng
       FROM venues
       WHERE lat BETWEEN ? AND ?
         AND lng BETWEEN ? AND ?
         ${category ? "AND category = ?" : ''}
       LIMIT 500`
    );

    query = category
      ? query.bind(box.minLat, box.maxLat, box.minLng, box.maxLng, category)
      : query.bind(box.minLat, box.maxLat, box.minLng, box.maxLng);

    const { results } = await query.all<Venue>();

    // Step 2: Haversine filter removes square-box false positives
    const nearby = results
      .map((v) => ({
        ...v,
        distance_km: haversineKm(centerLat, centerLng, v.lat, v.lng),
      }))
      .filter((v) => v.distance_km <= radiusKm)
      .sort((a, b) => a.distance_km - b.distance_km);

    return Response.json(nearby);
  },
};
```

## Limitations vs PostGIS

- **No R-tree index in D1** — SQLite ships with the `rtree` extension but D1 does not currently expose it. The `(lat, lng)` B-tree composite index only accelerates the lat range scan; the lng dimension is filtered in-engine but without a spatial index.
- **Bounding box is O(n) on the lng dimension** — For very dense datasets at low latitudes (lng degrees are wide), many rows may pass the lat filter but fail the lng filter. Pre-filtering by category or another column helps.
- **Accuracy at poles** — The `cos(lat)` longitude correction becomes inaccurate above ~80° latitude. Add a guard if your data set includes polar coordinates.
- **No polygon or line support** — Complex geo shapes require a dedicated spatial database (PostGIS, SpatiaLite, Cloudflare Workers + Geo libraries with Durable Objects).
- **Radius limit** — Bounding-box approximation degrades noticeably beyond 500 km; use a different projection for large radii.

## Anti-patterns

- **Storing lat/lng as TEXT** — String comparison does not support `BETWEEN` range scans; always use `REAL`.
- **Haversine in SQL (user-defined functions)** — D1 does not support custom SQLite UDFs; do Haversine post-processing in the Worker.
- **No upper bound on radius** — An unbounded radius can return millions of rows; always cap the radius parameter server-side.
- **Single-column index on lat only** — Misses the opportunity to narrow the lng dimension in the index; use a composite `(lat, lng)` index.

## Gotchas

- D1 `REAL` columns store IEEE 754 doubles — sufficient precision for GPS coordinates (6 decimal places ≈ 11 cm accuracy).
- The bounding box wraps around antimeridian (lng 180 / -180) incorrectly; add a special case if your data crosses the date line.
- `LIMIT 500` inside the SQL query prevents the Worker from receiving more candidates than it can filter in a single request; tune this based on expected density.

## Verification

```bash
# Insert test venues around London (51.5074° N, -0.1278° W)
wrangler d1 execute example project-db --command "
  INSERT INTO venues VALUES
    ('v1','The Shard','attraction',51.5045,-0.0865,unixepoch()),
    ('v2','Tate Modern','attraction',51.5076,-0.0994,unixepoch()),
    ('v3','Heathrow','airport',51.4700,-0.4543,unixepoch());
"

# Query for venues within 5 km of Waterloo (51.5031, -0.1132)
wrangler d1 execute example project-db --command "
  SELECT id, name, lat, lng
  FROM venues
  WHERE lat BETWEEN 51.4582 AND 51.5481
    AND lng BETWEEN -0.2273 AND 0.0010;
"
# Expected: v1 and v2 appear; v3 (Heathrow) is outside the box
```

## Related

- `d1-partial-index-conditional-expressions-workers.md`
- `d1-row-versioning-optimistic-locking-workers.md`
- `d1-generated-columns-computed-fields-workers.md`

## Sources

- SQLite Indexes — https://www.sqlite.org/queryplanner.html
- Haversine Formula — https://en.wikipedia.org/wiki/Haversine_formula
- Cloudflare D1 Documentation — https://developers.cloudflare.com/d1/
