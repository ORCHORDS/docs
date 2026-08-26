# Cloudflare Analytics Engine Grafana Dashboard

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

The team wants to visualise Cloudflare Analytics Engine (WAE) custom
metrics — mobile vs desktop request rates, p99 latency by route, and
error rates — inside Grafana alongside Prometheus data. The existing
Cloudflare dashboard in the Grafana marketplace does not query WAE;
it only surfaces the standard zone analytics. Custom SQL panels and
alert rules pointing at the WAE SQL API are missing.

## Context

Cloudflare's community Grafana datasource plugin (`grafana-cloudflare-
datasource`, maintained by Cloudflare) exposes the Analytics Engine
SQL API as a Grafana datasource backend. Once provisioned, Grafana
variables, panels, and alert rules can query WAE data with the same
ClickHouse-compatible SQL that the REST API accepts. The plugin uses
the Account Analytics Read token, not a Cloudflare API Gateway
routing key. example project (example.com) writes one data point per Worker
request with device type in `blob3`.

## Datasource plugin setup

Install the plugin on the Grafana instance or via Docker:

```bash
# Grafana Cloud — install from plugin catalogue
# Self-hosted: add to GF_INSTALL_PLUGINS env var
GF_INSTALL_PLUGINS=grafana-cloudflare-datasource

# Docker
docker run -e "GF_INSTALL_PLUGINS=grafana-cloudflare-datasource" \
  -p 3000:3000 grafana/grafana
```

Provision via YAML (recommended for GitOps):

```yaml
# grafana/provisioning/datasources/cloudflare-ae.yaml
apiVersion: 1
datasources:
  - name: CloudflareAE
    type: grafana-cloudflare-datasource
    uid: cloudflare-ae
    jsonData:
      accountId: "${CF_ACCOUNT_ID}"
    secureJsonData:
      apiToken: "${CF_API_TOKEN}"   # scope: Account Analytics Read
    editable: false
```

The plugin sends queries to:
`https://api.cloudflare.com/client/v4/accounts/{accountId}/analytics_engine/sql`

## SQL panel patterns

### Mobile vs desktop request rate

```sql
SELECT
  toStartOfMinute(timestamp)              AS time,
  blob3                                   AS device_type,
  count()                                 AS requests
FROM prod_metrics
WHERE
  $__timeFilter(timestamp)
GROUP BY time, device_type
ORDER BY time ASC
```

Set **Format** to *Time series* and **Group by** to `device_type`.
Grafana renders separate series for `mobile`, `desktop`, `tablet`.

### p99 latency by route (table panel)

```sql
SELECT
  blob1                         AS route,
  quantile(0.50)(double1)       AS p50_ms,
  quantile(0.95)(double1)       AS p95_ms,
  quantile(0.99)(double1)       AS p99_ms,
  count()                       AS requests
FROM prod_metrics
WHERE $__timeFilter(timestamp)
GROUP BY route
ORDER BY p99_ms DESC
LIMIT 20
```

### Error rate by device type (stat panel)

```sql
SELECT
  blob3                                           AS device_type,
  round(sum(double2) / count() * 100, 2)         AS error_pct
FROM prod_metrics
WHERE
  $__timeFilter(timestamp)
  AND blob3 IN ('mobile', 'desktop')
GROUP BY device_type
```

Map `device_type` to a Grafana variable `$device` using a constant
or query variable pointing at a distinct-values query.

## Dashboard variables

```
# Variable: $route
SELECT DISTINCT blob1 AS route
FROM prod_metrics
WHERE $__timeFilter(timestamp)
ORDER BY route

# Variable: $colo
SELECT DISTINCT indexes[1] AS colo
FROM prod_metrics
WHERE $__timeFilter(timestamp)
ORDER BY colo
```

Add `All` option to both. Reference in WHERE clauses:

```sql
WHERE blob1 = '$route'
  AND indexes[1] = '$colo'
  AND $__timeFilter(timestamp)
```

## Alert rules

WAE has 1–5 min ingestion lag; set **Evaluate every** to `5m` and
**For** to `10m` to avoid flapping on lag windows.

