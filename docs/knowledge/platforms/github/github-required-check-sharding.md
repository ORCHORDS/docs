# GitHub Required Check Sharding and Report Aggregation

## Cover

GitHub's required check sharding enables parallel CI execution by distributing test jobs across multiple runners while maintaining required check compliance. This approach uses matrix fan-out to split workloads, blob upload for artifact storage, and merge report aggregation to combine results into a single required status.

## Symptom

When implementing parallel CI with required checks, you may encounter:
- Required check failures due to incomplete shard reporting
- Inconsistent status updates across multiple jobs
- Missing aggregated results in the final commit status
- Timeout errors during report merging operations

## Gotchas

### Matrix Fan-out Configuration
Matrix fan-out requires careful partitioning to ensure all code paths are covered. Uneven distribution can cause some shards to take significantly longer, blocking overall completion.

### Required Aggregate Gate Issues
The required aggregate gate must be configured to wait for all shards before reporting completion. Without proper synchronization, GitHub may mark the check as failed if intermediate results aren't properly aggregated.

### Blob Upload Limitations
Large artifact uploads can fail due to size limits or network issues. Always implement retry mechanisms and validate blob integrity before proceeding with merge operations.

### Merge Report Complexity
Merging reports from multiple shards requires careful handling of test result formats, timestamps, and status codes. Inconsistent data structures can cause aggregation failures.

## Practical Implementation

```yaml
name: Required Check Sharding
on: [push, pull_request]

jobs:
  shard-tests:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - uses: actions/checkout@v3
      - name: Run shard tests
        run: |
          # Execute tests for this shard
          npm test -- --shard=${{ matrix.shard }}
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: test-results-${{ matrix.shard }}
          path: test-results-${{ matrix.shard }}.json

  aggregate-results:
    needs: shard-tests
    steps:
      - name: Download all shard results
        uses: actions/download-artifact@v3
      - name: Merge reports
        run: |
          # Combine all shard results into single report
          python merge_reports.py
      - name: Upload aggregated results
        uses: actions/upload-artifact@v3
        with:
          name: aggregated-results
