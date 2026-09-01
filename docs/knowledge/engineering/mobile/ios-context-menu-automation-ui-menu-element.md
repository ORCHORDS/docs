# UIContextMenuInteraction and Context Menu Automation

`UIContextMenuInteraction` gives iOS apps the press-and-hold preview-and-menu system — the translucent blur, the preview of the target content, and the floating menu of actions. It replaced the older `peek`/`pop` 3D Touch APIs with a unified interaction model accessible on every device. Building the interaction is half the work; the other half is that context menus are stateful, animation-coupled UI whose configuration blocks run at presentation time — which makes automated testing of menu items nontrivial, and Xcode 16's explicit support for menu-element automation (querying menu items, tapping them, verifying dismissal) finally closed the tooling gap. This article covers implementing `UIContextMenuInteraction` correctly and automating context menus in UI tests.

## Scope

This article addresses `UIContextMenuInteraction` on iOS: the delegate contract (`contextMenuInteraction(_:configurationForMenuAtLocation:)` returning a `UIContextMenuConfiguration`), preview providers and `UITargetedPreview`, `UIContextMenuDelegate` will-present/end handlers, commit (tap-through to content) behavior, and automation via XCUITest with Xcode 16's `menuItems` queries and related accessibility integration. It covers implementation and test automation. It does not cover `UIMenu` construction broadly (menu syntax in menus/toolbars), iPad pointer interactions, or SwiftUI `contextMenu` beyond mapping notes.

## Workflow or implementation guidance

The interaction object is attached once per target view:

```swift
let interaction = UIContextMenuInteraction(delegate: self)
view.addInteraction(interaction)
```

The delegate's configuration method runs when the system needs to present:

```swift
func contextMenuInteraction(_ interaction: UIContextMenuInteraction,
        configurationForMenuAtLocation location: CGPoint) -> UIContextMenuConfiguration? {
    return UIContextMenuConfiguration(identifier: nil) {
        // previewProvider: UIViewController for the elevated preview
        return PreviewViewController(item: self.item)
    } actionProvider: { suggested in
        // UIMenu built at presentation time
        return UIMenu(children: [
            UIAction(title: "Rename…", image: UIImage(systemName: "pencil")) { _ in self.rename(self.item) },
            UIAction(title: "Share…", image: UIImage(systemName: "square.and.arrow.up")) { _ in self.share(self.item) },
            UIAction(title: "Delete", attributes: .destructive, image: UIImage(systemName: "trash")) { _ in self.delete(self.item) }
        ])
    }
}
```

Implementation details that separate working menus from flaky ones:

