# Visual Regression Pixelmatch Threshold Calibration

Visual regression testing compares a rendered screenshot against a baseline image and
reports a difference. Pixelmatch, the Mapbox-maintained library that powers the comparison
in many toolchains, performs a pixel-by-pixel diff with *perceptual* colour-distance
weighting and an `alpha` threshold that determines whether a given pixel pair counts as
different. Calibration is the choice of that threshold, the baseline image's dimensions
and device pixel ratio, and the tolerance policy for anti-aliasing and sub-pixel
rendering differences across platforms. Get the calibration wrong in the permissive
direction and real regressions pass; get it wrong in the strict direction and every
rendering environment difference is flagged as a regression. The threshold is not a
number to guess — it is a parameter to calibrate against observed differences.

## Scope

Covers the calibration of pixelmatch's comparison parameters in a visual regression test
suite: the `alpha` threshold, image dimensions and device pixel ratio, anti-aliasing
tolerance, baseline management, and the diff-count policy that decides pass or fail.
Applies to any toolchain that uses pixelmatch directly or through a wrapper (Jest Image
Snapshot, Playwright's `toHaveScreenshot`, Percy and its peers use similar concepts).
Does not cover the choice of visual testing tool, nor the design of which components to
snapshot.

## Workflow or implementation guidance

1. **Understand what `alpha` controls.** Pixelmatch's `alpha` option is a number between
   0 and 1 that determines the maximum colour-distance at which two pixels are still
   considered identical. It is applied per-pixel with a perceptual weighting, so a small
   shift in a low-contrast area is more likely to be tolerated than the same shift in a
   high-contrast edge. The default (0.1) tolerates minor rendering differences; raising it
   tolerates more, lowering it tolerates less.
2. **Fix the rendering environment before calibrating.** The threshold cannot compensate
   for a baseline captured at a different device pixel ratio, a different font rendering
   engine, or a different browser version. Capture baselines and run comparisons in the
   same environment: same browser, same version, same viewport, same font set, same
   animation state. Any variation in that list produces diffs that no threshold will
   sensibly absorb.
3. **Calibrate against observed noise, not against intuition.** The method:
   - Capture a baseline.
   - Re-render the same component with no code change, N times, across the environments
     the CI will use.
   - Run pixelmatch at a low threshold and record the diff counts.
   - The observed diff counts *are* the noise floor. Choose a threshold and a diff-count
     tolerance that sits comfortably above the noise floor and below the magnitude of a
     regression you care about.
   A diff count of 40 pixels on a 1200x800 viewport is noise; a diff count of 5000 is a
   real change. The threshold and the max-diff policy should separate those two cases
   with margin.
4. **Use `includeAA` for components where anti-aliasing dominates.** Pixelmatch can
   detect and ignore anti-aliased pixels — the pixels at the edge of a shape whose colour
   is a blend of the shape and its background. Anti-aliasing differs across font
   renderers and GPU drivers even when the design intent is identical. Enable
   `includeAA: false` (the default) to ignore these; enable it explicitly only where the
   anti-aliasing *is* the thing being tested, which is rare.
5. **Set a diff-count policy in addition to the threshold.** Pixelmatch returns the number
   of differing pixels. A pass/fail decision based only on "any pixel differs" is too
   strict for any environment with font-rendering variation; a decision based on "more
   than K pixels differ" is calibratable. Choose K from the noise-floor measurement, not
   from a round number.
6. **Mask regions that are expected to vary.** Timestamps, avatars, rotating carousels,
   animations mid-frame, and third-party widgets produce diffs that are expected.
   Pixelmatch supports a mask image that excludes regions from comparison. Apply the mask
   narrowly — a large mask hides real regressions inside it.
7. **Manage baselines as reviewed artefacts.** A baseline is not "the current screenshot";
   it is a reviewed expectation. Baseline updates go through the same review as code
   changes, with the visual diff visible in the pull request. An auto-updating baseline
   that nobody reviews is a visual test that always passes.
8. **Snapshot at component boundaries, not full pages, where possible.** A full-page
   screenshot has a large pixel area and therefore a large noise floor; a component-level
   screenshot has a smaller one, so the signal-to-noise ratio of the diff-count policy is
   better. Full-page snapshots still have value for layout regressions; use them with a
   proportionally higher diff tolerance.
9. **Pin the viewport and device pixel ratio.** A baseline captured at 2x DPR compared
   against a render at 1x DPR produces massive diffs. Set both explicitly in the test
   configuration and assert that the captured image's dimensions match the baseline's
   before comparing.
10. **Re-calibrate when the rendering environment changes.** A browser upgrade, a new
    font version, or a change of CI runner image shifts the noise floor. Re-measure and
    re-derive the threshold; do not carry the old number forward on the assumption that
    it still separates noise from signal.

A representative comparison with calibrated parameters:

```js
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';

const diff = new PNG({ width: imgA.width, height: imgA.height });
const diffPixels = pixelmatch(imgA.data, imgB.data, diff.data,
  imgA.width, imgA.height,
  { threshold: 0.08, includeAA: false, diffMask: true });

expect(diffPixels).toBeLessThan(NOISE_FLOOR * 2); // calibrated, not guessed
```

## Controls

- The comparison parameters (`threshold`, diff-count policy, masks) are committed in the
  test configuration and reviewed like code.
- Baselines are reviewed artefacts; updates are visible in pull requests with the diff
  image attached.
- The noise floor is measured periodically and the threshold re-derived from it; the
  measurement is recorded with the configuration.
- Viewport, device pixel ratio, browser, and browser version are pinned in the test
  configuration.
- Masks are documented with the reason each masked region is expected to vary.

## Validation evidence

- A deliberate visual change (a padding change, a colour change) produces a diff count
  above the policy threshold and the test fails.
- An environment-only change (a font renderer update) produces a diff count below the
  policy threshold and the test passes; if it does not, the noise floor measurement is
  stale and the threshold is re-calibrated.
- Baseline updates are visible in pull requests; a change that updates a baseline without
  a visible diff image is rejected in review.
- The mask coverage is reviewed; a mask that covers a large proportion of the image is
  flagged.

## Failure modes and correction

- *Every run flags dozens of diffs.* The environment is not fixed: DPR, browser version,
  or fonts differ between baseline capture and comparison. Pin the environment; then
  re-measure the noise floor.
- *Real regressions pass.* The threshold or diff-count policy is too permissive. Lower
  the threshold, lower the diff count, and re-measure; a policy that tolerates a real
  regression is worse than no visual test.
- *Baseline auto-updates silently.* Disable auto-update; require explicit, reviewed
  baseline changes.
- *Mask covers most of the image.* Reduce the mask; if a component cannot be tested
  without masking most of it, the component is not stable enough to snapshot and should
  be refactored or tested at a different boundary.
- *Full-page snapshots dominate the suite.* Move to component-level snapshots where
  possible; keep full-page snapshots for layout with a proportional tolerance.
- *Threshold carried forward across environment changes.* Re-measure the noise floor and
  re-derive the threshold with each rendering-environment change.

## Limitations

- Pixelmatch compares pixels. It has no understanding of layout, semantics, or intent; a
  one-pixel shift of the entire page is a large diff count even though the design intent
  is unchanged, and a colour change in a small area is a small diff count even though
  the design intent changed significantly.
- Perceptual colour distance approximates human perception for the colour pairs the
  weighting was derived from; it does not model all perceptual effects (simultaneous
  contrast, adaptation) and can both over- and under-tolerate.
- The comparison is raster-based. Vector or scaling differences (a different font hinting
  strategy) manifest as distributed small diffs that the threshold may or may not absorb
  consistently.
- Visual regression testing catches what is visible. It does not catch accessibility
  regressions (missing alt text, broken focus order) or behavioural regressions unless
  they manifest visually in the captured state.
- Anti-aliasing detection is heuristic. In pathological cases (gradients, thin lines) it
  can mis-classify design-intended edges as anti-aliasing and ignore them.

## Canonical sources

- Mapbox, *pixelmatch* (repository documenting the `threshold`, `includeAA`, and mask
  options and the perceptual colour-distance algorithm):
  https://github.com/mapbox/pixelmatch
- Playwright, *Best practices* (visual comparison guidance including viewport, DPR, and
  animation-state control that determines the noise floor):
  https://playwright.dev/docs/best-practices
- Playwright, *Page Object Model* (structuring suites so snapshots are captured at stable
  component boundaries): https://playwright.dev/docs/pom
