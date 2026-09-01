# k6 Thresholds and CSV Export for Load-Test Reporting

A load test without pass/fail criteria is a graph, not a gate. k6's threshold mechanism attaches numeric assertions to metrics (`http_req_duration` under 500ms at p95, error rate under 1%), and when the run ends, each threshold passes or fails the exit code. Pair that with machine-readable output — CSV export of summary metrics — and load testing graduates from a dashboard someone glances at to a CI gate with an audit trail. This article covers writing meaningful thresholds, threshold-abort behavior, exporting results via the end-of-test summary to CSV, and wiring both into CI reporting.

## Scope

This article addresses k6 thresholds and results export: threshold syntax on built-in and custom metrics, aggregation selectors (avg, p(n), count, rate), `abortOnFail`, grace periods, the `handleSummary` callback for exporting end-of-test summaries (including CSV), and CI integration patterns. It does not cover scenario design (ramping VUs, soak profiles), k6 cloud output, or protocol-specific scripting beyond what thresholds reference.

## Workflow or implementation guidance

Thresholds live in the exported `options` object:

```js
export const options = {
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed:   ['rate<0.01'],
    checks:            ['rate>0.99'],
  },
};
```

Each entry is `metric: ['aggregation operator value']`. Aggregations: `avg`, `min`, `max`, `med`, `p(90)`, `p(95)`, `p(99)` (percentile of the value distribution), `count`, and for rates `rate`. Comparison operators `<` `<=` `>` `>=` `==` `===`. Multiple thresholds on one metric combine with AND; one failing threshold fails the run (exit code 99 by default).

Writing thresholds that mean something:

1. **Percentiles over averages.** Latency averages hide tail suffering; `p(95)` and `p(99)` are the industry-standard gates. Choose the percentile by product promise: an API with a 500 ms p95 SLO gates `p(95)<500`; a page-load experience gates p75/p90 as well because users feel the middle, not only the tail.
2. **Gate on both latency and correctness.** A fast-but-wrong system passes latency thresholds: always pair `http_req_failed` (rate of non-2xx/non-expected responses, controlled by `expected_response`) and `checks` (your scripted assertions) with duration thresholds.
3. **Custom metrics for business-shaped thresholds.** `counter`/`trend`/`gauge` metrics declared in the script capture domain events — `trend('checkout_latency', true)` (the second argument enables percentile computation on a custom trend, required before `p(95)` thresholds are legal on it) — so the gate speaks product language: `checkout_latency: ['p(90)<800']`.
4. **Sub-metric thresholds target the pain.** Thresholds can hang off tag-filtered sub-metrics: `'http_req_duration{endpoint:checkout}': ['p(95)<800']` gates one endpoint harder than the global bar, which is how realistic SLO tiers get expressed.
5. **`abortOnFail` for runaway protection.** `'http_req_failed': [{threshold: 'rate>0.05', abortOnFail: true}]` stops the test the moment the floor drops out, saving CI minutes on already-failed runs; `delayAbortEval: '30s'` avoids aborting on warm-up noise by evaluating only after a grace period.
6. **Thresholds are evaluated continuously** over the whole run (final values at end of test decide pass/fail; with abortOnFail, immediately when crossed). Design accordingly: a system that degrades monotonically fails at the end; one with a bad warm-up needs either a warm-up phase excluded via scenario tags (`name:warmup` excluded from threshold-bearing metrics by tagging requests) or `delayAbortEval`.

Exporting results. k6's `handleSummary(data)` callback receives the full end-of-test summary object (metrics, their aggregations, threshold results) and returns one or more destinations:

```js
import { csv } from 'k6/experimental/csv';

export function handleSummary(data) {
  return {
    'summary.csv': csv(data),
    stdout: textSummary(data),
  };
}
```

The `k6/experimental/csv` helper converts the summary to CSV rows; returning an object maps destinations to content: file paths are written, `stdout`/`stderr` special keys print, and remote HTTP endpoints POST the payload (that is how CI systems archive results). For per-request granularity rather than summary rows, use `--out csv=results.csv` (the machine-readable time-series output, one row per metric event) — heavier, but the right artifact when you need to re-aggregate percentiles offline or feed Grafana.

CI wiring pattern:

