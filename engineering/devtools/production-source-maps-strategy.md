# production-source-maps-strategy

**Issue:** A production frontend crash reports a stack trace pointing at `main.9f3ab2c.js:2:84731` — useless without maps, a full source-code disclosure with them. Teams flip between shipping `.map` files publicly (every error readable, entire original source downloadable by anyone), hiding them, and deleting them. The 2025 consensus: treat client-side code as public, keep secrets out of it entirely, and control map distribution deliberately instead of accidentally.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The threat model

1. **A public `.map` file restores your entire original source.** Sourcemaps embed the pre-minification sources: real variable names, comments, file structure, and internal package layout. Anyone who guesses `app.js.map` can run a deobfuscator (Sentry's own tooling demonstrates this class of "abusing exposed sourcemaps") and read the app like an open repo.
2. **What actually leaks is content, not the map itself.** Security reviewers generally treat the existence of public maps on a static host (GitHub Pages serves them by design) as low severity by itself — the vulnerability class is what the source contains: hardcoded internal endpoints, auth/entitlement logic, proprietary algorithms, and comments with internal hostnames or tokens.
3. **Minification is not protection; it is compression.** Teams regularly mistake minified JS for obfuscation. Any secret that reaches the bundle — an API key inlined from an env var, a token in a comment, a `.env` value accidentally imported — survives minification and is highlighted, named, and documented in the sourcemap.
4. **Automated scanners now flag this.** Bug-bounty platforms and app scanners increasingly report exposed sourcemaps as an information-disclosure finding, and leaks of internal endpoints via maps have shown up in real reports. Even if you accept the risk, expect the finding to keep arriving until it is a documented decision.
5. **Your real secrets policy is the fix, not the maps policy.** No client-side key is ever safe — obfuscated or not. Maps only change how convenient the reading is. Anything sensitive belongs behind a server route, and CI secret scanning (gitleaks etc.) should run over what ships, not just the repo.

## The four deployment strategies

1. **No maps at all (`sourcemap: false`).** Maximum security, minimum debuggability: every production trace stays minified forever. Only defensible when you have no error-monitoring investment or the bundle is genuinely trivial.
2. **Public maps (default behavior of some hosts and older scaffolds).** Best developer convenience — the browser DevTools console shows original code for every user — and total disclosure. Accept it as a conscious, documented choice for open-source apps; never let it be the fallback you forgot to turn off.
3. **Hidden maps.** Build external `.map` files but omit the `//# sourceMappingURL=` trailer (Vite/Rollup `sourcemap: 'hidden'`, webpack `hidden-source-map`). Your error tracker fetches maps by convention, while casual visitors see no pointer. Know the limit: hidden is obscurity, not access control — an attacker can still request `main.9f3ab2c.js.map` directly if it is deployed and guessable.
4. **Upload-only (the 2025 default).** Generate maps in CI, upload them to your monitoring platform (Sentry, GlitchTip, etc.), then delete them from the deploy artifact so they are never publicly served. You get symbolicated traces in the error tracker and nothing on the CDN. This is the recommended default posture for most commercial apps.

## Hardening whatever you choose

1. **Make map exposure a CI gate, not a hope.** After deploy, `curl -sI https://app.example.com/assets/main.*.js.map` must 403/404. Wire it into a smoke test so a bundler upgrade or host default change cannot silently flip maps to public.
2. **Adopt Debug IDs for map matching.** Modern Sentry-era tooling injects a Debug ID into both bundle and map so the platform matches them without `sourceMappingURL` or release-name gymnastics — more robust than filename conventions, and it works with hidden maps.
3. **Scan the shipped artifact, not the repo.** Secrets policies fail at the bundler: an env var referenced in code gets inlined at build time. Run secret detection over `dist/` (or the map `sourcesContent`) before the upload/delete step of your pipeline.
4. **Strip the trailer when you delete is hard.** If organizational constraints leave maps on the server (a legacy shared host you cannot clean), at minimum build with hidden mode so nothing advertises the URL, and add host-level deny rules for `*.map`.
5. **Remember non-JS maps.** CSS sourcemaps (and some transpiled-to-WASM setups) follow the same rules; a `styles.css.map` rarely leaks logic but does leak file paths and naming, and it appears in the same directory scans.

## Operational gotchas

1. **Release tagging must match exactly.** If you upload maps per-release (rather than Debug IDs), the release string on the error event and the uploaded artifact must be identical — a one-character mismatch means Sentry silently cannot symbolicate and nobody notices for weeks. Check the event's "Source Map Status" after the first deploy of a new pipeline.
2. **Verify in both directions.** Symbolication should be confirmed with a real production error (or a forced one in a canary release), and absence confirmed with a directory listing of the deployed assets — half-verified pipelines are how both leaks and useless maps persist.
3. **Delete maps from every layer, not just the output dir.** CI caches, Docker image layers, and the error-tracker upload staging folder all keep copies; a map "deleted from dist" that lives in a published container image is still a disclosure.
4. **Keep the decision in one place.** Record the chosen strategy (and its rationale) next to the build config — the setting lives in three tools (bundler config, upload script, deploy cleanup) and drifts when each is edited independently.
5. **Server-side errors are a different problem.** This whole strategy is about client bundles; backend stack traces are already original source and are governed by your API error-response hygiene, not by sourcemaps.

## Related

- sentry-error-monitoring-setup (the upload + release workflow side)
- gitleaks / secret scanning (run over shipped artifacts)
