# DNS Negative Caching Can Outlive the Fix

**Issue:** After a record is created or restored, resolvers may continue returning a cached NXDOMAIN or NODATA response, making recovery appear inconsistent by network and region.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Treat negative-cache TTL as part of DNS change and incident planning.
- Precreate names before cutover when practical and avoid probing undelegated names from production clients.
- Measure authoritative and recursive responses separately during recovery.
- Communicate the maximum negative-cache window and avoid repeated unrelated changes.

## Verification

- Query a missing name through representative recursive resolvers, then create it and measure recovery.
- Test NXDOMAIN and NODATA cases separately.
- Verify monitoring queries authoritative servers as well as user-path resolvers.

## Gotchas

- Lowering the positive record TTL does not retroactively lower cached negative answers.
- Resolver implementations may cap or alter TTL behavior.

## Official sources

- https://www.rfc-editor.org/rfc/rfc2308.html
