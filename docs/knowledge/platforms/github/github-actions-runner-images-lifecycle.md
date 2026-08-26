# github-actions-runner-images-lifecycle

**Issue:** GitHub-hosted runners run a rolling set of images (`ubuntu-latest`, `ubuntu-24.04`, `macos-15`, `windows-2022`…) that have a lifecycle: new images roll out, `latest` aliases migrate, old images are deprecated and then removed on published dates. Workflows pinned to an image past its end-of-life start failing overnight — the ubuntu-20.04 retirement (deprecated February 2025, gone April 2025) and the published ubuntu-22.04 schedule (deprecation beginning September 17, 2026; fully unsupported April 17, 2027) both broke pipelines that had not been touched for months. Treating runner images as infrastructure with EOL dates — pinning deliberately, migrating early, and monitoring deprecation announcements — is an operational discipline every CI-owning team needs.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Lifecycle and Labels

1. **Image lifecycle stages.** A new image (e.g., ubuntu-24.04) rolls out first as an explicit label, then becomes the `ubuntu-latest` default in a staged migration, and years later enters deprecation (brownouts where jobs may fail) before being fully removed. GitHub publishes each deprecation as an `announcement` issue in the actions/runner-images repository with exact dates; those issues are the authoritative calendar.
2. **`latest` is a moving target.** `ubuntu-latest` silently migrated from 22.04 to 24.04; the "silent" part is the risk — behavior changes (newer compilers, changed preinstalled tool versions, Python/Node defaults) arrive without any workflow edit. Track the runner-images releases page or pin when reproducibility matters more than freshness.
3. **Versioned labels exist but are fragile.** Labels like `ubuntu-24.04` track the rolling image; true image-version pinning (e.g., `ubuntu-24.04-313`) is possible but the community guidance and the runner-images maintainers discourage treating pin numbers as supported API — they exist for debugging and short-term reproducibility, not as a stable floor.
4. **Deprecation cadence tracks the OS.** Ubuntu images retire roughly with the LTS lifecycle (22.04 standard support to 2027); macOS images move faster with annual major versions (macos-14 → macos-15 transitions), so macOS pipelines churn more often.
5. **Third-party trackers help.** endoflife.date's GitHub Actions runner-images page consolidates EOL dates per image — convenient for dashboards, but verify against the runner-images announcement issue before scheduling migrations.

## Migration Playbook (ubuntu-22.04 → 24.04)

1. **Inventory usage.** Grep all workflows for `runs-on:` values (`gh api` or plain ripgrep over `.github/workflows/` and reusable-workflow repos); the goal is a list of repos and jobs pinned to the dying label versus `latest` (already migrated or silently about to).
2. **Create a dual-run canary.** Run the same workflow on the new image in a matrix (`runs-on: [ubuntu-22.04, ubuntu-24.04]`) before switching; failures surface toolchain deltas (default Python, missing apt packages, glibc-sensitive binaries) while the old lane still blocks regressions.
3. **Fix environment assumptions.** Common 22.04→24.04 breaks: removed/renamed apt packages, newer default interpreters needing explicit setup-action versions, and Docker-in-Docker or systemd behavior differences. Move every implicit dependency to a setup action or container job so image swaps stop mattering.
4. **Switch and watch.** Replace explicit labels (or adopt `ubuntu-24.04` deliberately instead of `latest`), then watch the next scheduled runs plus `dumpsys`-style health checks: cache-hit rates drop after image changes because cache keys including OS/tool versions invalidate — expect a temporary CI-time bump.
5. **Schedule against the calendar.** With 22.04 deprecation starting 2026-09-17, freeze new 22.04 usage immediately and complete migration before the first brownout window; put the April 17, 2027 removal date in the team calendar as the hard deadline.

## Pinning Policy

1. **Default to `latest` for leaf repos.** Small projects with green tests gain more from automatic migrations than they lose from surprise churn — provided tests actually catch environment breakage.
2. **Pin the major label for release infrastructure.** Release, deploy, and security-critical workflows pin `ubuntu-24.04` explicitly and migrate on the team's schedule, not GitHub's — paired with the SHA-pinning policy for actions already documented in `actions-policy-sha-pinning-and-blocklists-2026.md`.
3. **Never rely on preinstalled tool versions.** Preinstalled software lists change without notice between image rebuilds; always `setup-node`/`setup-python`/`setup-go` with explicit versions (or use containers) so image lifecycle events cannot change your toolchain.
4. **Document per-runner expectations.** Record required disk space (14GB free on standard runners), CPU count, and image-specific packages in the workflow README so a future migration knows what to re-verify.
5. **Watch the announcements feed.** Subscribe to the runner-images repository's announcement issues (or pipe them to Slack via the notification patterns in `github-actions-notify-slack.md`); every retirement is telegraphed months in advance there.

## Pitfalls

1. **Brownout confusion.** During deprecation windows jobs intermittently fail with no workflow change, which looks like flaky infrastructure; check the runner image name in the job's "Set up job" step against the announcement issue before debugging your code.
2. **`latest` pinning theater.** Teams "pin" by writing `ubuntu-latest` believing it is stable; it migrates underneath them. Pinning means an explicit version label.
3. **macOS lag lock-in.** macOS arm64/x64 label splits (macos-14 versus macos-15) change pricing and availability; cross-compile instead of queuing jobs on a retiring image class when the new one has no arm64 equivalent yet.
4. **Cache invalidation cliffs.** Any image migration invalidates caches keyed on tool versions; budget for slower first runs and communicate it, or the migration "causes" a phantom performance regression.
5. **Self-hosted drift.** Self-hosted runners (see `self-hosted-runners-dual-instance.md`) do not auto-retire, so fleets accumulate ancient environments; apply the same lifecycle calendar to your own runner images for parity.
