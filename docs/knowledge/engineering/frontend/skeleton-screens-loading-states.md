# skeleton-screens-loading-states

**Issue:** Every async UI needs a loading state, and teams reach for skeleton screens by default believing they universally improve perceived performance. The research is more nuanced: some studies found skeletons perceived as slower than blank screens or spinners, others found them faster only for short loads (under roughly three seconds), and NN/g recommends skeletons for full-page loads but explicitly not for individual components. Skeletons also carry real engineering obligations that spinners do not: they must match final layout to avoid CLS, they are invisible to screen readers unless deliberately annotated (Adrian Roselli's "More Accessible Skeletons" documents how badly most implementations fail), and Google's LCP documentation notes skeleton placeholders are typically not counted as LCP candidates — a skeleton does not buy back Core Web Vitals, only perceived continuity. Choosing and building loading states deliberately, rather than by default, is the engineering discipline here.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the Loading Pattern

1. **Match pattern to wait duration and determinism.** Spinners suit indeterminate, short waits and individual components; progress bars suit determinable multi-step waits; skeletons suit page-level loads where final layout is known in advance. The NN/g guidance (skeletons for full-page loads, not components) and the onething.design comparison both frame it as uncertainty management: spinners create open-ended waiting anxiety, skeletons promise eventual structure.

2. **Do not use skeletons above roughly three seconds.** Perceived-performance research (summarized in the UX Design.cc deep dive and the r/userexperience discussion of skeleton studies) shows skeletons help when loads are short and hurt when long — showing a promising structure that then sits static for ten seconds reads as broken. Past the three-second mark, switch to a progress indicator or an explicit empty/loading state with content.

3. **Prefer real content chunks when possible.** Streaming SSR, Suspense boundaries, and partial data let you render actual headers, navigation, and first sections immediately with skeletons only for the genuinely pending region. A page that is 70 percent real content and 30 percent skeleton outperforms a 100 percent skeleton in both perception and LCP, because rendered text is content.

4. **Standardize one loading vocabulary across the app.** Define in the design system which components have skeleton variants, which use inline spinners, and which use nothing (synchronous local state). Ad-hoc per-feature choices produce the same page showing three different loading idioms, which itself reads as slowness.

## Designing Skeletons That Help

1. **Mirror the final layout exactly.** A skeleton whose block sizes, spacing, and aspect ratios differ from loaded content causes layout shift (CLS) at swap-in and a visible "snap." Skeleton components should accept or derive dimensions from the real component — ideally the skeleton is the real component with placeholder content, guaranteeing parity by construction.

2. **Reserve media dimensions in the skeleton.** Images, avatars, and embeds need fixed aspect-ratio blocks in the skeleton (with width/height or aspect-ratio set) so the swap does not reflow. This is also standard CLS practice from the web vitals guidance and doubles as skeleton correctness.

3. **Keep the pulse subtle and slow.** A 1.5-2 second ease-in-out opacity pulse (shimmer between two close grays) is the accessible standard; fast shimmers and high-contrast gradient sweeps read as aggressive. The pulse should communicate liveness without demanding attention.

4. **Do not fake granularity you do not have.** If you have no idea what the content shape is (search results, arbitrary API payloads), a generic skeleton lies to the user. In those cases a labeled loading state ("Loading results...") is more honest and less jarring at swap-in than a guessed layout that completely reshuffles.

## Accessibility Semantics

1. **Annotate with aria-busy on the right element.** Roselli's critique: implementations routinely dump aria-busy on a wrapper that assistive tech ignores, or on the whole page. Put aria-busy="true" on the container whose content is being replaced, and remove it when content arrives; combine with aria-live="polite" announcing completion ("Results loaded") so screen reader users know the wait ended.

2. **Hide the placeholder shapes themselves.** Decorative skeleton bars convey nothing non-visually: mark the skeleton sub-tree aria-hidden="true" and provide the semantic container (heading, list, region roles) regardless of state. A skeleton must never be the only representation of structure.

3. **Honor prefers-reduced-motion.** The pulse/shimmer is motion; under prefers-reduced-motion, render static gray blocks (the r/accessibility discussion of loading indicators and vestibular triggers applies to skeleton shimmer too). Also offer a static text alternative where the animated bar would loop indefinitely.

4. **Never skeleton-block navigation semantics.** While loading, keep the page title, headings, and skip links real; do not replace the entire document with an unannotated gray layout. Screen reader users navigating by landmarks must still find them.

## Interaction with Core Web Vitals

1. **Skeletons do not count as LCP.** Google's LCP documentation is explicit that placeholder-like paints are typically not LCP candidates; the largest content element is measured when real content paints. A skeleton strategy masks waiting visually but does not improve LCP — only faster responses and optimized resources do. Report both perceived continuity and field LCP when evaluating the work.

2. **Watch CLS at skeleton-to-content swap.** All the layout-parity rules above exist because the swap is a classic CLS event, especially for client-rendered lists where row heights are estimated. Validate with lab tools and real-device traces on the slowest supported phone, not desktop.

3. **Do not delay content for skeleton aesthetics.** A bug pattern: gating the first paint of real data behind a minimum skeleton display time (to "avoid flicker") adds artificial latency to fast connections and inflates both LCP and user-perceived wait. If data arrives before the skeleton would paint, skip the skeleton entirely — a sub-100 ms flash of skeleton is itself a defect.

## Progressive and Streaming States

1. **Design the four-state model per data region.** Loading (skeleton), Loaded (content), Empty (no results, with guidance), and Error (retry affordance) are four distinct renderings of the same boundary. Most skeleton bugs are actually missing empty/error states falling through to eternal skeletons — a skeleton with no timeout is indistinguishable from a hang.

2. **Set a timeout and a retry path.** After a threshold (typically 10-15 seconds), transition the skeleton to an explicit error state with a retry action; an animated skeleton that runs forever trains users to leave. Wire this into the same state machine as the query library's error handling so network failures and timeouts look consistent.

3. **Coordinate parallel loads into one layout.** When several regions load at different speeds, each with its own skeleton, the page assembles piecemeal and shifts repeatedly. Prefer coordinating the shell (render all skeletons together) and letting regions fill in, with stable region sizes guaranteed by the parity rules above.
