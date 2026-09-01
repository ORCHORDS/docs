# Load Testing K6 Script Versioning Regression

A load test is a measurement instrument, and like any instrument it must be calibrated
against a known baseline to be useful. A k6 script that measures p99 latency against an
endpoint is meaningful only if it measures it the same way the previous script did; a
script that has drifted in its scenario, in its thresholds, or in its data shape produces
a measurement that is not comparable to the prior run. Script versioning is the discipline
that makes a load test comparable across releases: every script change is a numbered version,
every run is annotated with the script version, and every regression claim is anchored to
the difference between two specific script versions running against two specific
deployment versions.

## Scope

Covers the version management of k6 load test scripts, the metadata that ties a k6 run to
its script version, the comparison of two runs as the basis for a regression gate, and the
integration with CI for performance regression gating. Applies to k6 scripts written in
JavaScript or TypeScript, run locally, in k6 Cloud, or in a CI pipeline. Does not cover
the design of the load scenarios themselves (ramp-up, soak, stress) or the SUT
optimisation that follows a finding.

## Workflow or implementation guidance

1. **Version the script in the repository.** A k6 script is source code; it belongs in the
   repository alongside the SUT it exercises. Versioning happens via git; each script change
   is a commit, each release is a tag. A k6 script maintained outside the repository (for
   example, in a wiki) cannot be diffed, reviewed, or rolled back.
2. **Embed version metadata in the script's output.** Each k6 run emits a JSON summary that
   downstream tooling consumes. Stamp the summary with: git SHA of the script, git SHA of
   the SUT under test, environment identifier, scenario name, and a run id. The summary
   without these fields is a measurement without provenance; it cannot be compared to
   another run.
3. **Standardise on the thresholds file.** k6 supports thresholds expressed inline in the
   script or in a separate thresholds file. A separate file allows the same script to be
   run against different threshold profiles (smoke vs production). Pin the threshold
   profile to the environment; do not let the script's inline thresholds drift across
   environments.
4. **Tag the scenarios by intent.** A single k6 script may run multiple scenarios (smoke,
   load, stress, soak). Each scenario is identified by name; the output records which
   scenario was active. A regression claim must name the scenario, because the same
   endpoint can behave differently across scenarios.
5. **Treat data shape as part of the script version.** The payload the script sends affects
   the cache hit rate, the database query plan, the response size. Changing the payload is
   a script change that requires its own version bump and its own baseline reset. A
   regression claim made by a script whose payload changed since the baseline is not
   credible.
6. **Establish a baseline before claiming a regression.** A new script version needs a
   baseline run against a known-good deployment of the SUT. The baseline is the reference
   against which all subsequent runs are compared. A script that ships without a baseline
   produces measurements that cannot be used to make regression claims.
7. **Compare runs by metric, scenario, and threshold breach, not by total numbers.** Two
   runs at the same load level will not produce identical numbers; what matters is whether
   the thresholds were breached. The comparison output should highlight threshold
   breaches, not absolute numbers, with the delta visible.
8. **Version the comparison tooling.** The script that diffs two k6 summaries is itself
   code; it needs its own version. A comparison tool that changes its heuristics silently
   produces "regressions" that are actually tool changes.
9. **Persist run summaries in object storage.** A k6 run summary is a small JSON artefact;
   persist each run's summary in object storage keyed by `(script_version, deployment_version,
   environment)`. Long-term retention enables historical regression analysis and supports
   capacity planning that looks back over months of runs.
10. **Gate CI on threshold breaches from the current script version.** The CI pipeline runs
    the k6 script against a candidate deployment; if the threshold is breached, the build
    fails. The gate uses the *current* script version's thresholds, not a baseline run's
    thresholds; otherwise the gate is always comparing against yesterday's contract.

A representative k6 script header that stamps the run with metadata:

```js
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

export const options = {
  thresholds: {
    http_req_duration: ['p(99)<400'],
    http_req_failed: ['rate<0.01'],
  },
  tags: {
    script_git_sha: __ENV.SCRIPT_GIT_SHA,
    sut_git_sha: __ENV.SUT_GIT_SHA,
    environment: __ENV.TARGET_ENV,
  },
};

export default function () {
  // ...
}
```

The `tags` propagate to every metric in the summary; downstream tooling filters and groups
by tag.

## Controls

- Script changes are reviewed like SUT changes; merges without review are not allowed.
- The summary is required to include git SHA, environment, and scenario; summaries without
  these fields are rejected by the ingestion step.
- Baselines are pinned to `(script_version, deployment_version, environment)` tuples; an
  outdated baseline produces a comparison that flags noise as a regression.
- Threshold profiles are reviewed when the script's scenarios change; profile drift is
  treated as a script change.
- Run summaries are retained for the agreed period (typically 90 days for production
  environments, longer for capacity-planning data).

## Validation evidence

- A deliberate slowdown is introduced on the SUT; the k6 run against the candidate
  deployment shows the threshold breached, and CI fails. The rehearsal proves the gate is
  wired.
- A script change that alters the payload is observed to produce a different cache hit
  rate; the change is recorded as a payload change, the baseline is reset, and the
  regression claim is anchored to the new baseline.
- A historical run summary is queryable by `script_git_sha`, `sut_git_sha`, and
  `environment`; spot checks demonstrate the metadata is present and accurate.
- A comparison of two runs at the same script version and different SUT versions shows
  the expected difference; the comparison tool does not produce a regression claim when
  the threshold was not breached.

## Failure modes and correction

- *Script changes silently between runs.* Pin the script to a git SHA in CI; do not run
  from a working tree.
- *Threshold changes silently.* Pin the threshold profile; review threshold changes
  explicitly.
- *Payload changes silently.* Tag the payload's shape and content; any change requires a
  baseline reset.
- *Baseline never refreshed.* A baseline that is months old does not reflect the current
  SUT; the comparison flags noise. Reset the baseline when the SUT changes by an amount
  that affects the measurements.
- *Comparison uses absolute numbers.* Threshold breaches are the signal; an absolute
  number comparison flags every minor variation as a regression.
- *Run summaries not persisted.* A regression claim made without historical summaries
  cannot be investigated; persist every summary and back the retention policy with
  monitoring.
- *k6 version itself drifts.* Pin the k6 binary version in CI; different k6 versions
  produce subtly different metric calculations.

## Limitations

- k6 measures the SUT's behaviour under the load the script generates. The script is a
  model of real traffic, not real traffic itself; gaps between the model and reality are
  gaps in the test.
- Load test results are noisy. A single run is not a baseline; a baseline is a distribution
  over multiple runs against the same deployment, and a regression is a deviation outside
  that distribution.
- Cloud-rendered k6 Cloud runs introduce their own variance (network paths, runner
  locations); cross-environment comparison without environment normalisation produces
  false regressions.
- Performance regressions inside k6 are sometimes regressions of the test harness, not of
  the SUT. Without provenance metadata the wrong fix is applied.
- Long-running soak tests produce gigabytes of data; summarisation at the k6 side is
  necessary, and the summary is necessarily lossy. Granular drill-down requires storing
  raw samples, which is expensive.

## Canonical sources

- Grafana, *k6 documentation* (thresholds, scenarios, summary format, and tagging):
  https://grafana.com/docs/k6/latest/
- Grafana, *k6 testing guides* (test-type taxonomy, scripting patterns, and CI
  integration):
  https://grafana.com/docs/k6/latest/testing-guides/test-types/
- Cloudflare, *k6 on Cloudflare Workers* (k6 load testing patterns against Worker-deployed
  APIs): https://developers.cloudflare.com/workers/testing/
