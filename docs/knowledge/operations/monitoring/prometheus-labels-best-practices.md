# prometheus-labels-best-practices

**Issue:** Designing Prometheus label sets without causing cardinality explosions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Prometheus memory usage spikes and query performance degrades due to high-cardinality labels like user IDs or request IDs.

## Pattern / Solution
Good labels (low cardinality, high utility):
```
job, instance, env, region, status_code_class, method, route_template
```

Bad labels (never use):
```
user_id, request_id, session_id, email, ip_address
```

Naming conventions:
```
# Unit in metric name, not label
http_request_duration_seconds  # good
http_request_duration{unit="ms"}  # bad

# Use snake_case
cache_hit_total  # good
cacheHit  # bad
```

Label value guidelines:
- Keep cardinality < 10 per label dimension
- Use `route_template` (/users/:id) not `route` (/users/12345)
- Normalize HTTP status to class: 2xx, 4xx, 5xx

## Gotchas
- Each unique label combination creates a new time series
- Retroactively removing labels requires metric rename and migration
- Client libraries enforce label naming at registration time

## Related
- `prometheus-cardinality-management.md`
- `prometheus-scrape-config.md`
