# Page Object Model Selector Stability Playwright

A page object model encapsulates a page's structure behind a stable API; the test code
calls methods on the page object rather than reaching into the DOM. The model only earns
its keep when the page object outlives the page's current implementation. A page object
built on brittle selectors — class names that change with every redesign, attribute
selectors that depend on framework internals, xpaths that depend on DOM order — is a
page object that has to be rewritten with every UI change. Playwright offers selector
strategies and a page object pattern that, used deliberately, produce page objects whose
selectors survive the changes the application team will make next year.

## Scope

Covers the application of the page object model with Playwright, with a focus on selector
strategies that survive UI refactoring. Applies to test suites for any web application
exercised by Playwright, whether single-page or multi-page, whether server-rendered or
client-rendered. Does not cover general test architecture (that lives elsewhere in the
knowledge repository) nor the question of whether to use Playwright at all.

## Workflow or implementation guidance

1. **Treat the page object as a contract, not a helper.** A page object that exposes
   `loginPage.fillEmail(email)` and `loginPage.clickSubmit()` is a contract: the test code
   expresses intent, the page object knows how to translate it into DOM interaction. A
   page object that exposes the underlying `locator` to the test code has leaked its
   abstraction; the next UI change breaks the test, not the page object.
2. **Prefer user-facing attributes for selectors.** A selector based on `role`, `name`,
   `placeholder`, `label`, or visible text is a selector the next redesign will preserve
   because those attributes describe what the user sees and what the application does.
   A selector based on `class`, `id` patterns, or framework attributes is a selector the
   next redesign will change because those attributes describe how the implementation
   happens to be done today.
3. **Use Playwright's `getByRole`, `getByLabel`, `getByText`, `getByPlaceholder` as the
   default.** These locators are designed for the user-facing-attribute case and produce
   informative errors when the locator finds more than one element. Avoid the CSS and
   XPath locators except where the user-facing locators cannot express what is needed
   (for example, querying a specific element in a complex grid).
4. **Avoid selectors that depend on implementation details.** Selectors that include
   framework-internal classes (`ng-*`, `data-v-*`, hashed class names), component library
   prefixes, or attribute order break when the framework, library, or build pipeline
   changes. Even if the selectors work today, they encode a coupling that the test
   should not have.
5. **Centralise selectors inside the page object, never inline.** A selector that lives in
   a test file is a selector that has to be updated in every test file when it changes. A
   selector that lives in the page object is updated once. The cost of centralisation is
   the discipline of always reaching for the page object; the benefit is a single point
   of change.
6. **Use `data-testid` for cases where user-facing attributes are ambiguous.** When two
   elements share a role and label (a common case in dense tables or list rows),
   `data-testid` is a deliberate, application-team-recognised hook. The attribute must be
   added in the application code; treat it as a contract between the test author and the
   implementation team.
7. **Treat `data-testid` as the last resort, not the first.** A test surface that depends
   on `data-testid` everywhere signals that the application's accessibility attributes
   are not informative; the right fix is to improve the application's accessible
   attributes, not to keep adding `data-testid`. A test that requires a `data-testid` to
   find a button is a test that has noticed a real accessibility gap.
8. **Wrap Playwright's auto-waiting locators, not raw selectors.** The page object returns
   locators that Playwright's API auto-waits on (`getByRole(...).click()`); the test code
   does not need to manage waits. A page object that returns a `string` selector or a
   `Locator` constructed with raw selectors loses this property; the test code ends up
   re-implementing the wait discipline, and the abstraction leaks.
9. **Add a `describe` block per page object that documents the page's intent.** A page
   object whose class name is `CheckoutPage` is not self-documenting; a page object whose
   class name is `CheckoutPage` and whose `describe` block lists the user flows it
   supports is a contract that the next engineer can read. Naming flows (`fillShipping`,
   `applyCoupon`, `placeOrder`) makes the test code read like user intent.
10. **Version the page object with the page.** When the application changes a selector,
    update the page object in the same commit. A page object whose selectors no longer
    resolve is a page object that has not been maintained; remove or update it
    deliberately, do not let it rot.

A representative Playwright page object:

