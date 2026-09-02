# NIST SP 800-22 Random Bit Generator Testing Governance

## Purpose

NIST SP 800-22 provides statistical test suites for validating random number generators (RNGs) and pseudorandom number generators (PRNGs). Governance ensures that RNG/PRNG implementations intended for cryptographic use are tested for statistical quality, that test failures are investigated, and that passing tests are not mistaken for cryptographic strength.

## Current context and source status

NIST SP 800-22 Rev. 1a was published in 2010. The standard provides 15 statistical tests that can be applied to bit sequences produced by RNGs. The tests are statistical and do not prove randomness. Verify the current NIST publications before treating any specific test result as the sole evidence of randomness quality.

## Governance workflow and controls

### 1. Apply tests during implementation

Apply SP 800-22 tests to RNG/PRNG implementations during development. Use NIST's reference test suite or equivalent.

### 2. Apply a minimum sample size

Apply tests to a sufficiently large sample. SP 800-22 guidance provides minimum sample sizes per test. Document the sample size used.

### 3. Investigate failures

Investigate any statistical test failure. Failure may indicate a weakness in the generator. Re-test after remediation.

### 4. Distinguish statistical from cryptographic

Recognize that statistical tests do not prove cryptographic strength. Statistical tests show absence of certain biases but do not prove unpredictability. Apply additional analysis for cryptographic use.

### 5. Test in production conditions

Test the generator in production-like conditions, including under load and after restart. Test reseeding behavior where applicable.

### 6. Document test results

Document the test results, including the generator configuration, the sample size, the test parameters, and the pass/fail per test.

### 7. Repeat tests periodically

Repeat tests periodically to detect drift or regression. Repeat tests after any change to the generator or its environment.

## Validation and evidence

- Test plan per generator.
- Test results documentation.
- Failure investigation records.
- Re-test evidence.

## Failure correction

Common defects include use of inappropriate sample sizes, ignoring test failures, and treating passing tests as proof of cryptographic strength. Corrective actions include a sample size review, a failure investigation procedure, and a documentation template that distinguishes statistical from cryptographic.

## Limitations

- SP 800-22 provides statistical tests, not cryptographic tests.
- Passing all 15 tests does not prove cryptographic strength.
- Tests are sensitive to the sample size and the generator implementation.
- Tests do not replace entropy estimation (SP 800-90B).

## Canonical sources

- NIST SP 800-22 Rev. 1a, A Statistical Test Suite for Random and Pseudorandom Number Generators for Cryptographic Applications, 2010.
- NIST SP 800-90B, Recommendation for the Entropy Sources Used for Random Bit Generation, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for cryptographic implementation, and the standards leaf for cryptographic standards.
