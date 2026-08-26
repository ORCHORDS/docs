# postgis-spatial-data

**Issue:** Storing and querying geographic coordinates efficiently in Postgres
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Calculating distances, finding points within radius, or querying geographic boundaries. Naive approach stores lat/lng floats and uses Haversine formula in application code -- slow and not indexable.

## Pattern / Solution
Enable PostGIS extension. Use geography column type for lat/lng. Create GiST index on the column. Radius query: SELECT * FROM locations WHERE ST_DWithin(position, ST_MakePoint(lng, lat)::geography, 1000) for 1000 meters.

## Gotchas
- geometry is planar (fast); geography is spherical (accurate for large distances, ~10% slower)
- SRID must be consistent -- WGS84 (SRID 4326) for GPS coordinates
- VACUUM on GiST indexes is important; they bloat faster than B-tree

## Related
- postgres-extensions-useful
- partial-indexes
- index-selectivity
