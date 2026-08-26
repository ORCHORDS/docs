# behaviour-driven-development-gherkin

**Issue:** Acceptance criteria written by product are ambiguous and not directly testable by engineers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A story says "user should be able to log in." Engineers interpret this differently. QA finds gaps at the end. Product says "that's not what I meant." The back-and-forth happens after code is written.

## Pattern / Solution
BDD uses Gherkin — a structured English-like format — to write scenarios that are unambiguous and executable as tests.

**Gherkin format:**
```gherkin
Feature: User login

  Scenario: Successful login with valid credentials
    Given I am on the login page
    And I have a registered account with email "alice@example.com"
    When I enter my email and correct password
    And I click "Sign in"
    Then I should be redirected to the dashboard
    And I should see "Welcome, Alice"

  Scenario: Failed login with wrong password
    Given I am on the login page
    When I enter my email and an incorrect password
    And I click "Sign in"
    Then I should see "Invalid email or password"
    And I should remain on the login page
```

**Process:**
1. Product owner writes feature narrative
2. Product + engineer + QA write scenarios together in a 30-min "three amigos" meeting
3. Engineers implement step definitions (Cucumber, Behave, Playwright, etc.)
4. Scenarios run as automated acceptance tests in CI

**Three amigos meeting format:**
- Product: "Here's the feature and the business rule"
- Engineer: "Here's how I'd implement it; edge cases I see are X, Y"
- QA: "Here are the failure scenarios I'd test"
- Output: a shared Gherkin file, committed to the repo alongside the ticket

**When BDD adds the most value:**
- User-facing workflows (login, checkout, form submission)
- Business rules with multiple edge cases
- Features where product and engineering often miscommunicate

## Gotchas
- Gherkin is not a replacement for unit tests — it's for acceptance/integration level
- "Given/When/Then" is a thinking discipline; step libraries should be thin, not business logic
- Over-specifying UI details in steps (button IDs, CSS classes) makes scenarios brittle

## Related
- `test-driven-development-workflow.md`
- `definition-of-ready-checklist.md`
- `definition-of-done-checklist.md`
