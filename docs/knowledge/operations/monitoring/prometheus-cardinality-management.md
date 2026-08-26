# prometheus-cardinality-management

**Issue:** Detecting and reducing high metric cardinality in Prometheus
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Prometheus OOMs or slows down because a metric has millions of time series due to high-cardinality labels.

## Pattern / Solution
Find high-cardinality metrics:
```promql
# Top 10 metrics by series count
topk(10, count by (__name__)({__name__=~".+"}))
```

Identify problematic label values:
```promql
count by (route) (http_requests_total) > 1000
```

Mitigation strategies:
1. **Drop labels at scrape time:**
```yaml
metric_relabel_configs:
  - source_labels: [user_id]
    action: labeldrop
```

2. **Aggregate at recording rule level before exposing:**
```yaml
- record: api:requests:rate5m
  expr: sum by (method, status) (rate(http_requests_total[5m]))
```

3. **Use exemplars** for high-cardinality attributes (trace IDs) instead of labels.

## Gotchas
- `count({__name__=~".+"})` can itself be expensive; run during off-peak
- Some client libraries expose high-cardinality metrics by default (e.g., per-path routing)
- Remote write can filter metrics before they leave the scraper

## Related
- `prometheus-labels-best-practices.md`
- `prometheus-remote-write.md`
