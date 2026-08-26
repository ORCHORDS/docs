# merged-is-not-deployed-bundle-verification

**Issue:** CI says green, the PR is merged, and the team moves on — but the change never reached production (broken deploy, stale bundle, dead route). Users report the old behavior days later. The gap between "merged on GitHub" and "live on the domain" is where changes silently die. Happened multiple times on example project (example-org/example-repo): the admin API sat dead for six days after its merge.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The verification that actually proves "live"

1. **Fetch the deployed asset and grep it.** Pull the live JS bundle/HTML from the production domain and search for a string unique to the change (a new error message, a renamed function, a config literal). Seeing the marker in the shipped bytes is proof; the merge commit is not.
2. **Probe the behavioral endpoint** — trigger the changed path and observe the new response shape/status, not just a 200.
3. **Check the deploy event ties to YOUR merge** — the deploy timestamp/version must postdate the merge SHA; a green check on an older deploy is theater.
4. **Bypass caches once** — cache-busting query param or CDN purge — stale CDN layers make old bundles look immortally current.
5. **Record the probe result** in the PR or master-issue comment ("live check: marker `X` present in bundle at 12:04 UTC") — it converts "should be deployed" into evidence.

## Where changes die between merge and live

1. **Deploy job skipped or failed silently** (path filters, matrix misses, a workflow that no longer triggers on the changed path).
2. **Build cache reuse** — the deploy "succeeded" from a cached artifact predating the change.
3. **Routing gaps** — code deployed to a Worker/Pages project nothing routes to (see the 404 diagnosis article).
4. **Partial rollouts** — one region/coloc updated, another stale; a single-region probe can lie.
5. **Config drift** — the code is live but an env/flag it reads is unset in production, so the new path never executes.

## Making it systematic

1. **A "verify live" step in every shipper's Definition of Done** — same weight as tests passing.
2. **Unique markers per change** — a distinctive string (not reused identifiers) makes the grep unambiguous.
3. **Automate the probe** where possible: post-deploy smoke test hitting the public domain and asserting the new behavior.
4. **Watch for the negative proof too** — the OLD marker absent from the live bundle is as informative as the new one present.
5. **Timebox trust:** if you can't verify live within N minutes of merge, assume it's not deployed and investigate the pipeline — do not assume the platform will catch up.

## Related

- `../cloudflare/pages-404-worker-split-diagnosis.md`
- `../frontend/build-time-env-baking-chunk-hash.md`
