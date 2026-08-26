# ARIA Live Regions — Mobile Screen Reader Behavior

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

`aria-live="assertive"` toasts are silent on Android Chrome.
New posts appended by an infinite-scroll feed are never spoken
by TalkBack. A modal opens and VoiceOver focus stays behind the
backdrop. Reduced-motion animations fire on iOS even though the
user has enabled "Reduce Motion" in system settings.

## Context

VoiceOver (iOS/iPadOS) and TalkBack (Android) implement the ARIA
live region specification differently from desktop screen readers
(JAWS, NVDA). An anonymous social platform with dynamic feeds,
modals, and real-time notifications must handle these gaps to
satisfy WCAG 2.1 AA (SC 1.3.1, 4.1.3) and EN 301 549. Testing
on physical hardware is mandatory; emulators do not reproduce
gesture timing or audio feedback accurately.

## 1. Polite vs. Assertive — Platform Differences

| Attribute / Role        | VoiceOver iOS 17+      | TalkBack 16 / Chrome 143  |
|-------------------------|------------------------|---------------------------|
| `aria-live="polite"`    | Queues; next pause     | Queues; next pause        |
| `aria-live="assertive"` | Interrupts; no re-read | Treated as polite         |
| `role="alert"`          | Interrupts; no prefix  | Polite; usually announced |
| `role="status"`         | Queues politely        | Often silent (DOM-inject) |

TalkBack 16 (Android 16 + Chrome 143, 2025+) removed the
polite/assertive distinction for web content — assertive does NOT
interrupt ongoing speech; it is silently queued.

VoiceOver changed in iOS 17: assertive interrupts once but no
longer goes back to re-read the interrupted content (earlier
versions did re-read). Neither platform prepends "alert" — design
copy must be self-explanatory without that word.

Keep live region nodes in server-rendered HTML, empty on load.
Injecting `<div role="status">…</div>` dynamically from JS is
the single most common cause of silent TalkBack announcements.

## 2. Dropped Announcements During Scroll

Mobile accessibility frameworks pause live region processing while
a touch-scroll is in progress. If JS appends content while the
browser is mid-momentum-scroll (e.g. IntersectionObserver firing
mid-swipe), the announcement is dropped or coalesced to silence.

- VoiceOver: rapid successive mutations may be batched into one.
- TalkBack: scroll-concurrent mutations almost always drop; off-
  screen live regions are also ignored.

```js
// Double-rAF separates DOM mutation from paint cycle
function announce(msg) {
  statusEl.textContent = '';
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { statusEl.textContent = msg; });
  });
}
```

Never place `aria-live` directly on the scroll container. Keep a
separate, always-visible (off-screen via `clip` or `sr-only`)
status node and write only to that.

## 3. Swipe Navigation vs. Keyboard Navigation

Desktop screen readers rely on Tab/arrow keys. Mobile uses touch
gestures, which changes which ARIA patterns are most important.

| Intent               | JAWS / NVDA   | VoiceOver iOS    | TalkBack Android   |
|----------------------|---------------|------------------|--------------------|
| Next element         | Tab           | Swipe right      | Swipe right        |
| Previous element     | Shift+Tab     | Swipe left       | Swipe left         |
| Activate             | Enter / Space | Double-tap       | Double-tap         |
| Scroll container     | Arrow keys    | 3-finger swipe   | 2-finger swipe     |
| Jump to headings     | H key         | Rotor → Headings | Local context menu |

Swipe order follows DOM order, not CSS visual order. `display:flex`
+ CSS `order` reorders visually but NOT for screen reader swipe.
`opacity:0` alone does not hide from swipe — add `aria-hidden="true"`
on decorative elements. Skip-nav links remain important for
external Bluetooth keyboards paired with mobile devices.

## 4. Infinite Scroll and Dynamic Content

TalkBack does not reliably announce DOM nodes appended to an off-
screen scrollable list even inside an `aria-live` container. Use
the WAI-ARIA `feed` role and announce load completion via a
separate external status node, not from inside the feed:

```html
<div role="feed" aria-busy="false" aria-label="Posts">
  <article aria-posinset="1" aria-setsize="-1">…</article>
</div>
<!-- Status node outside the feed, present in server HTML -->
<div id="sr-status" role="status" aria-live="polite"
     aria-atomic="true"></div>
```

```js
feedEl.setAttribute('aria-busy', 'true');
const added = await loadMorePosts();
appendToDom(added);
feedEl.setAttribute('aria-busy', 'false');
announce(`Loaded ${added.length} new posts.`);
```