```yaml
# grafana/provisioning/alerts/wam-mobile-error-rate.yaml
apiVersion: 1
groups:
  - name: example project-ae-alerts
    folder: example project
    interval: 5m
    rules:
      - uid: ae-mobile-err-rate
        title: Mobile error rate > 5% (WAE)
        condition: C
        data:
          - refId: A
            datasourceUid: cloudflare-ae
            model:
              rawSql: |
                SELECT
                  toStartOfMinute(timestamp)                    AS time,
                  round(sum(double2)/count()*100, 2)           AS mobile_err_pct
                FROM prod_metrics
                WHERE timestamp > NOW() - INTERVAL '15' MINUTE
                  AND blob3 = 'mobile'
                GROUP BY time
                ORDER BY time ASC
              format: time_series
          - refId: C
            type: math
            expression: $A > 5
        noDataState: NoData
        execErrState: Alerting
        for: 10m
        annotations:
          summary: Mobile error rate {{ $values.A.Value }}% over last 15 min
        labels:
          severity: warning
          team: platform
```

| Panel type  | WAE field    | Grafana format | Notes                             |
|-------------|--------------|----------------|-----------------------------------|
| Time series | `timestamp`  | Time series    | Use `$__timeFilter(timestamp)`    |
| Table       | any          | Table          | Good for route-level p99          |
| Stat        | aggregated   | Table (1 row)  | Override unit to `percent (0-100)`|
| Alert       | aggregated   | Time series    | Min eval interval 5 min           |

## Anti-patterns

- **Using `$__timeFrom()` / `$__timeTo()` raw macros** — the plugin
  exposes `$__timeFilter(timestamp)` as the supported macro; raw
  epoch substitution breaks on timezone offsets.
- **Setting alert evaluation interval to < 5 min** — WAE ingestion
  lag causes spurious NoData states and alert churn.
- **Writing raw user IDs into blobs** — they appear in Grafana
  Explore query results which may be visible to all Grafana users;
  use opaque tenant slugs instead.
- **Joining WAE data with Prometheus in a single panel** — the
  plugin does not support mixed datasource panels; use a Grafana
  Transformations join after two separate queries in a table panel.

## Gotchas

- The `$__timeFilter(timestamp)` macro expands to a ClickHouse
  `timestamp BETWEEN epoch_s AND epoch_s` expression; it does not
  accept a column alias.
- Grafana panel previews execute the SQL query live on every save;
  complex aggregations over wide windows may hit the 5 s WAE timeout
  — narrow the default time range to 1 h in the dashboard settings.
- The plugin authenticates with a Cloudflare API token, not a
  Cloudflare Access service token. The token needs Account scope,
  not Zone scope.
- Alert rule state history is stored in Grafana's internal database,
  not in WAE; Grafana downtimes or restarts lose in-memory alert
  state before the `For` window completes.
- Grafana Cloud free tier imposes a 10 active alert rules limit;
  WAE alert rules count against this total.

## Verification

- Datasource health check: Settings → CloudflareAE → Test; expects
  HTTP 200 from the SQL API.
- Panel smoke test: query `SELECT count() FROM prod_metrics WHERE
  timestamp > NOW() - INTERVAL '1' HOUR` returns a non-zero row.
- Variable population: `$route` dropdown shows at least 3 routes
  after selecting last-24h range.
- Alert rule fires correctly against a synthetic spike injected via
  a staging Worker writing `double2 = 1` for 15 consecutive minutes.
- Mobile vs desktop panel shows two distinct series within 10 minutes
  of a real mobile request reaching the Worker.

## Related

- `documentation/categories/monitoring/cloudflare-analytics-engine-custom-metrics.md`
- `documentation/categories/monitoring/cloudflare-analytics-engine.md`
- `documentation/categories/monitoring/grafana-setup.md`
- `documentation/categories/monitoring/grafana-alerts-setup.md`
- `documentation/categories/monitoring/grafana-datasource-config.md`
- `documentation/categories/monitoring/rum-mobile-desktop-cwv-disparity.md`

## Sources

- Cloudflare Analytics Engine SQL API —
  https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Grafana Cloudflare datasource plugin —
  https://grafana.com/grafana/plugins/grafana-cloudflare-datasource/
- WAE ClickHouse SQL reference —
  https://developers.cloudflare.com/analytics/analytics-engine/sql-reference/
- Grafana provisioning datasources —
  https://grafana.com/docs/grafana/latest/administration/provisioning/#datasources
- Grafana alert rule provisioning —
  https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/