1. **Configuration runs at presentation time.** The action provider closure executes when the menu shows, so it must capture the item *at that moment*. In a collection view where cells are reused, capturing `self.item` from a reused cell presents the menu for the wrong item — the canonical bug. Resolve identity from the interaction's view (`interaction.view` → model lookup via index path) or register interactions per-configuration with captured identifiers, and re-look-up the model inside the closure by ID rather than by reference.
2. **Preview and targeted preview.** The `previewProvider` returns a view controller rendered elevated; `UITargetedPreview` (via the presentation delegate's `contextMenuInteraction(_:previewForHighlightingMenuWithConfiguration:)`) offers precise alignment of the highlighted region with the source view — use it when the menu target is a subregion of a cell (a thumbnail inside a card) so the lift animation doesn't clip. Misaligned previews read as jank even when functionally correct.
3. **Commit behavior.** Tapping the preview (not a menu item) dismisses and "commits" — call your navigation in `contextMenuInteraction(_:willPerformPreviewActionForMenuWith:animator)` by adding to the provided animator's registration. Without it, tapping the preview does nothing and users perceive the menu as broken.
4. **Update/invalidate flows.** If the item's state changes while a menu could present (selection, edit mode), the stale action provider builds from stale state; keep providers lightweight and state-derived so the next presentation is correct, and call `invalidateMenu()` (on the interaction, when supported) after model mutations that change actions.
5. **SwiftUI mapping.** SwiftUI's `.contextMenu { }` modifier wraps this machinery; identity pitfalls mostly vanish but preview customization and animation control are more limited — the UIKit path remains the escape hatch for precise behavior.

**Automation.** Context menus historically resisted UI testing: they render in a separate context-menu presentation layer, and taps that trigger them are long-presses. Xcode 16 added first-class support — context menu items appear in the element tree as `menuItems`, queryable and tappable directly:

```swift
func testItemContextMenuActions() {
    let cell = app.collectionViews.cells["Report 42"]
    cell.press(forDuration: 1.0)
    let rename = app.menuItems["Rename…"]
    XCTAssertTrue(rename.waitForExistence(timeout: 2))
    app.menuItems["Delete"].tap()
    XCTAssertTrue(app.alerts["Confirm deletion"].waitForExistence(timeout: 2))
}
```

Automation discipline:

1. **Trigger via long-press on the source element** (`press(forDuration:)`), then query `menuItems` by title; the menu layer's elements are not descendants of your view hierarchy, so query the app-level `menuItems` collection rather than `cell.menuItems`.
2. **Assert full action sets, not just one item.** The state-capture bug (wrong item's actions) manifests as *wrong titles* in the menu: assert the exact expected titles for a known item, catching identity regressions that single-item taps miss.
3. **Test the commit path too** — tap the preview region and assert navigation fired; this is the interaction most often forgotten in manual testing as well.
4. **Accessibility underpins automation.** Menu items expose titles from `UIAction.title`; dynamic titles (counts, names) should stay deterministic in tests (seed data with stable names) — `format:verbatim`-style localized assertions depend on consistent titles.
5. **Timing.** Menus animate in; `waitForExistence` on the item before tapping avoids flaky early taps. Dismissal (tap elsewhere) needs an assert that `menuItems` go away before continuing.

A worked example: a document list where each cell offers Rename/Share/Delete, with delete confirmed by an alert. The regression that motivated automation: after a cell-reuse refactor, long-pressing the third document showed the *first* document's actions (identity captured at interaction creation). The test above — assert exact titles for a seeded distinct item — caught it in CI on the refactor PR, before release. The test suite now covers: long-press → exact action set, destructive flow through confirmation, commit-on-preview-tap navigation, and dismissal state.

## Controls

- Every context-menu surface ships with a UI test asserting (a) exact action titles for a seeded item, (b) each action's effect on state, (c) the commit path, (d) dismissal — the four-assertion pattern catches identity, action-wiring, commit, and dismissal regressions.
- Identity derivation rule (interaction.view → model lookup by ID inside the action provider) is code-reviewed; direct capture of mutable cell state in providers is rejected.
- Destructive actions must route through confirmation UI, and their tests assert both the confirmation and the cancel path.
- Menu titles participate in localization: tests run against the development language with seeded stable data; localized-title runs (one smoke suite) verify key screens' menus localize without breaking automation contracts.
- Xcode version pins: menu-item automation support arrived in Xcode 16 — CI images pinned at/above it; UI test suites gate on availability so older toolchains skip menu tests loudly rather than silently.

## Validation evidence

- The `UIContextMenuInteraction` delegate contract, `UIContextMenuConfiguration` preview/action providers, `UITargetedPreview` alignment, commitAnimator registration, and `UIMenu`/`UIAction` construction are specified in Apple's UIKit documentation (UIContextMenuInteraction and related reference pages) on developer.apple.com.
- XCUITest context-menu automation (`menuItems` element queries, long-press triggering) is documented in Apple's XCUITest framework reference and Xcode 16 release notes describing menu-element query support.
- A reproducible validation: the four-assertion suite above run against a deliberately broken build (identity captured at interaction creation) fails the exact-titles assertion — demonstrating the test detects the canonical implementation bug before shipping.

## Failure modes and correction

- **Wrong item's menu after cell reuse.** Symptom: actions apply to a different model object. Correct by ID-based lookups inside providers; guard with the exact-titles test.
- **Dead preview tap.** Symptom: tapping preview dismisses without navigating. Correct by implementing the commit animator path.
- **Stale actions after state change.** Symptom: menu shows actions invalid for current mode. Correct by state-derived providers and menu invalidation on mutation.
- **Flaky automation taps.** Symptom: tests tap before menu presents. Correct by wait-for-existence on menuItems before interaction.
- **Automation blind spot on older toolchains.** Symptom: menu tests silently absent from CI. Correct by availability-gated loud skips and pinned CI images.

## Limitations

- Menu presentation lives in a system-managed layer; fine-grained layout assertions inside the menu (beyond titles/existence) are not reliably automatable.
- Long-press timing varies by device/pointer; automation uses conservative durations and waits.
- SwiftUI `contextMenu` covers common cases but defers to UIKit for preview alignment and animation control.
- Localized-title assertions require stable seeded data; systems with server-driven menu titles need test doubles for determinism.

## Canonical sources

- Apple, UIContextMenuInteraction — UIKit documentation (delegate, configuration, previews, commit): https://developer.apple.com/documentation/uikit/uicontextmenuinteraction
- Apple, XCUITest framework reference and Xcode 16 release notes (menu item automation support): https://developer.apple.com/documentation/xctest
