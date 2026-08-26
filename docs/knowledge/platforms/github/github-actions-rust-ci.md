# github-actions-rust-ci

**Issue:** Rust CI with Cargo caching, clippy, and cross-platform matrix
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Rust builds are slow due to incremental compilation artefacts. CI must cache `~/.cargo` and `target/` correctly.

## Pattern / Solution
```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: clippy, rustfmt
      - uses: Swatinem/rust-cache@v2
      - run: cargo fmt --check
      - run: cargo clippy --all-targets --all-features -- -D warnings
      - run: cargo test --all-features
```
Cross-platform matrix:
```yaml
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
```

## Gotchas
- `Swatinem/rust-cache` is the community standard; it keys on `Cargo.lock` and toolchain hash.
- `dtolnay/rust-toolchain` is preferred over `actions-rs/toolchain` (archived).
- Avoid caching `target/` on Windows — symlinks behave differently and corrupt the cache.
- `--all-features` can surface feature-flag conflicts; test both `--no-default-features` and `--all-features`.

## Related
- `github-actions-cache-dependencies.md`
- `github-actions-large-runners.md`
