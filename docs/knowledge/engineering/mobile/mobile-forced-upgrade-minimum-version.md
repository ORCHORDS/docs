# mobile-forced-upgrade-minimum-version

**Issue:** You shipped an API your backend is about to deprecate, a security protocol changed, or a compliance deadline lands next quarter, and the only real fix is getting users onto a new app version. But neither Apple nor Google lets you push an update over an installed app; the binary in the user's hands is immutable, and stores gate every release. The only lever is a server-driven minimum-version gate inside the app itself. Done crudely it blocks a paying user at an airport with no Wi-Fi, triggers App Store review problems, or bricks the app when the gate-check endpoint itself is broken. This article covers designing version gates that enforce when they must and fail open when they should.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Server-driven version gates

1. **Never hardcode the minimum version in the binary.** A gate compiled into version N only helps users you already reached; the versions that need gating are the old ones, whose hardcoded values you cannot change. The minimum must come from a backend endpoint or remote config that old clients already know how to read.
2. **Ship the gate before you need it.** The classic trap is adding version-check code only when the first forced upgrade looms, then discovering the oldest installed versions do not have the check at all and are ungovernable forever. Add a version-check call to every new app from day one.
3. **Return structured policy, not a boolean.** A good payload carries minimum required version, recommended version, per-platform values (iOS and Android deprecate on different schedules), a message string, store URL, and an enforcement type. Encoding only required=true couples policy and copy in ways marketing cannot edit later.
4. **Gate at startup and at auth/checkout boundaries.** A user mid-session when policy changes should finish their task; check the gate at launch and at sensitive boundaries rather than yanking the app out from under active work.

## Soft block versus hard block

1. **Tier the enforcement: nag, then warn, then block.** Start with a dismissible "a new version is available" banner, escalate to a permanent-but-bypassable warning as the deadline nears, and only then make the update mandatory. Most users update during the soft phase and never see the wall.
2. **Make the hard block honest and actionable.** The block screen must say why (security, new terms, old version retired), offer a one-tap deep link straight to the store listing, and offer a "try anyway" degraded read-only mode where the product allows it. Zoom's quarterly lifecycle policy (sign users out below minimum, allow back in after update) is the mature template.
3. **Set the floor by data, not vibes.** Examine the version distribution and revenue/usage per version before picking the minimum. Blocking a version still carrying 8% of sessions is a product decision with a support cost, not an engineering cleanup.
4. **Exempt internal and enterprise builds.** QA, staging, enterprise, and TestFlight builds must bypass production gates via build flavor or entitlement, or you lock out your own testers and field staff on the eve of every release.

## Failure modes and fail-open design

1. **Fail open when the gate endpoint is unreachable.** If the version-check call fails (offline, DNS, 5xx), blocking the user punishes them for your endpoint's outage. Cache the last known policy, let the session proceed when no policy can be fetched, and enforce on the next successful check.
2. **Treat gate infrastructure as critical-path.** The endpoint backing the gate now sits in front of every launch. It needs the same uptime, CDN caching, and monitoring as login; a misconfigured cache serving a stale minimum of 99.0.0 blocks every user at once.
3. **Do not gate inside the auth flow only.** Users with cached sessions skip login for months; a gate that lives in the login response never fires for them. Put the check on a plain version/policy endpoint reachable pre-auth.
4. **Beware kill switches in review builds.** If the gate server returns block during App Store review (because the reviewer hits production with an unreleased version), review can fail for an unusable app. Whitelist review ranges or scope hard blocks to versions older than the one in review.

## Version comparison mechanics

1. **Never compare versions as floats or strings.** 1.10 must be newer than 1.9, and 1.0.0-rc1 vs 1.0.0 must resolve deterministically; parse into integer tuples per component with documented tie-breakers for prerelease/build metadata. One shared comparator implementation, unit-tested to death.
2. **Decide which identifier rules: iOS marketing version or build number.** iOS ships CFBundleShortVersionString (marketing) and CFBundleVersion (build); Android has versionName and versionCode. Pick one per platform as authoritative for gating (usually versionCode/versionCode-equivalent build number, since it is strictly monotonic) and verify it increments on every branch and hotfix.
3. **Pin platform floors independently.** iOS users update fast; Android longtails for years. A single cross-platform minimum either strands iOS users needlessly or leaves Android users on insecure builds; always key policy by platform.

## Operational rollout

1. **Canary the gate itself.** When first turning a hard block on, enable it for 1% of sessions or one market, watch support volume and store update conversion, then expand. A bad gate is an instant outage-shaped event that no app release can quickly fix.
2. **Coordinate with a staggered release.** Raise the store phased-release percentage and the gate floor together, so the forced population can actually get the new version; announcing a floor the store has not fully served strands users between versions.
3. **Instrument the funnel.** Log gate checks, block impressions, store deep-link taps, and returning-on-new-version events. The number that matters is not "users blocked" but "blocked users who updated within 7 days"; if that conversion is poor, soften the gate and fix the store page instead.