```ts
import { Page, Locator } from '@playwright/test';

export class CheckoutPage {
  readonly email: Locator;
  readonly placeOrder: Locator;
  readonly coupon: Locator;

  constructor(private readonly page: Page) {
    this.email = page.getByLabel('Email address');
    this.coupon = page.getByPlaceholder('Coupon code');
    this.placeOrder = page.getByRole('button', { name: 'Place order' });
  }

  async fillEmail(value: string) {
    await this.email.fill(value);
  }

  async applyCoupon(code: string) {
    await this.coupon.fill(code);
    await this.coupon.press('Enter');
  }

  async place() {
    await this.placeOrder.click();
  }
}
```

The test code reads as `await checkout.fillEmail('a@example.com')`; the DOM details live
inside the page object.

## Controls

- The page object's selectors are reviewed for user-facing attributes; reviewers reject
  selectors that depend on implementation details.
- `data-testid` is added only where user-facing locators fail; a test that introduces a
  new `data-testid` includes a comment explaining why the user-facing locator was
  insufficient.
- Page object classes are colocated with the tests that use them, in a directory the
  team owns; ad-hoc inline selectors in test files are rejected in review.
- A change to the application's DOM is reflected in the page object in the same commit;
  the page object is the documented single point of change.
- Auto-waiting locators are preferred; tests that manage waits manually with
  `waitForSelector` are reviewed and refactored where possible.

## Validation evidence

- A redesign that changes the application's CSS class names does not break the page
  object; the user-facing locators still resolve.
- A change to a `data-testid` value is caught at code review and accompanied by a
  page-object update in the same commit.
- A test that was flaky because of a race between click and navigation becomes
  deterministic once the page object uses `getByRole(...).click()`, which auto-waits.
- A page object with `getByRole`, `getByLabel`, and `getByPlaceholder` locators
  produces informative errors on failure, surfacing which user-visible attribute is
  ambiguous.

## Failure modes and correction

- *Selector based on a hashed class name.* Replace with `getByRole`/`getByLabel`; if
  none works, add a `data-testid` and document why.
- *Page object returns a `Locator` constructed from a raw CSS string.* Refactor to
  `getByRole` or another user-facing locator; do not let the abstraction leak.
- *Test code reaches into `page.locator(...)` directly.* Move the locator into the page
  object; the test code should only see the page object's methods.
- *Page object not updated with the page.* Treat as a defect in the change that
  updated the page; the page object must change in the same commit.
- *`data-testid` proliferation.* Each new `data-testid` is reviewed against the
  user-facing-locator alternative; if the alternative works, prefer it.
- *Page object grows too large.* Split by user flow (`CheckoutPageShipping`,
  `CheckoutPagePayment`); each page object represents a coherent set of actions.
- *Selector ambiguity not caught.* A `getByRole` that finds two elements is a
  selector ambiguity; tighten the locator with `name` or `hasText` rather than reach
  for `nth(0)`.

## Limitations

- User-facing locators depend on the application providing user-facing attributes. An
  application that does not expose roles, labels, or accessible names will not be
  testable through user-facing locators without remediation.
- `data-testid` is a permanent contract with the application team; adding many of them
  is a long-term commitment that must be respected by both sides.
- A page object that wraps a complex component library (for example, a date picker or a
  rich text editor) may need to expose methods that hide significant complexity; the
  abstraction is honest only if the test code does not need to know about it.
- Playwright's auto-waiting works on actions and expectations; it does not cover
  every race condition. A page object that depends on a specific animation timing still
  needs explicit waits in narrow cases.
- Page objects do not eliminate the need for selector debugging. When a test fails, the
  selector must still be resolvable in the Playwright trace viewer; the page object
  makes the resolution easier, not unnecessary.

## Canonical sources

- Playwright, *Best practices* (recommended selector strategies and the rationale for
  user-facing attributes): https://playwright.dev/docs/best-practices
- Playwright, *Page Object Model* (the page object pattern as recommended by
  Playwright): https://playwright.dev/docs/pom
- W3C Web Accessibility Initiative, *Web Content Accessibility Guidelines (WCAG)*
  (the source of the accessible-name and role attributes the locators rely on):
  https://www.w3.org/WAI/standards-guidelines/wcag/
