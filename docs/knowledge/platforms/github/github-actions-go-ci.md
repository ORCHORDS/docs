# github-actions-go-ci

**Issue:** Go CI workflow with module caching, vet, and test coverage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Go projects need CI that caches modules, runs `go vet`, and reports test coverage without slow repeated downloads.

## Pattern / Solution
```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: go.mod
          cache: true
      - run: go vet ./...
      - run: go test -race -coverprofile=coverage.out ./...
      - uses: codecov/codecov-action@v4
        with:
          files: coverage.out
```
Matrix across multiple Go versions:
```yaml
    strategy:
      matrix:
        go: ["1.22", "1.23"]
```

## Gotchas
- `go-version-file: go.mod` picks the `go` directive automatically — no hard-coded version needed.
- `cache: true` in `setup-go` uses the module cache (`GOPATH/pkg/mod`).
- `-race` detector requires CGO; it is enabled by default on Linux but not on `windows-latest`.
- `go test ./...` includes test binaries; use `-count=1` to disable result caching during flaky investigation.

## Related
- `github-actions-cache-dependencies.md`
- `github-actions-timeout-jobs.md`
