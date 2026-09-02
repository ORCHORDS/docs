# IEEE 29119-5 Keyword-Driven Testing Governance

## Purpose

IEEE 29119-5 defines a keyword-driven testing approach, where test cases are expressed using reusable keywords that abstract actions and verification. The standard supports test automation and reduces maintenance cost. Governance ensures that the keyword library is curated, that keywords are version-controlled, and that test design follows the keyword-driven approach consistently.

## Current context and source status

IEEE 29119-5 was published as the first edition in 2016, as part of the IEEE 29119 software testing family. The standard is a process and notation standard, not a certifiable standard. Other parts of the family cover test process (29119-2), test documentation (29119-3), and test techniques (29119-4). Verify the current IEEE 29119 family status before treating any clause identifier as a current requirement.

## Governance workflow and controls

### 1. Establish the keyword library

Define a keyword library that covers test actions (for example, login, submit form, navigate to page) and verification (for example, assert message, assert value). Reuse keywords across test cases.

### 2. Version the keyword library

Treat the keyword library as a reusable asset. Version it. Apply change management to keyword definitions. Maintain backward compatibility where possible.

### 3. Apply keyword-driven test design

Express test cases using the keyword library. Avoid inline test logic outside of keywords. Maintain traceability between test cases and requirements.

### 4. Implement the keyword executor

Implement a keyword executor that interprets test cases and dispatches to the system under test. The executor SHOULD support data-driven execution and parameterization.

### 5. Integrate with automation

Integrate keyword-driven tests with the test automation framework (Selenium, Playwright, Cypress, etc.). Run tests in CI. Track results.

### 6. Maintain keywords

When a new action is needed, add a keyword to the library. When a keyword becomes obsolete, deprecate it. Review the library periodically.

### 7. Report and analyze

Track keyword usage, test execution results, and defect detection rate by keyword. Use metrics to improve the library.

## Validation and evidence

- Keyword library with definitions and version.
- Keyword change log.
- Test cases expressed using keywords.
- Test execution reports.
- Keyword library review records.

## Failure correction

Common defects include keyword sprawl (too many similar keywords), inline test logic outside keywords, and keywords without versioning. Corrective actions include a keyword review cadence, a code review check for inline logic, and a versioning enforcement at commit.

## Limitations

- IEEE 29119-5 is a process and notation standard, not a certifiable standard.
- Keyword-driven testing requires upfront investment in the library.
- Some tests (for example, exploratory testing) are not well-suited to keyword-driven design.
- Keyword maintenance requires ongoing effort.

## Canonical sources

- IEEE 29119-5-2016, IEEE Standard for Software and Systems Engineering — Software Testing — Part 5: Keyword-Driven Testing, first edition.
- IEEE 29119-2, IEEE Standard for Software and Systems Engineering — Software Testing — Part 2: Test Processes.
- IEEE 29119-3, IEEE Standard for Software and Systems Engineering — Software Testing — Part 3: Test Documentation.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for test automation, the operations leaf for CI integration, and the business leaf for test coverage reporting.