1. Run k6 with thresholds in the script; the process exit code gates the job.
2. `handleSummary` writes `summary.csv` (aggregate metrics + threshold outcomes) as a CI artifact next to the run log; `--out csv=` captures the raw series when deep-dive is expected.
3. A small report step renders the CSV into the job summary (Markdown table of metric/p95/threshold/pass-fail), so humans read the gate without downloading artifacts.
4. Retention: keep raw series for a rotation window (they are large); keep summary CSVs indefinitely — they are the audit trail of system behavior over time and small enough to store forever.

A worked example: a checkout service gates deployment on `p(95)<500` globally and `p(90)<800` on the checkout endpoint, error rate under 0.5%. A regression sneaks in that shifts checkout p90 to 1.2 s. The run fails with exit 99; the CI job blocks merge; `summary.csv` shows `http_req_duration{endpoint:checkout} p(90) 1.23s` against the 800 ms threshold. The engineer pulls the raw CSV artifact for the failed run and graphs the latency curve over the ramp, isolating the regression to a query plan change — the threshold turned a silent degradation into a blocked merge with evidence attached.

## Controls

- Every load-test script must carry at least one latency, one correctness, and one business-metric threshold; a script without thresholds fails review (it produces graphs, not verdicts).
- Pin the k6 version in CI; percentile computation and summary internals evolve, and CSV layouts must stay stable for the reporting pipeline.
- Archive `summary.csv` per run keyed by commit SHA and store the threshold configuration alongside (it is in the script — versioned with the code); the pairing answers "what did we gate and did it pass" for any historical run.
- Alert on threshold *changes* in review the same as SLO changes: tightening or loosening a threshold is a reliability-policy edit, visible in the PR diff by construction — keep it that way by never overriding thresholds ad hoc from CI command lines (`--thresholds` overrides bypass review).
- For flaky environments, prefer `delayAbortEval` and scenario-tagged warm-up exclusion over loosening thresholds; document each deliberate loosen with its justification in the PR.

## Validation evidence

- Threshold syntax, aggregation operators, sub-metric (tag-based) thresholds, `abortOnFail`, `delayAbortEval`, exit-code semantics, the `handleSummary` callback and its destinations, and the `k6/experimental/csv` helper are documented in the official k6 documentation at grafana.com (thresholds and results output sections).
- The `--out csv=` time-series export format is specified in the same documentation's data outputs reference.
- A reproducible check: run a script against a local test server with `http_req_duration: ['p(100)<10']` (impossible); observe exit 99 and the failing threshold listed in the summary; rerun with a sane bound and observe exit 0 and `summary.csv` containing the metric rows — a closed loop validating gate, exit code, and export in one pass.

## Failure modes and correction

- **Average-only thresholds.** Symptom: green gate, users complain about tail latency. Correct by percentile gates matched to the SLO.
- **Thresholds too tight for environment noise.** Symptom: CI load tests flake; teams ignore the gate. Correct by dedicated load environment, warm-up exclusion, and calibrated thresholds from measured baselines — then hold the line.
- **Missing correctness gate.** Symptom: fast 500s pass. Correct by pairing `http_req_failed` and `checks` rate thresholds.
- **Custom trend without percentile flag.** Symptom: `p(95)` threshold on a custom trend errors or compares garbage. Correct by enabling percentiles on the metric at declaration.
- **CI command-line threshold overrides.** Symptom: someone's branch passes by overriding; history diverges from repo config. Correct by disallowing `--thresholds` overrides in CI job templates.

## Limitations

- k6 thresholds evaluate one run's distribution; SLO compliance over weeks needs the exported data aggregated in monitoring, not single-run gates.
- `handleSummary` receives summary-level data; per-request analysis requires `--out` time-series output with its storage cost.
- Experimental modules (`k6/experimental/csv`) carry API-stability caveats; pin versions and re-verify on upgrade.
- CSV summary layout is k6-version-dependent; reporting pipelines parsing it must be version-locked to the runner.

## Canonical sources

- Grafana (k6), Thresholds documentation: https://grafana.com/docs/k6/latest/using-k6/thresholds/
- Grafana (k6), Results output end-of-test summary and CSV export documentation: https://grafana.com/docs/k6/latest/get-started/results-output/