`aria-setsize="-1"` signals unknown total length (correct for
infinite scroll). `aria-posinset` must increment across pages;
missing it causes TalkBack to announce "1 of 1" on every item.

## 5. Focus Management — Modal Open/Close

Without explicit management, VoiceOver focus stays on the trigger
and TalkBack may reach content behind the modal backdrop by swipe.

```js
function openModal(triggerEl, modalEl) {
  document.getElementById('app-root').inert = true; // block bg
  modalEl.removeAttribute('hidden');
  modalEl.setAttribute('aria-modal', 'true');
  requestAnimationFrame(() => {
    modalEl.querySelector('button,[href],input').focus();
  });
}
function closeModal(triggerEl, modalEl) {
  document.getElementById('app-root').inert = false;
  modalEl.setAttribute('hidden', '');
  triggerEl.focus(); // restore prior focus position
}
```

`inert` is supported from iOS Safari 15.5+ and Chrome Android 102+.
VoiceOver sometimes requires a second rAF before announcing the
newly focused element — test on device, not in Simulator.

## 6. prefers-reduced-motion on Mobile

iOS "Reduce Motion" (Settings → Accessibility → Motion) and
Android "Remove Animations" (Settings → Accessibility) both
surface as `prefers-reduced-motion: reduce` in CSS. Android does
not suppress web animations at the OS level — CSS must do it:

```css
@media (prefers-reduced-motion: reduce) {
  .feed-item { animation: none; transition: none; }
  html        { scroll-behavior: auto; }
}
```

WCAG 2.1 SC 2.3.3 (AAA) requires honouring this preference for
motion triggered by user interaction. Infinite-scroll entrance
animations and skeleton-shimmer pulses are the most common
violators on social feeds.

## Anti-patterns

- **Assertive for non-critical messages** — silently queued on
  TalkBack 16; causes speech fatigue on desktop.
- **New live region node per update** — destroys the AT
  registration; keep one persistent node, update `textContent`.
- **Writing to a live region before DOMContentLoaded** — the
  accessibility API has not registered it; first write is dropped.
- **`aria-live` on the scroll container** — mutations during
  scroll drop announcements; use an off-screen status node.
- **`opacity:0` as the sole hide mechanism** — element stays in
  the swipe navigation order and is read aloud.
- **No `inert` on modal background** — TalkBack reaches backdrop
  elements via swipe even when they are visually hidden.

## Gotchas

- VoiceOver drops updates identical to the previous live region
  text — always set `textContent = ''` before the new message.
- `aria-atomic="true"` re-reads the whole region on any change;
  fine for short status strings, disruptive on long containers.
- The `feed` role requires `role="article"` children with both
  `aria-posinset` and `aria-setsize`; missing either causes
  TalkBack to announce "1 of 1" on every item.
- `aria-live` on a `display:none` element fires no announcement;
  unhide the node before writing text to it.
- External Bluetooth keyboards put VoiceOver and TalkBack into
  keyboard navigation mode — test Tab order with one connected.

## Verification

1. VoiceOver (device): Settings → Accessibility → VoiceOver.
   Swipe through feed; after load confirm status announcement.
2. TalkBack (device): Settings → Accessibility → TalkBack.
   Trigger load; confirm "Loaded N new posts" is spoken and
   `aria-posinset` increments correctly per article.
3. Open modal; confirm focus lands on first interactive element;
   background content must be unreachable by swipe.
4. Close modal; confirm focus returns to the trigger element.
5. Enable Reduce Motion / Remove Animations; confirm CSS
   transitions and scroll animations are suppressed.
6. axe-core 4.9+ in mobile browser:
   `axe.run().then(r => console.table(r.violations))`

## Related

- `documentation/docs/policies/mobile/mobile-accessibility-a11y.md`
- `documentation/docs/policies/mobile/react-native-accessibility.md`
- `documentation/docs/policies/mobile/android-accessibility.md`
- `documentation/docs/policies/frontend/html-accessibility-aria.md`
- `documentation/docs/policies/frontend/inert-attribute-accessibility.md`

## Source URLs (verified 2026-08-17)

- https://adrianroselli.com/2026/01/live-region-support.html
- https://tetralogical.com/blog/2024/05/01/why-are-my-live-regions-not-working/
- https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions
- https://a11ysupport.io/tech/aria/aria-live_attribute
- https://auditsu.com/resources/voiceover-vs-talkback
- https://www.w3.org/TR/wai-aria-practices-1.2/examples/feed/feed.html
- https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
- https://testparty.ai/blog/mobile-accessibility-patterns
